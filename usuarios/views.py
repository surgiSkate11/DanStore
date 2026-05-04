import threading
import re
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from django.core.mail import send_mail
from django.core.signing import TimestampSigner, SignatureExpired, BadSignature
from django.contrib.sessions.models import Session
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone

from empresas.models import SuscripcionEmpresa, Plan
from productos.models import Producto, TipoProducto
from tiendita_project.utils import form_errors_to_messages
from .models import UserProfile


def cerrar_todas_las_sesiones(user):
    """
    Busca y elimina de la base de datos todas las sesiones activas del usuario.
    """
    sesiones_activas = Session.objects.filter(expire_date__gte=timezone.now())
    for sesion in sesiones_activas:
        data = sesion.get_decoded()
        if str(user.pk) == str(data.get('_auth_user_id', '')):
            sesion.delete()


@login_required
def perfil(request):
    usuario = request.user
    # Asegurar que el perfil exista
    perfil, _ = UserProfile.objects.get_or_create(user=usuario)
    empresa = getattr(request, 'empresa', perfil.empresa)
    
    suscripcion = None
    if empresa:
        # Crear un plan por defecto si no hay ninguno en el sistema
        plan_basico, _ = Plan.objects.get_or_create(nombre="Plan Básico", defaults={'precio_mensual': 0, 'precio_anual': 0})
        # Crear suscripción de prueba de 30 días automáticamente si no tiene una
        suscripcion, _ = SuscripcionEmpresa.objects.get_or_create(
            empresa=empresa,
            defaults={
                'plan': plan_basico,
                'tipo_plan': 'mensual',
                'fecha_inicio': timezone.now(),
                'fecha_vencimiento': timezone.now() + timedelta(days=30)
            }
        )

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # 1. Actualizar datos personales básicos (Todos los roles)
                usuario.first_name = request.POST.get('first_name', '').strip()
                usuario.last_name = request.POST.get('last_name', '').strip()
                
                cambios_especiales = False
                requiere_relogin = False
                
                # --- 🔒 VALIDACIÓN Y ACTUALIZACIÓN DE USERNAME (Estilo GitHub) ---
                nuevo_username = request.POST.get('username', '').strip()
                if nuevo_username and nuevo_username != usuario.username:
                    if not re.match(r'^[a-zA-Z0-9_-]+$', nuevo_username):
                        messages.error(request, "El nombre de usuario solo puede contener letras, números, guiones y guiones bajos.")
                        return redirect('perfil')
                    if User.objects.filter(username__iexact=nuevo_username).exists():
                        messages.error(request, f"El nombre de usuario '{nuevo_username}' no está disponible.")
                        return redirect('perfil')
                    usuario.username = nuevo_username
                    cambios_especiales = True
                    requiere_relogin = True

                # --- 📧 VALIDACIÓN DE EMAIL CON CONFIRMACIÓN ---
                nuevo_email = request.POST.get('email', '').strip()
                if nuevo_email and nuevo_email != usuario.email:
                    if User.objects.filter(email__iexact=nuevo_email).exists():
                        messages.error(request, f"El correo '{nuevo_email}' ya está registrado en otra cuenta.")
                        return redirect('perfil')
                    
                    signer = TimestampSigner()
                    token = signer.sign_object({'user_id': usuario.id, 'new_email': nuevo_email})
                    verification_url = f"{request.scheme}://{request.get_host()}/usuarios/verificar-email/{token}/"
                    
                    app_name = cache.get('saas_app_name', 'Tiendita SaaS')
                    mensaje_txt = f"Hola {usuario.username},\n\nHas solicitado cambiar tu correo a {nuevo_email}.\nPor favor visita este enlace para confirmar (válido por 24 horas): {verification_url}\n\nSi no fuiste tú, ignora este correo."
                    
                    # Renderizar plantilla HTML
                    contexto_email = {
                        'username': usuario.username,
                        'nuevo_email': nuevo_email,
                        'verification_url': verification_url,
                        'app_name': app_name
                    }
                    mensaje_html = render_to_string('security/email_change_verification.html', contexto_email)

                    def enviar_verificacion_email_async():
                        try:
                            send_mail(
                                f'Confirma tu nuevo correo - {app_name}', mensaje_txt,
                                getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com'),
                                [nuevo_email], html_message=mensaje_html, fail_silently=True
                            )
                        except Exception as e:
                            print(f"Error enviando correo de confirmación de email: {e}")
                            
                    threading.Thread(target=enviar_verificacion_email_async).start()
                    messages.info(request, f"Por seguridad, hemos enviado un enlace a {nuevo_email}. Ábrelo para confirmar el cambio.")
                    cambios_especiales = True

                usuario.save()

                # 2. Si es DUEÑO, actualizamos los datos de la Empresa y Negocio Operativo
                if perfil.rol == 'owner':
                    perfil.nombre_negocio = request.POST.get('nombre_negocio', '').strip()
                    perfil.descripcion_negocio = request.POST.get('descripcion_negocio', '').strip()
                    perfil.negocio_tipo = request.POST.get('negocio_tipo', 'otro')
                    perfil.save()
                    
                    if empresa:
                        empresa.nombre = request.POST.get('nombre_empresa', '').strip()
                        empresa.save()

                if requiere_relogin:
                    cerrar_todas_las_sesiones(usuario)
                    logout(request) # Limpiamos la petición actual en memoria
                    messages.success(request, "Tu nombre de usuario ha sido actualizado. Por seguridad, hemos cerrado tus sesiones activas. Por favor, inicia sesión nuevamente.")
                    return redirect(getattr(settings, 'LOGIN_URL', '/'))

                if not cambios_especiales:
                    messages.success(request, 'Tu perfil se ha actualizado correctamente.')
                return redirect('perfil')
        except Exception as e:
            messages.error(request, f'Ocurrió un error al actualizar: {str(e)}')

    context = {'usuario': usuario, 'perfil': perfil, 'empresa': empresa, 'suscripcion': suscripcion}
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
            
            cerrar_todas_las_sesiones(user)
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
def onboarding(request):
    """Vista para configurar la cuenta la primera vez que se inicia sesión"""
    usuario = request.user
    perfil, _ = UserProfile.objects.get_or_create(user=usuario)

    # REGLA: El onboarding SOLO aplica para Dueños de Empresa
    if perfil.rol != 'owner':
        return redirect('dashboard_router')

    if request.method == 'POST':
        perfil.nombre_negocio = request.POST.get('nombre_negocio', '').strip()
        perfil.negocio_tipo = request.POST.get('negocio_tipo', 'otro')
        perfil.onboarding_completado = True
        perfil.save()
        return redirect('dashboard_router')
        
    context = {
        'tipos_negocio': UserProfile.TIPO_NEGOCIO_CHOICES,
    }
    return render(request, 'usuarios/onboarding.html', context)


@login_required
def limpiar_demo(request):
    """Desactiva el modo demo para el usuario actual"""
    perfil = request.user.profile
    if perfil.usa_demo_data:
        perfil.usa_demo_data = False
        perfil.save()
        messages.success(request, "Modo demostración desactivado correctamente.")
    return redirect('dashboard_router')


@login_required
def cargar_demo(request):
    """Activa el modo demo y genera algunos datos de prueba básicos"""
    if request.method == 'POST':
        perfil = request.user.profile
        empresa = getattr(request, 'empresa', None)
        
        if not perfil.usa_demo_data and empresa:
            # Crear una categoría y un par de productos de demostración
            tipo_demo, _ = TipoProducto.objects.get_or_create(nombre="Demo", empresa=empresa)
            
            Producto.objects.get_or_create(
                nombre="Producto de Demostración 1",
                empresa=empresa,
                defaults={'tipo_producto': tipo_demo, 'precio': 199.99, 'stock': 10, 'estado': 'disponible'}
            )
            Producto.objects.get_or_create(
                nombre="Producto de Demostración 2",
                empresa=empresa,
                defaults={'tipo_producto': tipo_demo, 'precio': 45.50, 'stock': 5, 'estado': 'disponible'}
            )
            
            perfil.usa_demo_data = True
            perfil.save()
            messages.success(request, "Datos de demostración cargados exitosamente.")
            
    return redirect('dashboard_router')


# ====================================================================
# FLUJO PROFESIONAL DE RECUPERACIÓN DE USUARIO (CORREO OCULTO)
# ====================================================================

def username_reset_request_view(request):
    """Paso 1: Solicita el correo para buscar el/los usuarios"""
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if email:
            usuarios = User.objects.filter(email__iexact=email)
            if usuarios.exists():
                # Guardamos el correo en sesión y pasamos al Paso 2
                request.session['reset_email'] = email
                return redirect('username_reset_masked')
            else:
                messages.error(request, "No encontramos ninguna cuenta asociada a este correo.")
    return render(request, 'security/username_reset_form.html')


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
                    send_mail(
                        'Recuperación de Usuario - Tiendita', mensaje_txt,
                        getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com'),
                        [email], html_message=mensaje_html, fail_silently=True
                    )
                except Exception as e:
                    print(f"Error enviando correo en segundo plano: {e}")
                    
            threading.Thread(target=enviar_recuperacion_async).start()
                
        del request.session['reset_email'] # Limpiar sesión por seguridad
        return redirect('username_reset_done')
        
    return render(request, 'security/username_reset_masked.html', {'correo_oculto': correo_oculto})


def recuperar_usuario_done(request):
    """Vista de confirmación de envío de correo para recuperación de usuario"""
    return render(request, 'security/username_reset_done.html')


# ====================================================================
# FLUJO PROFESIONAL DE RECUPERACIÓN DE CONTRASEÑA (CORREO OCULTO)
# ====================================================================

def password_reset_request_view(request):
    """Paso 1: Solicita el nombre de usuario para buscar su correo"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        try:
            user = User.objects.get(username__iexact=username)
            if user.email:
                # Guarda el ID en sesión temporalmente y pasa al Paso 2
                request.session['reset_uid'] = user.id
                return redirect('password_reset_masked')
            else:
                messages.error(request, "Este usuario no tiene un correo registrado.")
        except User.DoesNotExist:
            messages.error(request, "No encontramos ningún usuario con ese nombre.")
            
    return render(request, 'security/password_reset_form.html')


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
            
            def enviar_password_async():
                try:
                    form.save(
                        request=None, # Importante: desvincular de la petición activa
                        domain_override=host_actual, 
                        use_https=es_seguro,
                        email_template_name='security/password_reset_email.html',
                        subject_template_name='security/password_reset_subject.txt',
                        extra_email_context={'app_name': app_name},
                    )
                except Exception as e:
                    print(f"Error enviando correo de password: {e}")
                    
            threading.Thread(target=enviar_password_async).start()
            
            del request.session['reset_uid'] # Limpiar sesión por seguridad
            return redirect('password_reset_done')
        else:
            form_errors_to_messages(request, form)            
    return render(request, 'security/password_reset_masked.html', {'correo_oculto': correo_oculto})

class CustomLoginView(LoginView):
    def form_invalid(self, form):
        form_errors_to_messages(self.request, form)
        return super().form_invalid(form)