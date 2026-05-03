from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import UserProfile
from empresas.models import SuscripcionEmpresa, Plan
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import LoginView
from django.core.cache import cache
from tiendita_project.utils import form_errors_to_messages

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
                usuario.email = request.POST.get('email', '').strip()
                usuario.save()

                # 2. Si es DUEÑO, actualizamos los datos de la Empresa y Negocio
                if perfil.rol in ['owner', 'superadmin']:
                    perfil.nombre_negocio = request.POST.get('nombre_negocio', '').strip()
                    perfil.descripcion_negocio = request.POST.get('descripcion_negocio', '').strip()
                    perfil.negocio_tipo = request.POST.get('negocio_tipo', 'otro')
                    perfil.save()
                    
                    if empresa:
                        empresa.nombre = request.POST.get('nombre_empresa', '').strip()
                        empresa.save()

                messages.success(request, 'Tu perfil se ha actualizado correctamente.')
                return redirect('perfil')
        except Exception as e:
            messages.error(request, f'Ocurrió un error al actualizar: {str(e)}')

    context = {'usuario': usuario, 'perfil': perfil, 'empresa': empresa, 'suscripcion': suscripcion}
    return render(request, 'usuarios/perfil.html', context)


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
            from productos.models import Producto, TipoProducto
            
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
            
            try:
                send_mail(
                    'Recuperación de Usuario - Tiendita', mensaje_txt,
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com'),
                    [email], html_message=mensaje_html, fail_silently=True
                )
            except Exception as e:
                print(f"Error enviando correo: {e}")
                
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
            form.save(
                request=request,
                use_https=request.is_secure(),
                email_template_name='security/password_reset_email.html',
                subject_template_name='security/password_reset_subject.txt',
                extra_email_context={'app_name': app_name},
            )
            del request.session['reset_uid'] # Limpiar sesión por seguridad
            return redirect('password_reset_done')
        else:
            form_errors_to_messages(request, form)            
    return render(request, 'security/password_reset_masked.html', {'correo_oculto': correo_oculto})

class CustomLoginView(LoginView):
    def form_invalid(self, form):
        form_errors_to_messages(self.request, form)
        return super().form_invalid(form)