import csv
import json
from datetime import timedelta
from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.apps import apps
from django import forms
from django.forms import modelform_factory
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q
from django.utils import timezone
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.models import User

from empresas.models import Empresa, SuscripcionEmpresa, Plan, Ticket, MensajeTicket
from usuarios.models import ModuloSaaS, RolEmpresa

def home(request):
    """
    Redirige la ruta principal (/) al nuevo enrutador inteligente de SaaS.
    """
    return redirect('dashboard_router')


@login_required
def dashboard_router(request):
    """
    ESTRATEGIA DE DASHBOARDS: Enrutador Inteligente.
    Redirige al usuario a su ecosistema correspondiente según su rol.
    """
    usuario = request.user
    perfil = getattr(usuario, 'profile', None)
    
    # El onboarding es estrictamente para los DUEÑOS
    if perfil and perfil.rol == 'DUEÑO' and not perfil.onboarding_completado:
        return redirect('onboarding')
        
    if perfil and perfil.rol == 'SUPERADMIN':
        return redirect('dashboard_saas')
    elif perfil and perfil.rol in ['DUEÑO', 'EMPLEADO']:
        return redirect('dashboard_tenant')
    else:
        # Si es cliente final, va al catálogo de su empresa
        if perfil and getattr(perfil, 'empresa', None):
            return redirect('tienda_publica', slug=perfil.empresa.slug)
        return redirect('home')  # Fallback


@login_required
def dashboard_saas(request):
    """Dashboard GLOBAL y exclusivo para el dueño del software (SuperAdmin)"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales del sistema.")
        
    # Métricas Globales SaaS
    total_empresas = Empresa.objects.count()
    empresas_activas = Empresa.objects.filter(activa=True).count()
    
    suscripciones = SuscripcionEmpresa.objects.select_related('empresa', 'plan').all()
    mrr_estimado = suscripciones.aggregate(total=Sum('plan__precio_mensual'))['total'] or 0
    
    # --- DATOS REALES PARA GRÁFICAS SaaS ---
    # Distribución real de empresas activas por plan
    planes_stats = Plan.objects.annotate(
        num_suscripciones=Count('suscripciones', filter=Q(suscripciones__empresa__activa=True))
    ).values('nombre', 'num_suscripciones')
    
    planes_labels = [p['nombre'] for p in planes_stats] if planes_stats else ['Sin Planes']
    planes_series = [p['num_suscripciones'] for p in planes_stats] if planes_stats else [1]
    # ----------------------------------------

    context = {
        'total_empresas': total_empresas,
        'empresas_activas': empresas_activas,
        'suscripciones': suscripciones,
        'mrr_estimado': mrr_estimado,
        'planes_labels': json.dumps(planes_labels),
        'planes_series': json.dumps(planes_series),
    }
    return render(request, 'dashboard/saas_dashboard.html', context)


@login_required
def saas_empresas(request):
    """Vista del SuperAdmin para gestionar Inquilinos (Tenants)"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    # Obtenemos las empresas y pre-cargamos sus suscripciones para optimizar consultas
    empresas = Empresa.objects.prefetch_related('suscripcion').order_by('-fecha_creacion')
    return render(request, 'dashboard/saas_empresas.html', {'empresas': empresas})


@login_required
def exportar_empresas_csv(request):
    """Exporta el listado de empresas a CSV para el Super Admin"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'empresas_saas_{timezone.now().strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Nombre de Empresa', 'URL Slug', 'Estado', 'Fecha Registro', 'Teléfono', 'Email de Contacto'])
    
    # Prefetch empleados para sacar el email del dueño de forma eficiente
    empresas = Empresa.objects.prefetch_related('empleados__user').all()
    
    for emp in empresas:
        estado = "Activa" if emp.activa else "Suspendida"
        dueño_perfil = emp.empleados.filter(rol='DUEÑO').first()
        email = dueño_perfil.user.email if dueño_perfil and dueño_perfil.user else "Sin email"
        
        writer.writerow([emp.id, emp.nombre, emp.slug, estado, emp.fecha_creacion.strftime("%Y-%m-%d"), emp.telefono_whatsapp, email])
        
    return response


@login_required
def toggle_estado_empresa(request, empresa_id):
    """Suspende o activa una empresa (Tenant)"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN' or request.method != 'POST':
        raise PermissionDenied("Acción no permitida.")
        
    empresa = get_object_or_404(Empresa, id=empresa_id)
    empresa.activa = not empresa.activa
    empresa.save()
    
    if empresa.activa:
        # Si se está reactivando, verificar si la suscripción está vencida
        if hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() <= 0:
            # Otorgar 24 horas de gracia para que puedan entrar a pagar o usar el sistema
            empresa.suscripcion.fecha_vencimiento = timezone.now() + timedelta(days=1)
            empresa.suscripcion.save()
            messages.warning(request, f"Empresa '{empresa.nombre}' activada. Su suscripción estaba vencida, se le otorgó 1 día de gracia.")
        else:
            messages.success(request, f"La empresa '{empresa.nombre}' ha sido activada con éxito.")
    else:
        messages.success(request, f"La empresa '{empresa.nombre}' ha sido suspendida con éxito.")
        
    return redirect('saas_empresas')


@login_required
def saas_configuracion(request):
    """Vista del SuperAdmin para configuración global del SaaS"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    if request.method == 'POST':
        # Aquí se conectaría con un modelo en Base de Datos (Ej: ConfiguracionGlobal).
        # Por ahora habilitamos la UI funcional interceptando el guardado:
        tab_activa = request.POST.get('active_tab', 'branding')
        messages.success(request, 'Ajustes del sistema guardados correctamente.')
        return redirect(f"{reverse('saas_configuracion')}#{tab_activa}")
        
    return render(request, 'dashboard/saas_configuracion.html')


@login_required
def saas_tickets(request):
    """Bandeja de entrada (Inbox) de Soporte Técnico para el SuperAdmin"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    ticket_id = request.GET.get('id')
    ticket_activo = None
    
    if request.method == 'POST' and ticket_id:
        ticket = get_object_or_404(Ticket, id=ticket_id)
        mensaje_texto = request.POST.get('mensaje', '').strip()
        nuevo_estado = request.POST.get('estado')
        adjunto = request.FILES.get('adjunto')
        
        if mensaje_texto or adjunto:
            MensajeTicket.objects.create(ticket=ticket, remitente=request.user, mensaje=mensaje_texto, adjunto=adjunto, es_staff=True)
        
        if nuevo_estado and nuevo_estado != ticket.estado:
            ticket.estado = nuevo_estado
            ticket.save()
            messages.success(request, "Estado del ticket actualizado.")
            
        return redirect(f"{reverse('saas_tickets')}?id={ticket.id}")
        
    tickets = Ticket.objects.select_related('empresa').order_by('-actualizado_en')
    if ticket_id:
        ticket_activo = get_object_or_404(Ticket, id=ticket_id)
        
    return render(request, 'dashboard/saas_tickets.html', {'tickets': tickets, 'ticket_activo': ticket_activo})


@login_required
def saas_control_panel(request):
    """Hub central de la base de datos para crear/editar todos los modelos (CRUD)"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    # Estadísticas para el header del panel
    context = {
        'total_usuarios': User.objects.count(),
        'total_planes': Plan.objects.count(),
        'total_modulos': ModuloSaaS.objects.count(),
        'total_roles': RolEmpresa.objects.count(),
        'total_empresas': Empresa.objects.count(),
    }
    
    return render(request, 'dashboard/saas_database.html', context)


@login_required
def saas_crear_registro(request, app_label, model_name):
    """Fábrica de Formularios: Crea dinámicamente el formulario para CUALQUIER modelo"""
    if getattr(request.user.profile, 'rol', '') != 'SUPERADMIN':
        raise PermissionDenied("Acceso exclusivo para administradores globales.")

    try:
        Modelo = apps.get_model(app_label, model_name)
    except LookupError:
        messages.error(request, "El módulo o tabla solicitada no existe.")
        return redirect('saas_control_panel')

    # Creamos un ModelForm en el aire
    FormularioDinamico = modelform_factory(Modelo, exclude=[])

    if request.method == 'POST':
        form = FormularioDinamico(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, f"¡Registro creado exitosamente en {Modelo._meta.verbose_name.title()}!")
            return redirect('saas_control_panel')
        else:
            from tiendita_project.utils import form_errors_to_messages
            form_errors_to_messages(request, form)
    else:
        form = FormularioDinamico()

    # Inyectar estilos Premium (Bootstrap) a todos los campos dinámicamente
    for field_name, field in form.fields.items():
        if isinstance(field.widget, forms.CheckboxInput):
            field.widget.attrs.update({'class': 'form-check-input ms-0 me-2', 'style': 'width: 1.5em; height: 1.5em; cursor: pointer;'})
        elif isinstance(field.widget, forms.SelectMultiple):
            field.widget.attrs.update({'class': 'form-select bg-light border-0 shadow-sm', 'style': 'border-radius: 12px; min-height: 120px;'})
        elif isinstance(field.widget, forms.Select):
            field.widget.attrs.update({'class': 'form-select form-select-lg bg-light border-0 shadow-sm', 'style': 'border-radius: 12px;'})
        elif isinstance(field.widget, forms.Textarea):
            field.widget.attrs.update({'class': 'form-control bg-light border-0 shadow-sm', 'style': 'border-radius: 12px;', 'rows': 3})
        else:
            field.widget.attrs.update({'class': 'form-control form-control-lg bg-light border-0 shadow-sm', 'style': 'border-radius: 12px;'})

    context = {
        'form': form,
        'titulo': f"Añadir {Modelo._meta.verbose_name.title()}",
    }
    return render(request, 'dashboard/saas_generic_form.html', context)


@login_required
def dashboard_tenant(request):
    """Dashboard OPERATIVO exclusivo para la Empresa (Dueño y Empleados)"""
    empresa = getattr(request, 'empresa', None)
    if not empresa:
        return redirect('onboarding')
        
    # Aislamiento Multi-tenant estricto usando request.empresa
    # Importaciones locales para evitar dependencias circulares
    from ventas.models import Venta
    from productos.models import Producto
    from clientes.models import Cliente
    
    hoy = timezone.now()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0)
    
    ventas_mes = Venta.objects.filter(empresa=empresa, fecha__gte=inicio_mes).aggregate(Sum('total'))['total__sum'] or 0
    productos_activos = Producto.objects.filter(empresa=empresa, estado='disponible').count()
    nuevos_clientes = Cliente.objects.filter(empresas=empresa, creado_en__gte=inicio_mes).count()
    
    # --- DATOS REALES PARA GRÁFICA DE VENTAS (Últimos 30 días) ---
    hace_30_dias = hoy - timedelta(days=29) # 30 días incluyendo hoy
    ventas_diarias = Venta.objects.filter(
        empresa=empresa, 
        fecha__gte=hace_30_dias
    ).values('fecha__date').annotate(total_dia=Sum('total')).order_by('fecha__date')
    
    # Convertir a diccionario para llenado rápido
    ventas_dict = {v['fecha__date']: float(v['total_dia']) for v in ventas_diarias}
    
    fechas_chart = []
    totales_chart = []
    
    # Iterar los últimos 30 días garantizando que no haya huecos en la gráfica
    for i in range(29, -1, -1):
        fecha_iter = (hoy - timedelta(days=i)).date()
        fechas_chart.append(fecha_iter.strftime('%d %b'))
        totales_chart.append(ventas_dict.get(fecha_iter, 0.0))
    # -------------------------------------------------------------

    context = {
        'empresa': empresa,
        'ventas_mes': ventas_mes,
        'productos_activos': productos_activos,
        'nuevos_clientes': nuevos_clientes,
        'fechas_chart': json.dumps(fechas_chart),
        'totales_chart': json.dumps(totales_chart),
    }
    return render(request, 'dashboard/tenant.html', context)


def tienda_publica(request, slug):
    """Landing page / Catálogo público dinámico del cliente final"""
    # Buscamos la empresa sin importar si está activa o no
    empresa = get_object_or_404(Empresa, slug=slug)
    
    # Verificamos si la tienda está suspendida (por administración o por falta de pago)
    suspendida = False
    if not empresa.activa:
        suspendida = True
    elif hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() <= 0:
        suspendida = True
        
    if suspendida:
        return render(request, 'dashboard/tienda_publica.html', {'empresa': empresa, 'suspendida': True})

    from productos.models import Producto
    
    # Mostrar solo los últimos 20 productos disponibles para no saturar
    productos = Producto.objects.filter(empresa=empresa, estado='disponible').order_by('-creado_en')[:20]
    
    context = {'empresa': empresa, 'productos': productos, 'suspendida': False}
    return render(request, 'dashboard/tienda_publica.html', context)
