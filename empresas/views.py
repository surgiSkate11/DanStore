import calendar
import threading
import stripe
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth.models import User
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from usuarios.models import UserProfile, RolEmpresa, ModuloSaaS
from .models import Empresa, SuscripcionEmpresa, Ticket, MensajeTicket, Plan, ConfiguracionSaaS
from .mixins import requiere_rol_dueño, requiere_modulo


@login_required
@requiere_rol_dueño
def lista_roles(request):
    """Gestión de roles personalizados de la empresa"""
    roles = RolEmpresa.objects.filter(empresa=request.empresa).prefetch_related('modulos_permitidos')
    modulos = ModuloSaaS.objects.all()
    
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        modulos_ids = request.POST.getlist('modulos')
        action = request.POST.get('action', 'crear')
        rol_id = request.POST.get('rol_id')
        
        if nombre:
            # Recolectar permisos granulares del formulario (UI)
            permisos_json = {}
            if modulos_ids:
                modulos_objs = ModuloSaaS.objects.filter(id__in=modulos_ids)
                for mod in modulos_objs:
                    perms = request.POST.getlist(f'permisos_{mod.codigo}')
                    if request.POST.get('granular_ui') == 'true':
                        if 'ver' not in perms: perms.append('ver')
                        permisos_json[mod.codigo] = perms
                    else:
                        # Si no viene de la nueva UI, otorga Full Access por compatibilidad
                        permisos_json[mod.codigo] = ['ver', 'crear', 'editar', 'eliminar']
                        
            if action == 'crear':
                if RolEmpresa.objects.filter(empresa=request.empresa, nombre__iexact=nombre).exists():
                    messages.error(request, f"Ya existe un rol con el nombre '{nombre}'.")
                else:
                    rol = RolEmpresa.objects.create(empresa=request.empresa, nombre=nombre)
                    if modulos_ids:
                        rol.modulos_permitidos.set(modulos_ids)
                    rol.permisos_detallados = permisos_json
                    rol.save()
                    messages.success(request, f"Rol '{nombre}' creado exitosamente.")
            
            elif action == 'editar' and rol_id:
                rol = get_object_or_404(RolEmpresa, id=rol_id, empresa=request.empresa)
                rol.nombre = nombre
                rol.permisos_detallados = permisos_json
                rol.save()
                rol.modulos_permitidos.set(modulos_ids)
                messages.success(request, f"Rol '{nombre}' actualizado exitosamente.")
                
            return redirect('lista_roles')
            
    return render(request, 'empresas/roles.html', {'roles': roles, 'modulos': modulos})


@login_required
@requiere_rol_dueño
def lista_empleados(request):
    """Gestión de empleados de la empresa"""
    empleados = UserProfile.objects.filter(empresa=request.empresa, rol='EMPLEADO').select_related('user', 'rol_empresa')
    roles = RolEmpresa.objects.filter(empresa=request.empresa)
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        rol_id = request.POST.get('rol_id')
        
        if username and email and password and rol_id:
            try:
                with transaction.atomic():
                    # 1. Crear el usuario nativo de Django
                    user = User.objects.create_user(username=username, email=email, password=password)
                    
                    # 2. Configurar su perfil automáticamente (creado por signals)
                    profile = user.profile
                    profile.empresa = request.empresa
                    profile.rol = 'EMPLEADO'
                    profile.rol_empresa_id = rol_id
                    profile.onboarding_completado = True  # Bypass de onboarding
                    profile.save()
                    
                    messages.success(request, f"Empleado {username} añadido exitosamente.")
            except Exception as e:
                messages.error(request, f"Error al crear empleado. Es posible que el usuario ya exista.")
        return redirect('lista_empleados')
        
    return render(request, 'empresas/empleados.html', {'empleados': empleados, 'roles': roles})


@login_required
def cuenta_suspendida(request):
    """Vista de bloqueo cuando la suscripción de la empresa expira o es suspendida"""
    
    perfil = getattr(request.user, 'profile', None)
    empresa = getattr(request, 'empresa', None)
    if not empresa and perfil:
        empresa = perfil.empresa
        
    # VALIDACIÓN DE REACTIVACIÓN INMEDIATA
    # Si el usuario recarga la página pero ya fue reactivado (pagó o el Admin lo renovó), lo sacamos de aquí.
    if empresa and empresa.activa:
        if hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() > 0:
            messages.success(request, "¡Tu cuenta ha sido reactivada exitosamente!")
            return redirect('dashboard_router')
            
    # Determinar el motivo de la suspensión (Prioridad a la administrativa)
    motivo = 'pago'
    if empresa and not empresa.activa:
        motivo = 'admin'
        
    context = {
        'motivo': motivo,
        'empresa': empresa
    }
    
    # Solo consultamos y enviamos los planes si el motivo es por pago y el usuario es dueño
    if motivo == 'pago' and perfil and perfil.rol == 'DUEÑO':
        context['planes'] = Plan.objects.prefetch_related('modulos').order_by('precio_mensual')
        
    return render(request, 'empresas/suspendida.html', context)


@login_required
@requiere_rol_dueño
def configuracion_empresa(request):
    """Módulo para que el dueño personalice su marca, redes y landing page"""
    empresa = request.empresa
    if request.method == 'POST':
        empresa.telefono_whatsapp = request.POST.get('telefono_whatsapp', '').strip()
        empresa.instagram_url = request.POST.get('instagram_url', '').strip()
        empresa.facebook_url = request.POST.get('facebook_url', '').strip()
        empresa.youtube_url = request.POST.get('youtube_url', '').strip()
        empresa.landing_titulo = request.POST.get('landing_titulo', '').strip()
        empresa.landing_descripcion = request.POST.get('landing_descripcion', '').strip()
        empresa.mensaje_promocional = request.POST.get('mensaje_promocional', '').strip()
        empresa.color_primario = request.POST.get('color_primario', '#0d6efd').strip()
        empresa.save()
        
        messages.success(request, 'Configuración de la empresa actualizada con éxito.')
        return redirect('configuracion_empresa')
        
    return render(request, 'empresas/configuracion.html', {'empresa': empresa})


@login_required
def crear_ticket(request):
    """Vista para que el cliente (Dueño) envíe un ticket desde el modal de soporte"""
    if request.method == 'POST':
        asunto = request.POST.get('asunto', '').strip()
        categoria = request.POST.get('categoria')
        mensaje_texto = request.POST.get('mensaje', '').strip()
        adjunto = request.FILES.get('adjunto')
        
        # VALIDACIÓN CRÍTICA: Asunto y Mensaje Obligatorios en el Backend
        if not asunto or not mensaje_texto:
            messages.error(request, "El asunto y el mensaje son obligatorios para crear un ticket.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))
        
        empresa = getattr(request, 'empresa', getattr(request.user.profile, 'empresa', None))
        
        if not empresa:
            messages.error(request, "No tienes una empresa asociada para crear tickets.")
            return redirect(request.META.get('HTTP_REFERER', 'home'))
            
        with transaction.atomic():
            ticket = Ticket.objects.create(
                empresa=empresa, usuario=request.user, asunto=asunto,
                categoria=categoria, prioridad='media', estado='abierto'
            )
            MensajeTicket.objects.create(
                ticket=ticket, remitente=request.user, mensaje=mensaje_texto, adjunto=adjunto, es_staff=False
            )
            
        # FUNCIÓN ASÍNCRONA PARA NO BLOQUEAR LA PÁGINA
        def enviar_correos_async():
            try:
                config = ConfiguracionSaaS.objects.first()
                remitente = config.support_email if config and config.support_email else getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com')
                nombre_app = config.nombre_plataforma if config and config.nombre_plataforma else "Tiendita SaaS"
                
                # 1. Correo de confirmación para el Usuario que creó el ticket
                if request.user.email:
                    ctx_cliente = {
                        'usuario': request.user.first_name or request.user.username,
                        'asunto': asunto,
                        'categoria': ticket.get_categoria_display(),
                        'mensaje': mensaje_texto,
                        'app_name': nombre_app,
                        'ticket_id': ticket.id
                    }
                    html_cliente = render_to_string('dashboard/ticket_creado_cliente.html', ctx_cliente)
                    text_cliente = strip_tags(html_cliente)
                    send_mail(
                        subject=f"[Ticket #{ticket.id}] {asunto}",
                        message=text_cliente,
                        html_message=html_cliente,
                        from_email=remitente,
                        recipient_list=[request.user.email],
                        fail_silently=True
                    )
                    
                # 2. Correo de Alerta para el Administrador del SaaS (Dueño del Software)
                if config and config.support_email:
                    ctx_admin = {
                        'empresa': empresa.nombre,
                        'usuario': request.user.username,
                        'asunto': asunto,
                        'mensaje': mensaje_texto,
                        'app_name': nombre_app,
                        'ticket_id': ticket.id
                    }
                    html_admin = render_to_string('dashboard/ticket_creado_admin.html', ctx_admin)
                    text_admin = strip_tags(html_admin)
                    send_mail(
                        subject=f"NUEVO TICKET: [#{ticket.id}] {asunto}",
                        message=text_admin,
                        html_message=html_admin,
                        from_email=remitente,
                        recipient_list=[config.support_email],
                        fail_silently=True
                    )
            except Exception as e:
                print(f"Error enviando correo de confirmación de ticket: {e}")
                
        # Lanzar en segundo plano para que la respuesta sea inmediata
        threading.Thread(target=enviar_correos_async).start()
            
        messages.success(request, "Ticket enviado exitosamente. Revisa el comprobante con los detalles a tu correo electrónico.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required
@requiere_rol_dueño
def procesar_pago_saas(request, metodo, plan_id, tipo_plan):
    """Genera los links de pago (Checkout Sessions) para renovar planes"""
    
    # 1. Validar el plan
    plan = get_object_or_404(Plan, id=plan_id)
    
    # Determinar el precio y nombre exacto a cobrar basado en si es mensual o anual
    if tipo_plan == 'anual':
        precio_cobrar = plan.precio_anual
        nombre_plan_str = f"Suscripción Anual - {plan.nombre}"
    else:
        tipo_plan = 'mensual'  # Fallback seguro
        precio_cobrar = plan.precio_mensual
        nombre_plan_str = f"Suscripción Mensual - {plan.nombre}"
        
    if precio_cobrar <= 0:
        messages.error(request, f"El plan {plan.nombre} no tiene configurado un precio {tipo_plan} válido.")
        return redirect('cuenta_suspendida')

    # 2. Definir URLs absolutas de retorno para cuando el usuario termine de pagar
    url_exito = request.build_absolute_uri(reverse('pago_exitoso', args=[plan.id, tipo_plan]))
    url_cancelado = request.build_absolute_uri(reverse('cuenta_suspendida'))
    
    # 3. Obtener credenciales desde la base de datos
    config_saas = ConfiguracionSaaS.objects.first()
    if not config_saas:
        messages.error(request, "Las pasarelas de pago no están configuradas en el sistema SaaS.")
        return redirect('cuenta_suspendida')
        
    try:
        # ==========================================
        # PASARELA 1: STRIPE
        # ==========================================
        if metodo == 'stripe':
            if not config_saas.stripe_secret_key:
                raise Exception("La llave de Stripe no ha sido configurada por el administrador.")
            stripe.api_key = config_saas.stripe_secret_key
            
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                    'product_data': {'name': nombre_plan_str},
                    'unit_amount': int(precio_cobrar * 100), # Stripe cobra en centavos
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=url_exito,
                cancel_url=url_cancelado,
            )
            return redirect(session.url)
            
        # ==========================================
        # PASARELA 2: PAYPAL
        # ==========================================
        elif metodo == 'paypal':
            if not config_saas.paypal_client_id or not config_saas.paypal_secret_key:
                raise Exception("Las credenciales de PayPal no han sido configuradas.")
            client_id = config_saas.paypal_client_id
            client_secret = config_saas.paypal_secret_key
            environment = SandboxEnvironment(client_id=client_id, client_secret=client_secret)
            client = PayPalHttpClient(environment)
            
            request_paypal = OrdersCreateRequest()
            request_paypal.prefer('return=representation')
            request_paypal.request_body({
                "intent": "CAPTURE",
            "purchase_units": [{"amount": {"currency_code": "USD", "value": str(precio_cobrar)}}],
                "application_context": {
                    "return_url": url_exito,
                    "cancel_url": url_cancelado
                }
            })
            
            response = client.execute(request_paypal)
            for link in response.result.links:
                if link.rel == "approve":
                    return redirect(link.href)
                    
        # ==========================================
        # PASARELA 3: PAYPHONE (Ecuador/Latam)
        # ==========================================
        elif metodo == 'payphone':
            if not config_saas.payphone_token:
                raise Exception("El token de PayPhone no ha sido configurado.")
            payphone_token = config_saas.payphone_token
            headers = {
                'Authorization': f'Bearer {payphone_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                "amount": int(precio_cobrar * 100),
                "amountWithoutTax": int(precio_cobrar * 100),
                "clientTransactionId": f"plan_{plan.id}_user_{request.user.id}",
                "currency": "USD",
                "responseUrl": url_exito,
                "cancellationUrl": url_cancelado
            }
            
            response = requests.post('https://pay.payphonetodoesposible.com/api/button/Prepare', headers=headers, json=data)
            
            if response.status_code == 200:
                return redirect(response.json().get('paymentUrl'))
            else:
                raise Exception("Error de comunicación con PayPhone")
                
    except Exception as e:
        messages.error(request, f"Ocurrió un error al intentar conectar con {metodo.title()}: {str(e)}")
        return redirect('cuenta_suspendida')
        
    messages.error(request, "Método de pago no válido.")
    return redirect('cuenta_suspendida')


@login_required
@requiere_rol_dueño
def pago_exitoso(request, plan_id, tipo_plan):
    """Vista de retorno tras un pago exitoso. Renueva la suscripción automáticamente."""
    plan = get_object_or_404(Plan, id=plan_id)
    empresa = request.empresa
    
    if tipo_plan == 'anual':
        meses_a_sumar = 12
        texto_tiempo = "1 año"
    else:
        meses_a_sumar = 1
        texto_tiempo = "1 mes"
    
    suscripcion, created = SuscripcionEmpresa.objects.get_or_create(
        empresa=empresa,
        defaults={'plan': plan, 'fecha_vencimiento': timezone.now()}
    )
    
    fecha_base = timezone.now() if suscripcion.dias_restantes() <= 0 else suscripcion.fecha_vencimiento
    suscripcion.plan = plan
    suscripcion.tipo_plan = 'anual' if tipo_plan == 'anual' else 'mensual'
    
    # Cálculo exacto de mes calendario respetando 28, 30 y 31 días (y bisiestos)
    mes = fecha_base.month - 1 + meses_a_sumar
    año = fecha_base.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha_base.day, calendar.monthrange(año, mes)[1])
    
    suscripcion.fecha_vencimiento = fecha_base.replace(year=año, month=mes, day=dia)
    suscripcion.save()
    
    empresa.activa = True
    empresa.save()
    
    messages.success(request, f"¡Pago procesado exitosamente! Tu suscripción al '{plan.nombre}' ha sido renovada por {texto_tiempo}.")
    return redirect('dashboard_router')
