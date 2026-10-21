import logging
import threading
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.password_validation import validate_password, ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.http import Http404
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.db import transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, NoReverseMatch
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from empresas.mail_utils import enviar_correo_saas
from productos.models import Producto
from tiendita_project.utils import cerrar_sesiones_de_usuario, form_errors_to_messages
from .models import UserProfile

logger = logging.getLogger(__name__)
logger_seguridad = logging.getLogger('seguridad')


def ruta_trampa(request, *args, **kwargs):
    """Responde 404 a rutas que solo prueban los robots y registra el intento."""
    # %r escapa saltos de línea: X-Forwarded-For lo controla el cliente.
    logger_seguridad.warning(
        'Intento de acceso a %r desde %r',
        request.path,
        request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR')),
    )
    raise Http404


@login_required
def perfil(request):
    usuario = request.user

    # Un superadmin no tiene UserProfile (no es un usuario del dominio
    # de negocio), así que acá NO se hace get_or_create: eso volvería a
    # crearle una fila que no le corresponde. Se usa getattr para leer
    # el perfil solo si existe (será None para un superadmin).
    perfil = getattr(usuario, 'profile', None)

    empresa = getattr(request, 'empresa', None) or getattr(perfil, 'empresa', None)

    # La suscripción de la empresa YA NO se crea acá. Se asigna
    # automáticamente al momento de crear la Empresa (ver la señal
    # 'crear_suscripcion_inicial' en empresas/signals.py) — esta vista
    # solo LEE lo que ya existe, nunca genera un Plan ni una
    # Suscripción como efecto secundario de simplemente ver el perfil.
    suscripcion = getattr(empresa, 'suscripcion', None) if empresa else None

    if request.method == 'POST':
        with transaction.atomic():
            try:
                # 1. Actualizar datos personales básicos (Todos los roles)
                usuario.first_name = request.POST.get('first_name', '').strip()
                usuario.last_name = request.POST.get('last_name', '').strip()
                
                cambios_especiales = False
                requiere_relogin = False
                error_presente = False
                
                # --- VALIDACIÓN Y ACTUALIZACIÓN DE USERNAME  ---
                nuevo_username = request.POST.get('username', '').strip()
                if nuevo_username and nuevo_username != usuario.username:
                    if not re.match(r'^[a-zA-Z0-9_-]+$', nuevo_username):
                        messages.error(request, "El nombre de usuario solo puede contener letras, números, guiones y guiones bajos.")
                        error_presente = True
                    else:
                        # No se comprueba aquí, se deja que IntegrityError lo capture al guardar.
                        usuario.username = nuevo_username
                        cambios_especiales = True
                        requiere_relogin = True
                
                if error_presente:
                    return redirect('perfil')

                # --- VALIDACIÓN DE EMAIL CON CONFIRMACIÓN ---
                nuevo_email = request.POST.get('email', '').strip()
                if nuevo_email and nuevo_email != usuario.email:
                    # Se elimina la comprobación previa. La unicidad se valida en el enlace de confirmación.
                    signer = TimestampSigner()
                    token = signer.sign_object({'user_id': usuario.id, 'new_email': nuevo_email})
                    verification_url = request.build_absolute_uri(reverse('verificar_cambio_email', kwargs={'token': token}))
                    
                    app_name = cache.get('saas_app_name', 'Tiendita SaaS')
                    mensaje_txt = f"Hola {usuario.username},\n\nHas solicitado cambiar tu correo a {nuevo_email}.\nPor favor visita este enlace para confirmar (válido por 24 horas): {verification_url}\n\nSi no fuiste tú, ignora este correo."
                    
                    contexto_email = {
                        'username': usuario.username,
                        'nuevo_email': nuevo_email,
                        'verification_url': verification_url,
                        'app_name': app_name
                    }
                    mensaje_html = render_to_string('security/email_change_verification.html', contexto_email)

                    def enviar_verificacion_email_async():
                        enviar_correo_saas(
                            f'Confirma tu nuevo correo - {app_name}',
                            mensaje_txt,
                            [nuevo_email],
                            html_message=mensaje_html,
                            fail_silently=True,
                        )
                            
                    threading.Thread(target=enviar_verificacion_email_async).start()
                    messages.info(request, f"Por seguridad, hemos enviado un enlace a {nuevo_email}. Ábrelo para confirmar el cambio.")
                    cambios_especiales = True

                usuario.save()

                # 2. Si es DUEÑO, actualizamos los datos de la Empresa y Negocio Operativo
                # (perfil es None para un superadmin, por eso el chequeo "perfil and")
                if perfil and perfil.rol == 'owner':
                    perfil.nombre_negocio = request.POST.get('nombre_negocio', '').strip()
                    perfil.descripcion_negocio = request.POST.get('descripcion_negocio', '').strip()
                    perfil.negocio_tipo = request.POST.get('negocio_tipo', 'otro')
                    perfil.save()
                    
                    if empresa:
                        empresa.nombre = request.POST.get('nombre_empresa', '').strip()
                        empresa.save()

                if requiere_relogin:
                    cerrar_sesiones_de_usuario(usuario)
                    logout(request) # Limpiamos la petición actual en memoria
                    messages.success(request, "Tu nombre de usuario ha sido actualizado. Por seguridad, hemos cerrado tus sesiones activas. Por favor, inicia sesión nuevamente.")
                    return redirect(getattr(settings, 'LOGIN_URL', '/'))

                if not cambios_especiales:
                    messages.success(request, 'Tu perfil se ha actualizado correctamente.')
                return redirect('perfil')
            except IntegrityError:
                messages.error(request, "No se pudo actualizar el perfil. El nombre de usuario o correo electrónico ya está en uso por otra cuenta.")
                return redirect('perfil')

    context = {'usuario': usuario, 'perfil': perfil, 'empresa': empresa, 'suscripcion': suscripcion, 'tipos_negocio': UserProfile.TIPO_NEGOCIO_CHOICES}
    return render(request, 'usuarios/perfil.html', context)


def verificar_cambio_email(request, token):
    """Vista de confirmación de correo desde el enlace enviado"""
    signer = TimestampSigner()
    try:
        data = signer.unsign_object(token, max_age=86400) # Válido por 24 horas
        user = get_object_or_404(User, id=data.get('user_id'))
        new_email = data.get('new_email')
        
        if not User.objects.filter(email__iexact=new_email).exists():
            user.email = new_email
            user.save()
            
            cerrar_sesiones_de_usuario(user)
            if request.user.is_authenticated and request.user.id == user.id:
                logout(request)
            messages.success(request, "¡Tu correo electrónico ha sido actualizado exitosamente! Por seguridad, hemos cerrado tus sesiones activas. Inicia sesión de nuevo.")
            return redirect(getattr(settings, 'LOGIN_URL', '/'))
        else:
            messages.error(request, "El correo electrónico ya fue ocupado por otra cuenta.")
    except SignatureExpired:
        messages.error(request, "El enlace de verificación ha expirado. Solicita el cambio nuevamente desde tu perfil.")
    except BadSignature:
        messages.error(request, "El enlace de verificación es inválido o está corrupto.")
        
    return redirect('perfil')

@login_required
def forzar_cambio_password(request):
    """
    Vista para que los empleados cambien su contraseña temporal obligatoriamente.

    Un superadmin no tiene UserProfile, por lo tanto nunca tiene este
    flag: se usa getattr para no asumir que el perfil existe.
    """
    perfil = getattr(request.user, 'profile', None)
    # Si no hay perfil (superadmin) o no necesita cambiar la contraseña, lo sacamos de aquí.
    if not perfil or not perfil.debe_cambiar_password:
        return redirect('dashboard_router')

    if request.method == 'POST':
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        if password != password2:
            messages.error(request, "Las contraseñas no coinciden.")
            return redirect('forzar_cambio_password')

        try:
            validate_password(password, request.user)
            request.user.set_password(password)
            request.user.save()

            perfil.debe_cambiar_password = False
            perfil.save()

            cerrar_sesiones_de_usuario(request.user)
            logout(request)
            messages.success(request, "Tu contraseña ha sido actualizada. Por favor, inicia sesión de nuevo.")
            return redirect(getattr(settings, 'LOGIN_URL', '/'))
        except ValidationError as e:
            messages.error(request, f"La contraseña no es válida: {' '.join(e.messages)}")
            return redirect('forzar_cambio_password')

    return render(request, 'usuarios/forzar_cambio_password.html')


def _reverse_seguro(nombre_url, fallback='dashboard_router'):
    """
    Intenta resolver una URL por su nombre. Si no existe (por ejemplo,
    porque el nombre de la ruta de ventas/clientes/productos es distinto
    en este proyecto), cae al dashboard en vez de romper la página con
    un NoReverseMatch. Ajustar los nombres reales abajo en cuanto se
    confirmen las urls.py de ventas/clientes/productos.
    """
    try:
        return reverse(nombre_url)
    except NoReverseMatch:
        try:
            return reverse(fallback)
        except NoReverseMatch:
            return '/'

def _construir_contexto_onboarding(perfil, empresa):
    """
    Arma todo el contexto del onboarding leyendo suscripción, plan,
    módulos y progreso de configuración inicial de forma 100% defensiva:
    cualquier dato faltante, relación nula o modelo inexistente cae a un
    valor seguro por defecto — esta función nunca debe lanzar una excepción
    sin capturar, porque de eso depende que el onboarding no tire un 500.

    Los accesos rápidos y la checklist de "primeros pasos" se filtran
    SIEMPRE por los módulos reales del plan de la empresa — nunca se
    muestra un acceso a un módulo que el dueño no tiene contratado.
    """
    usuario = perfil.user

    contexto = {
        'usuario': usuario,
        'perfil': perfil,
        'empresa': empresa,
        'nombre_empresa': getattr(empresa, 'nombre', '') or 'tu empresa',
        'nombre_usuario': usuario.first_name.strip() if usuario.first_name else usuario.username,
        'empresa_activa': bool(getattr(empresa, 'activa', True)),
        'plan_nombre': 'Sin plan asignado',
        'tipo_plan_display': '',
        'fecha_inicio': None,
        'fecha_vencimiento': None,
        'dias_restantes': None,
        'porcentaje_consumido': 0,
        'estado_color': 'secondary',
        'limite_usuarios': None,       # None = ilimitado
        'usuarios_usados': 0,
        'modulos': [],
        'progreso_setup': 0,
        'pasos_pendientes': [],
        'accesos_rapidos': [],
    }

    # --- Suscripción, plan y módulos habilitados ---
    suscripcion = None
    try:
        suscripcion = getattr(empresa, 'suscripcion', None)
    except Exception:
        logger.warning("Onboarding: no se pudo leer la suscripción de la empresa %s", getattr(empresa, 'pk', '?'))

    if suscripcion:
        try:
            contexto['fecha_inicio'] = suscripcion.fecha_inicio
            contexto['fecha_vencimiento'] = suscripcion.fecha_vencimiento
            contexto['dias_restantes'] = suscripcion.dias_restantes()
            contexto['porcentaje_consumido'] = suscripcion.porcentaje_consumido()
            contexto['estado_color'] = suscripcion.estado_color()
            contexto['tipo_plan_display'] = suscripcion.get_tipo_plan_display()
        except Exception:
            logger.warning("Onboarding: error calculando datos de suscripción para empresa %s", getattr(empresa, 'pk', '?'))

        plan = getattr(suscripcion, 'plan', None)
        if plan:
            contexto['plan_nombre'] = plan.nombre
            contexto['limite_usuarios'] = plan.limite_empleados
            try:
                contexto['modulos'] = list(plan.modulos.all())
            except Exception:
                logger.warning("Onboarding: error leyendo módulos del plan %s", getattr(plan, 'pk', '?'))

    # Set de códigos de módulo del plan — única fuente de verdad para
    # decidir qué accesos rápidos y pasos de checklist se muestran.
    codigos_modulos = {m.codigo for m in contexto['modulos']}

    # --- Usuarios utilizados (empleados asociados a la empresa) ---
    try:
        contexto['usuarios_usados'] = empresa.empleados.count()
    except Exception:
        logger.warning("Onboarding: error contando empleados de la empresa %s", getattr(empresa, 'pk', '?'))

    # --- Progreso de configuración inicial (detecta pendientes) ---
    # Cada paso solo se agrega si el módulo correspondiente está en el
    # plan de la empresa. "Configurar empresa" siempre está disponible
    # porque no depende de ningún módulo operativo.
    pasos = []

    if 'productos' in codigos_modulos:
        try:
            tiene_productos = Producto.objects.filter(empresa=empresa).exists()
            pasos.append({'texto': 'Agregar tu primer producto', 'hecho': tiene_productos, 'url': reverse('crear_producto')})
        except NoReverseMatch:
            logger.warning("Onboarding: la url 'crear_producto' no existe, se omite ese paso")
        except Exception:
            logger.warning("Onboarding: no se pudo verificar productos de la empresa %s", getattr(empresa, 'pk', '?'))

    if 'clientes' in codigos_modulos:
        try:
            from clientes.models import Cliente
            tiene_clientes = Cliente.objects.filter(empresa=empresa).exists()
            pasos.append({'texto': 'Registrar tu primer cliente', 'hecho': tiene_clientes, 'url': reverse('crear_cliente')})
        except NoReverseMatch:
            logger.warning("Onboarding: la url 'crear_cliente' no existe, se omite ese paso")
        except Exception:
            logger.warning("Onboarding: app 'clientes' no disponible o sin campo empresa, se omite ese paso")

    if 'ventas' in codigos_modulos:
        try:
            from ventas.models import Venta
            tiene_ventas = Venta.objects.filter(empresa=empresa).exists()
            pasos.append({'texto': 'Crear tu primera venta', 'hecho': tiene_ventas, 'url': reverse('crear_venta')})
        except NoReverseMatch:
            logger.warning("Onboarding: la url 'crear_venta' no existe, se omite ese paso")
        except Exception:
            logger.warning("Onboarding: app 'ventas' no disponible o sin campo empresa, se omite ese paso")

    pasos.append({
        'texto': 'Configurar el logo y datos de tu empresa',
        'hecho': bool(getattr(empresa, 'logo', None)),
        'url': _reverse_seguro('perfil'),
    })

    total_pasos = len(pasos) or 1
    completados = sum(1 for p in pasos if p['hecho'])
    contexto['progreso_setup'] = int((completados / total_pasos) * 100)
    contexto['pasos_pendientes'] = pasos

    # --- Accesos rápidos del CTA: solo los módulos que el plan habilita ---
    catalogo_accesos = [
        {'codigo_requerido': 'ventas', 'texto': 'Crear primera venta', 'icono': 'bi-cart-plus', 'url_name': 'crear_venta'},
        {'codigo_requerido': 'clientes', 'texto': 'Registrar primer cliente', 'icono': 'bi-person-plus', 'url_name': 'crear_cliente'},
        {'codigo_requerido': 'productos', 'texto': 'Agregar primer producto', 'icono': 'bi-box-seam', 'url_name': 'crear_producto'},
    ]

    accesos_rapidos = []
    for acceso in catalogo_accesos:
        if acceso['codigo_requerido'] in codigos_modulos:
            try:
                url = reverse(acceso['url_name'])
            except NoReverseMatch:
                continue  # si la url no existe, se omite el acceso en vez de caer a /router/
            accesos_rapidos.append({'texto': acceso['texto'], 'icono': acceso['icono'], 'url': url})

    # "Configurar empresa" siempre está disponible, no depende de ningún módulo
    accesos_rapidos.append({'texto': 'Configurar empresa', 'icono': 'bi-gear', 'url': _reverse_seguro('perfil')})

    contexto['accesos_rapidos'] = accesos_rapidos

    return contexto


@login_required
def onboarding(request):
    """
    Pantalla de bienvenida al primer login. 
    El superadmin se saca de acá ANTES de tocar UserProfile.objects,
    """
    usuario = request.user

    if usuario.is_superuser:
        return redirect('dashboard_router')

    perfil = getattr(usuario, 'profile', None)

    if not perfil or perfil.rol != 'owner':
        return redirect('dashboard_router')

    # Si ya completó el onboarding antes, no tiene que volver a verlo
    # desde acá (para volver a verlo manualmente existe la opción en
    # Configuración, que resetea onboarding_completado a False).
    if perfil.onboarding_completado:
        return redirect('dashboard_router')

    empresa = perfil.empresa

    # El admin todavía no le asignó una Empresa: no dejamos "completar"
    # el onboarding en este estado, porque quedaría exactamente igual
    # de roto que antes (perfil.empresa = None, nada funciona después).
    if not empresa:
        return render(request, 'usuarios/onboarding_pendiente.html', {'perfil': perfil})

    # Se marca completado al mostrar la pantalla (GET), no al hacer clic.
    try:
        if not perfil.onboarding_completado:
            perfil.onboarding_completado = True
            perfil.save(update_fields=['onboarding_completado'])
    except Exception:
        logger.exception("Onboarding: no se pudo marcar onboarding_completado para el usuario %s", usuario.pk)

    try:
        contexto = _construir_contexto_onboarding(perfil, empresa)
    except Exception:
        # Blindaje final: si algo inesperado falla armando el contexto
        # enriquecido, igual mostramos el onboarding con lo mínimo
        # indispensable en vez de tirar un 500.
        logger.exception("Onboarding: fallo inesperado construyendo el contexto para la empresa %s", getattr(empresa, 'pk', '?'))
        contexto = {
            'usuario': usuario,
            'perfil': perfil,
            'empresa': empresa,
            'nombre_empresa': getattr(empresa, 'nombre', '') or 'tu empresa',
            'nombre_usuario': usuario.first_name or usuario.username,
            'accesos_rapidos': [],
            'pasos_pendientes': [],
            'modulos': [],
            'progreso_setup': 0,
        }

    return render(request, 'usuarios/onboarding.html', contexto)


# ====================================================================
# FLUJO DE RECUPERACIÓN DE USUARIO (CORREO OCULTO)
# ====================================================================

def username_reset_request_view(request):
    """Paso 1: Solicita el correo para buscar el/los usuarios"""
    error_message = None
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if email:
            usuarios = User.objects.filter(email__iexact=email)
            if usuarios.exists():
                # Guardamos el correo en sesión y pasamos al Paso 2
                request.session['reset_email'] = email
                request.session.set_expiry(600)
                return redirect('username_reset_masked')
            else:
                error_message = "No encontramos ninguna cuenta asociada a este correo."
    return render(request, 'security/username_reset_form.html', {'error_message': error_message})


def username_reset_masked_view(request):
    """Paso 2: Muestra el correo con asteriscos y confirma el envío"""
    email = request.session.get('reset_email')
    if not email:
        return redirect('username_reset')
        
    # Enmascarar el correo (ej: ju***@gmail.com)
    partes = email.split('@')
    if len(partes) == 2:
        nombre, dominio = partes
        correo_oculto = f"{nombre[:2]}{'*' * (len(nombre)-2)}@{dominio}" if len(nombre) > 2 else f"{nombre[0]}*@{dominio}"
    else:
        correo_oculto = email
        
    if request.method == 'POST':
        usuarios = User.objects.filter(email__iexact=email)
        if usuarios.exists():
            nombres_usuario = [u.username for u in usuarios]
            context = {'email': email, 'nombres_usuario': nombres_usuario}
            mensaje_html = render_to_string('security/username_reset_email.html', context)
            mensaje_txt = f"Hola,\n\nHemos recibido una solicitud para recordarte tu nombre de usuario.\n\nTus usuarios asociados son: {', '.join(nombres_usuario)}\n\nSi no solicitaste esto, puedes ignorar este correo."
            
            def enviar_recuperacion_async():
                try:
                    enviar_correo_saas(
                        'Recuperación de Usuario - Tiendita',
                        mensaje_txt,
                        [email],
                        html_message=mensaje_html,
                        fail_silently=False,
                    )
                except Exception:
                    logger.exception("Error enviando correo de recuperación de usuario")
                    
            threading.Thread(target=enviar_recuperacion_async).start()
                
        del request.session['reset_email'] # Limpiar sesión por seguridad
        return redirect('username_reset_done')
        
    return render(request, 'security/username_reset_masked.html', {'correo_oculto': correo_oculto})


def recuperar_usuario_done(request):
    """Vista de confirmación de envío de correo para recuperación de usuario"""
    return render(request, 'security/username_reset_done.html')


# ====================================================================
# FLUJO DE RECUPERACIÓN DE CONTRASEÑA (CORREO OCULTO)
# ====================================================================

def password_reset_request_view(request):
    """Paso 1: Solicita el nombre de usuario para buscar su correo"""
    error_message = None
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        try:
            user = User.objects.get(username__iexact=username)
            if user.email:
                # Guarda el ID en sesión temporalmente y pasa al Paso 2
                request.session['reset_uid'] = user.id
                request.session.set_expiry(600)
                return redirect('password_reset_masked')
            else:
                error_message = "Este usuario no tiene un correo registrado."
        except User.DoesNotExist:
            error_message = "No encontramos ningún usuario con ese nombre."
            
    return render(request, 'security/password_reset_form.html', {'error_message': error_message})


def password_reset_masked_view(request):
    """Paso 2: Muestra el correo con asteriscos y confirma el envío"""
    user_id = request.session.get('reset_uid')
    if not user_id:
        return redirect('password_reset')
        
    user = get_object_or_404(User, id=user_id)
    
    # Enmascarar el correo (ej: ju***@gmail.com)
    partes = user.email.split('@')
    if len(partes) == 2:
        nombre, dominio = partes
        correo_oculto = f"{nombre[:2]}{'*' * (len(nombre)-2)}@{dominio}" if len(nombre) > 2 else f"{nombre[0]}*@{dominio}"
    else:
        correo_oculto = user.email
        
    if request.method == 'POST':
        form = PasswordResetForm({'email': user.email})
        if form.is_valid():
            # Obtener el nombre del SaaS desde el caché (configurado por el SuperAdmin)
            app_name = cache.get('saas_app_name', 'Tiendita SaaS')
            
            # Extraer variables necesarias antes de abrir el hilo para evitar errores WSGI de petición cerrada
            host_actual = request.get_host()
            es_seguro = request.is_secure()
            protocolo = 'https' if es_seguro else 'http'
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f"{protocolo}://{host_actual}{reverse('password_reset_confirm', kwargs={'uidb64': uidb64, 'token': token})}"
            mensaje_html = render_to_string('security/password_reset_email.html', {
                'protocol': protocolo,
                'domain': host_actual,
                'uid': uidb64,
                'token': token,
                'app_name': app_name,
            })
            mensaje_txt = (
                f"Hola {user.username},\n\n"
                f"Hemos recibido una solicitud para restablecer tu contraseña.\n\n"
                f"Abre este enlace para crear una nueva contraseña:\n{reset_url}\n\n"
                f"Si no solicitaste este cambio, puedes ignorar este correo."
            )
            
            def enviar_password_async():
                try:
                    enviar_correo_saas(
                        f'Restablecer tu contraseña - {app_name}',
                        mensaje_txt,
                        [user.email],
                        html_message=mensaje_html,
                        fail_silently=False,
                    )
                except Exception:
                    logger.exception("Error enviando correo de recuperación de contraseña")
                    
            threading.Thread(target=enviar_password_async).start()
            
            del request.session['reset_uid'] # Limpiar sesión por seguridad
            return redirect('password_reset_done')
        else:
            form_errors_to_messages(request, form)            
    return render(request, 'security/password_reset_masked.html', {'correo_oculto': correo_oculto})

class CustomLoginView(LoginView):
    def form_invalid(self, form):
        messages.error(self.request, "Usuario o contraseña incorrectos.")
        return super().form_invalid(form)
    
def error_403_view(request, exception=None):
    """
    Vista personalizada para errores 403 (Permission Denied).
    Muestra una página amigable en vez de la genérica de Django.
    """
    return render(request, '403.html', status=403)