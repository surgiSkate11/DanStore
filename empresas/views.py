import calendar
import json
import threading
from datetime import timedelta

import requests
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from usuarios.models import ModuloSaaS, RolEmpresa, UserProfile
from .mixins import requiere_modulo, requiere_rol_dueño
from .models import ConfiguracionSaaS, Empresa, MensajeTicket, Plan, SuscripcionEmpresa, Ticket


@login_required
@requiere_rol_dueño
def lista_roles(request):
    """Gestión de roles personalizados de la empresa"""
    roles = RolEmpresa.objects.filter(empresa=request.empresa).prefetch_related('modulos_permitidos')
    
    for r in roles:
        r.permisos_json = json.dumps(r.permisos_detallados)
        r.modulos_ids = ",".join(str(m.id) for m in r.modulos_permitidos.all())
        
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
                
            elif action == 'eliminar' and rol_id:
                rol = get_object_or_404(RolEmpresa, id=rol_id, empresa=request.empresa)
                nombre_rol = rol.nombre
                rol.delete()
                messages.success(request, f"Rol '{nombre_rol}' eliminado. Los empleados asociados han perdido sus accesos hasta que les asignes un nuevo rol.")
                
            return redirect('lista_roles')
            
    return render(request, 'empresas/roles.html', {'roles': roles, 'modulos': modulos})


@login_required
@requiere_rol_dueño
def lista_empleados(request):
    """Gestión de empleados de la empresa"""
    empleados = UserProfile.objects.filter(empresa=request.empresa, rol__in=['employee', 'EMPLEADO']).select_related('user', 'rol_empresa')
    roles = RolEmpresa.objects.filter(empresa=request.empresa)
    
    if request.method == 'POST':
        action = request.POST.get('action', 'crear')
        
        if action == 'crear':
            username = request.POST.get('username')
            email = request.POST.get('email')
            password = request.POST.get('password')
            rol_id = request.POST.get('rol_id')
            
            if username and email and password and rol_id:
                try:
                    with transaction.atomic():
                        # 1. Crear el usuario nativo de Django
                        user = User.objects.create_user(username=username, email=email, password=password)
                        
                        # 2. Obtener o crear su perfil de forma segura
                        profile, _ = UserProfile.objects.get_or_create(user=user)
                        profile.empresa = request.empresa
                        profile.rol = 'employee'
                        profile.rol_empresa_id = rol_id
                        profile.onboarding_completado = True  # Bypass de onboarding
                        profile.save()
                        
                        messages.success(request, f"Empleado {username} añadido exitosamente.")
                except Exception as e:
                    messages.error(request, f"No se pudo crear el empleado: El nombre de usuario o correo ya está en uso.")
                    
        elif action == 'toggle_estado':
            empleado_id = request.POST.get('empleado_id')
            perfil = get_object_or_404(UserProfile, id=empleado_id, empresa=request.empresa, rol__in=['employee', 'EMPLEADO'])
            user = perfil.user
            user.is_active = not user.is_active
            user.save()
            estado_txt = "reactivado" if user.is_active else "suspendido"
            messages.success(request, f"El acceso del empleado '{user.username}' ha sido {estado_txt}.")
            
        elif action == 'eliminar':
            empleado_id = request.POST.get('empleado_id')
            perfil = get_object_or_404(UserProfile, id=empleado_id, empresa=request.empresa, rol__in=['employee', 'EMPLEADO'])
            username = perfil.user.username
            perfil.user.delete() # Elimina el usuario y su perfil en cascada
            messages.success(request, f"El empleado '{username}' ha sido eliminado definitivamente del sistema.")
            
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
        
    config_saas = ConfiguracionSaaS.objects.first()

    context = {
        'motivo': motivo,
        'empresa': empresa,
        'config_pagos': config_saas
    }
    
    # Solo consultamos y enviamos los planes si el motivo es por pago y el usuario es dueño
    if motivo == 'pago' and perfil and perfil.rol == 'owner':
        planes_qs = Plan.objects.prefetch_related('modulos').order_by('precio_mensual')
        
        # Preparar datos para JS en el frontend
        planes_data = []
        for plan in planes_qs:
            planes_data.append({
                'id': plan.id,
                'nombre': plan.nombre,
                'descripcion': plan.descripcion,
                'precio_mensual': float(plan.precio_mensual),
                'precio_anual': float(plan.precio_anual),
                'modulos': [{'nombre': m.nombre, 'icono': m.icono} for m in plan.modulos.all()]
            })
        context['planes_data_json'] = json.dumps(planes_data)
        context['planes'] = planes_qs # Mantener por retrocompatibilidad si es necesario

    return render(request, 'empresas/suspendida.html', context)


@login_required
@requiere_modulo('tienda', accion='editar')
def configuracion_tienda(request):
    """Módulo para que el dueño o empleado autorizado personalice la tienda pública"""
    empresa = request.empresa
    if request.method == 'POST':
        nuevo_nombre = request.POST.get('nombre_empresa', '').strip()
        if nuevo_nombre:
            empresa.nombre = nuevo_nombre
            
        empresa.telefono_whatsapp = request.POST.get('telefono_whatsapp', '').strip()
        empresa.instagram_url = request.POST.get('instagram_url', '').strip()
        empresa.facebook_url = request.POST.get('facebook_url', '').strip()
        empresa.youtube_url = request.POST.get('youtube_url', '').strip()
        empresa.sitio_web = request.POST.get('sitio_web', '').strip()
        empresa.tiktok_url = request.POST.get('tiktok_url', '').strip()
        empresa.x_url = request.POST.get('x_url', '').strip()
        empresa.landing_titulo = request.POST.get('landing_titulo', '').strip()
        empresa.landing_descripcion = request.POST.get('landing_descripcion', '').strip()
        empresa.mensaje_promocional = request.POST.get('mensaje_promocional', '').strip()
        empresa.color_primario = request.POST.get('color_primario', '#0d6efd').strip()
        empresa.color_fondo = request.POST.get('color_fondo', '#faf9f7').strip()
        empresa.color_cabecera = request.POST.get('color_cabecera', '#faf9f7').strip()
        empresa.color_texto = request.POST.get('color_texto', '#1a1611').strip()
        
        if 'logo' in request.FILES:
            empresa.logo = request.FILES['logo']
        empresa.save()
        
        messages.success(request, 'Configuración de la tienda actualizada con éxito.')
        return redirect('configuracion_tienda')
        
    return render(request, 'empresas/configuracion_tienda.html', {'empresa': empresa})


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
            
        # Hilo en segundo plano para no bloquear al usuario
        def enviar_email_ticket_async():
            try:
                app_name = cache.get('saas_app_name', 'Tiendita SaaS')
                
                # 1. Notificar al cliente
                cliente_html = render_to_string('emails/ticket_creado_cliente.html', {
                    'app_name': app_name, 'usuario': request.user.username,
                    'ticket_id': ticket.id, 'asunto': asunto, 
                    'categoria': ticket.get_categoria_display(), 'mensaje': mensaje_texto
                })
                send_mail(
                    f"Ticket #{ticket.id} Recibido", 
                    f"Hemos recibido tu ticket: {asunto}\n\nDetalle: {mensaje_texto}",
                    getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com'), 
                    [request.user.email], 
                    html_message=cliente_html,
                    fail_silently=True
                )
                
                # 2. Notificar al Admin del SaaS
                config = ConfiguracionSaaS.objects.first()
                admin_email = config.support_email if config and config.support_email else getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com')
                admin_html = render_to_string('emails/ticket_creado_admin.html', {
                    'empresa': empresa.nombre, 'ticket_id': ticket.id, 'asunto': asunto, 
                    'usuario': request.user.username, 'mensaje': mensaje_texto
                })
                send_mail("⚠️ Nuevo Ticket de Soporte", f"Ticket de {empresa.nombre}", getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com'), [admin_email], html_message=admin_html, fail_silently=True)
            except Exception as e:
                print(f"Error enviando correos de ticket: {e}")
                
        threading.Thread(target=enviar_email_ticket_async).start()
            
        messages.success(request, "Ticket enviado exitosamente. Revisa el comprobante con los detalles a tu correo electrónico.")
    return redirect(request.META.get('HTTP_REFERER', 'home'))


@login_required
@requiere_rol_dueño
def reportar_pago_transferencia(request):
    """Vista para que el dueño suba su comprobante de transferencia."""
    if request.method == 'POST':
        plan_id = request.POST.get('plan_id')
        tipo_plan = request.POST.get('tipo_plan')
        comprobante = request.FILES.get('comprobante')
        titular_cuenta = request.POST.get('titular_cuenta', 'No especificado').strip()
        cedula_cuenta = request.POST.get('cedula_cuenta', 'No especificado').strip()
        
        if not plan_id or not comprobante:
            messages.error(request, "Debe seleccionar un plan y adjuntar el comprobante de transferencia.")
            return redirect('cuenta_suspendida')
            
        plan = get_object_or_404(Plan, id=plan_id)
        empresa = request.empresa
        
        with transaction.atomic():
            asunto = f"COMPROBANTE DE PAGO: {empresa.nombre} - Plan {plan.nombre} ({tipo_plan.upper()})"
            ticket = Ticket.objects.create(
                empresa=empresa, usuario=request.user, asunto=asunto,
                categoria='facturacion', prioridad='alta', estado='abierto'
            )
            mensaje = f"He realizado el pago mediante transferencia bancaria para renovar la suscripción al Plan {plan.nombre} ({tipo_plan}).\n\nDatos de la transferencia:\n- Titular de la cuenta: {titular_cuenta}\n- CI/RUC: {cedula_cuenta}\n\nAdjunto el comprobante."
            MensajeTicket.objects.create(ticket=ticket, remitente=request.user, mensaje=mensaje, adjunto=comprobante, es_staff=False)
            
        messages.success(request, "¡Comprobante enviado! El administrador revisará tu pago y activará tu cuenta en breve.")
        return redirect('cuenta_suspendida')
    return redirect('cuenta_suspendida')


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
                
        # ==========================================
        # PASARELA 4: MERCADOPAGO
        # ==========================================
        elif metodo == 'mercadopago':
            if not getattr(config_saas, 'mercadopago_token', None):
                raise Exception("El token de MercadoPago no ha sido configurado.")
            
            headers = {
                'Authorization': f"Bearer {config_saas.mercadopago_token}",
                'Content-Type': 'application/json'
            }
            data = {
                "items": [{
                    "title": nombre_plan_str,
                    "quantity": 1,
                    "unit_price": float(precio_cobrar)
                }],
                "back_urls": {
                    "success": url_exito,
                    "failure": url_cancelado,
                    "pending": url_cancelado
                },
                "auto_return": "approved"
            }
            response = requests.post("https://api.mercadopago.com/checkout/preferences", headers=headers, json=data)
            if response.status_code in [200, 201]:
                return redirect(response.json().get('init_point'))
            else:
                raise Exception("Error de comunicación con MercadoPago")

        # ==========================================
        # PASARELA 5: COINBASE COMMERCE (CRIPTO)
        # ==========================================
        elif metodo == 'coinbase':
            if not getattr(config_saas, 'coinbase_api_key', None):
                raise Exception("La API Key de Coinbase no ha sido configurada.")
            
            headers = {
                'X-CC-Api-Key': config_saas.coinbase_api_key,
                'X-CC-Version': '2018-03-22',
                'Content-Type': 'application/json'
            }
            data = {
                "name": nombre_plan_str,
                "description": f"Renovación de {nombre_plan_str}",
                "local_price": {
                    "amount": str(precio_cobrar),
                    "currency": "USD"
                },
                "pricing_type": "fixed_price",
                "redirect_url": url_exito,
                "cancel_url": url_cancelado
            }
            response = requests.post('https://api.commerce.coinbase.com/charges', headers=headers, json=data)
            if response.status_code == 201:
                return redirect(response.json()['data']['hosted_url'])
            else:
                raise Exception("Error de comunicación con Coinbase Commerce")

        # ==========================================
        # PASARELA 6: RAZORPAY
        # ==========================================
        elif metodo == 'razorpay':
            if not getattr(config_saas, 'razorpay_key_id', None) or not getattr(config_saas, 'razorpay_key_secret', None):
                raise Exception("Las credenciales de Razorpay no han sido configuradas.")
            
            auth = (config_saas.razorpay_key_id, config_saas.razorpay_key_secret)
            data = {
                "amount": int(precio_cobrar * 100),
                "currency": "USD",
                "reference_id": f"plan_{plan.id}_user_{request.user.id}",
                "description": nombre_plan_str,
                "callback_url": url_exito,
                "callback_method": "get"
            }
            response = requests.post("https://api.razorpay.com/v1/payment_links", auth=auth, json=data)
            if response.status_code == 200:
                return redirect(response.json().get('short_url'))
            else:
                raise Exception("Error de comunicación con Razorpay")
                
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
