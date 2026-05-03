import csv
import json
import threading
import openpyxl
from datetime import timedelta

from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.apps import apps
from django import forms
from django.forms import modelform_factory
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum, Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone
from django.http import HttpResponse
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from empresas.models import Empresa, SuscripcionEmpresa, Plan, Ticket, MensajeTicket, ConfiguracionSaaS
from usuarios.models import ModuloSaaS, RolEmpresa
from ventas.models import Venta, DetalleVenta
from productos.models import Producto
from clientes.models import Cliente
from empresas.mixins import requiere_modulo
from tiendita_project.utils import form_errors_to_messages

# Identificadores internos de roles (Mejor mantenibilidad)
ROLE_SUPERADMIN = 'superadmin'
ROLE_OWNER = 'owner'
ROLE_EMPLOYEE = 'employee'

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
    if perfil and perfil.rol == ROLE_OWNER and not perfil.onboarding_completado:
        return redirect('onboarding')
        
    if perfil and perfil.rol == ROLE_SUPERADMIN:
        return redirect('dashboard_saas')
    elif perfil and perfil.rol in [ROLE_OWNER, ROLE_EMPLOYEE]:
        return redirect('dashboard_tenant')
    else:
        # Si es cliente final, va al catálogo de su empresa
        if perfil and getattr(perfil, 'empresa', None):
            return redirect('tienda_publica', slug=perfil.empresa.slug)
        return redirect('home')  # Fallback


@login_required
def dashboard_saas(request):
    """Dashboard GLOBAL y exclusivo para el dueño del software (SuperAdmin)"""
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
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
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    empresas = Empresa.objects.select_related('suscripcion').prefetch_related('empleados__user').order_by('-fecha_creacion')
    return render(request, 'dashboard/saas_empresas.html', {'empresas': empresas})


@login_required
def exportar_empresas_csv(request):
    """Exporta el listado de empresas a CSV para el Super Admin"""
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'empresas_saas_{timezone.now().strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    response.write(u'\ufeff'.encode('utf8'))  # Forzar codificación UTF-8 para Excel
    writer = csv.writer(response)
    writer.writerow(['ID', 'Nombre de Empresa', 'URL Slug', 'Estado', 'Fecha Registro', 'Teléfono', 'Email de Contacto'])
    
    # Prefetch empleados para sacar el email del dueño de forma eficiente
    empresas = Empresa.objects.prefetch_related('empleados__user').all()
    
    for emp in empresas:
        estado = "Activa" if emp.activa else "Suspendida"
        dueño_perfil = next((p for p in emp.empleados.all() if p.rol == ROLE_OWNER), None)
        email = dueño_perfil.user.email if dueño_perfil and dueño_perfil.user else "Sin email"
        
        writer.writerow([emp.id, emp.nombre, emp.slug, estado, emp.fecha_creacion.strftime("%Y-%m-%d"), emp.telefono_whatsapp, email])
        
    return response


@login_required
def toggle_estado_empresa(request, empresa_id):
    """Suspende o activa una empresa (Tenant)"""
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN or request.method != 'POST':
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
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    # Obtener la configuración o crearla si es la primera vez (singleton)
    config, created = ConfiguracionSaaS.objects.get_or_create(id=1)
        
    if request.method == 'POST':
        config.nombre_plataforma = request.POST.get('app_name', '')
        config.support_email = request.POST.get('support_email', '')
        config.theme_color = request.POST.get('theme_color', '')
        
        config.smtp_host = request.POST.get('smtp_host', '')
        config.smtp_port = request.POST.get('smtp_port', 587) or 587
        config.smtp_user = request.POST.get('smtp_user', '')
        smtp_pass = request.POST.get('smtp_pass', '')
        if smtp_pass:
            config.smtp_password = smtp_pass
        config.smtp_tls = request.POST.get('smtp_tls') == 'on'
        
        config.stripe_active = request.POST.get('stripe_active') == 'on'
        config.stripe_public_key = request.POST.get('stripe_public', '')
        stripe_secret = request.POST.get('stripe_secret', '')
        if stripe_secret:
            config.stripe_secret_key = stripe_secret
            
        config.paypal_active = request.POST.get('paypal_active') == 'on'
        config.paypal_client_id = request.POST.get('paypal_client_id', '')
        paypal_secret = request.POST.get('paypal_secret', '')
        if paypal_secret:
            config.paypal_secret_key = paypal_secret
            
        config.payphone_active = request.POST.get('payphone_active') == 'on'
        payphone_token = request.POST.get('payphone_token', '')
        if payphone_token:
            config.payphone_token = payphone_token
            
        config.force_2fa = request.POST.get('force_2fa') == 'on'
        config.session_timeout = request.POST.get('session_timeout', 120) or 120
        
        config.save()
        
        cache.delete('saas_app_name')

        tab_activa = request.POST.get('active_tab', 'branding')
        messages.success(request, 'Ajustes del sistema guardados correctamente.')
        return redirect(f"{reverse('saas_configuracion')}#{tab_activa}")
        
    return render(request, 'dashboard/saas_configuracion.html', {'config': config})


@login_required
def saas_tickets(request):
    """Bandeja de entrada (Inbox) de Soporte Técnico para el SuperAdmin"""
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
        raise PermissionDenied("Acceso exclusivo para administradores globales.")
        
    ticket_id = request.GET.get('id')
    filtro_actual = request.GET.get('filtro', 'inbox')
    ticket_activo = None
    
    if request.method == 'POST' and ticket_id:
        ticket = get_object_or_404(Ticket, id=ticket_id)
        
        if 'eliminar_ticket' in request.POST and request.POST.get('eliminar_ticket') == '1':
            ticket.delete()
            messages.success(request, "El ticket fue eliminado de forma permanente.")
            return redirect(f"{reverse('saas_tickets')}?filtro={filtro_actual}")
            
        mensaje_texto = request.POST.get('mensaje', '').strip()
        nuevo_estado = request.POST.get('estado')
        adjunto = request.FILES.get('adjunto')
        
        enviar_correo = False
        
        if mensaje_texto or adjunto:
            MensajeTicket.objects.create(ticket=ticket, remitente=request.user, mensaje=mensaje_texto, adjunto=adjunto, es_staff=True)
            enviar_correo = True
        
        if nuevo_estado and nuevo_estado != ticket.estado:
            ticket.estado = nuevo_estado
            ticket.save()
            if nuevo_estado == 'resuelto':
                messages.success(request, "Ticket archivado correctamente.")
            else:
                messages.success(request, "Estado del ticket actualizado.")
            
        # ENVÍO DE CORREO AUTOMÁTICO - Respuesta del Equipo de Soporte
        if enviar_correo and ticket.usuario and ticket.usuario.email:
            def enviar_respuesta_async():
                try:
                    config = ConfiguracionSaaS.objects.first()
                    remitente = config.support_email if config and config.support_email else getattr(settings, 'DEFAULT_FROM_EMAIL', 'soporte@tiendita.com')
                    nombre_app = config.nombre_plataforma if config and config.nombre_plataforma else "Tiendita SaaS"
                    
                    ctx_email = {
                        'usuario': ticket.usuario.first_name or ticket.usuario.username,
                        'asunto': ticket.asunto,
                        'respuesta': mensaje_texto,
                        'app_name': nombre_app,
                        'ticket_id': ticket.id
                    }
                    html_email = render_to_string('dashboard/ticket_respuesta.html', ctx_email)
                    text_email = strip_tags(html_email)
                    
                    send_mail(
                        subject=f"Re: [Ticket #{ticket.id}] {ticket.asunto}",
                        message=text_email,
                        html_message=html_email,
                        from_email=remitente,
                        recipient_list=[ticket.usuario.email],
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Error enviando correo de respuesta de ticket: {e}")
            
            threading.Thread(target=enviar_respuesta_async).start()
                
        return redirect(f"{reverse('saas_tickets')}?id={ticket.id}&filtro={filtro_actual}")
        
    if filtro_actual == 'archivados':
        tickets = Ticket.objects.filter(estado='resuelto').select_related('empresa').prefetch_related('mensajes').order_by('-actualizado_en')
    else:
        tickets = Ticket.objects.exclude(estado='resuelto').select_related('empresa').prefetch_related('mensajes').order_by('-actualizado_en')
        
    if ticket_id:
        ticket_activo = get_object_or_404(Ticket, id=ticket_id)
        
    return render(request, 'dashboard/saas_tickets.html', {'tickets': tickets, 'ticket_activo': ticket_activo, 'filtro_actual': filtro_actual})


@login_required
def saas_control_panel(request):
    """Hub central de la base de datos para crear/editar todos los modelos (CRUD)"""
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
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
    if getattr(request.user.profile, 'rol', '') != ROLE_SUPERADMIN:
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
        
    hoy = timezone.now()
    inicio_mes = hoy.replace(day=1, hour=0, minute=0, second=0)
    
    ventas_mes = Venta.objects.filter(
        empresa=empresa, fecha__gte=inicio_mes
    ).exclude(estado='anulada').aggregate(Sum('total'))['total__sum'] or 0
    productos_activos = Producto.objects.filter(empresa=empresa, estado='disponible').count()
    nuevos_clientes = Cliente.objects.filter(empresas=empresa, creado_en__gte=inicio_mes).count()
    
    hace_30_dias = hoy - timedelta(days=29) # 30 días incluyendo hoy
    ventas_diarias = Venta.objects.filter(
        empresa=empresa, 
        fecha__gte=hace_30_dias
    ).exclude(estado='anulada').values('fecha__date').annotate(total_dia=Sum('total')).order_by('fecha__date')
    
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
    return render(request, 'dashboard/tenant_dashboard.html', context)


@login_required
@requiere_modulo('reportes')
def tenant_reportes(request):
    """Módulo Avanzado de Reportes y Estadísticas para el Dueño"""
    empresa = getattr(request, 'empresa', None)
    if not empresa:
        return redirect('onboarding')
        
    # Filtro de días (Predeterminado a 30)
    try:
        dias = int(request.GET.get('dias', 30))
    except ValueError:
        dias = 30
        
    fecha_inicio = timezone.now() - timedelta(days=dias)
    
    ventas_periodo = Venta.objects.filter(empresa=empresa, fecha__gte=fecha_inicio).select_related('cliente')
    
    tipo_exportacion = request.GET.get('export')
    if tipo_exportacion in ['csv', 'excel']:
        if tipo_exportacion == 'excel':
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="reporte_ventas_{dias}_dias.xlsx"'
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Ventas"
            
            # --- TÍTULOS SUPERIORES ---
            ws.append([f"REPORTE DE VENTAS - {empresa.nombre.upper()}"])
            ws.append([f"Período: Últimos {dias} días"])
            ws.append([])
            
            # --- CABECERAS DE TABLA ---
            headers = ['ID Venta', 'Fecha', 'Cliente', 'Subtotal', 'Descuento', 'Total', 'Estado', 'Origen']
            ws.append(headers)
            
            # Estilos de Títulos y Cabeceras
            ws['A1'].font = Font(size=14, bold=True, color="1F2937")
            ws['A2'].font = Font(italic=True, color="6B7280")
            
            fill_header = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
            font_header = Font(color="FFFFFF", bold=True)
            thin_border = Border(left=Side(style='thin', color='4F46E5'), right=Side(style='thin', color='4F46E5'), top=Side(style='thin', color='4F46E5'), bottom=Side(style='thin', color='4F46E5'))
            
            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=4, column=col_num)
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = thin_border
                
            # Estilos estrictos para las celdas de datos
            fill_blanco = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
            fill_gris = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
            borde_datos = Border(
                left=Side(style='thin', color='E5E7EB'), right=Side(style='thin', color='E5E7EB'), 
                top=Side(style='thin', color='E5E7EB'), bottom=Side(style='thin', color='E5E7EB')
            )
            align_datos = Alignment(horizontal='left', vertical='center', wrap_text=False)
            align_centro = Alignment(horizontal='center', vertical='center', wrap_text=False)
            
            for row_idx, v in enumerate(ventas_periodo.order_by('-fecha'), start=5):
                cliente_nombre = v.cliente.nombre if v.cliente else 'Consumidor Final'
                
                try:
                    estado = v.get_estado_display()
                except AttributeError:
                    estado = getattr(v, 'estado', 'Completada')
                try:
                    origen = v.get_origen_display()
                except AttributeError:
                    origen = getattr(v, 'origen', 'Manual')
                    
                data_row = [
                    v.id, v.fecha.strftime("%Y-%m-%d %H:%M"), cliente_nombre, 
                    float(v.subtotal) if v.subtotal else 0, 
                    float(v.descuento) if v.descuento else 0, 
                    float(v.total) if v.total else 0, 
                    estado, origen
                ]
                
                # Inyectamos una barrera invisible (espacio) al final de la fila
                # para forzar a Excel a recortar la última columna y evitar desbordamientos
                data_row.append(" ")
                ws.append(data_row)
                
                # Aplicar color alternado (Zebra Striping)
                current_fill = fill_blanco if row_idx % 2 == 1 else fill_gris
                
                # Aplicar estilos, bordes y alineación a TODAS las celdas de la fila
                for col_num in range(1, len(headers) + 1):
                    cell = ws.cell(row=row_idx, column=col_num)
                    cell.fill = current_fill
                    cell.border = borde_datos
                    if col_num in [4, 5, 6]:
                        cell.number_format = '"$"#,##0.00'
                        cell.alignment = align_centro
                    elif col_num in [1, 2, 7, 8]:
                        cell.alignment = align_centro
                    else:
                        cell.alignment = align_datos
                        
            # Aplicar anchos estrictos y controlados para la tabla de Ventas
            anchos = {'A': 10, 'B': 18, 'C': 22, 'D': 12, 'E': 12, 'F': 12, 'G': 12, 'H': 16}
            for col, ancho in anchos.items():
                ws.column_dimensions[col].width = ancho
                
            wb.save(response)
            return response
        else:
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="reporte_ventas_{dias}_dias.csv"'
            response.write(u'\ufeff'.encode('utf8'))  # BOM para tildes
            writer = csv.writer(response)
            
            # --- TÍTULOS SUPERIORES CSV ---
            writer.writerow([f"REPORTE DE VENTAS - {empresa.nombre.upper()}"])
            writer.writerow([f"Período: Últimos {dias} días"])
            writer.writerow([])
            writer.writerow(['ID Venta', 'Fecha', 'Cliente', 'Subtotal', 'Descuento', 'Total', 'Estado', 'Origen'])
        
        for v in ventas_periodo.order_by('-fecha'):
            cliente_nombre = v.cliente.nombre if v.cliente else 'Consumidor Final'
            
            try:
                estado = v.get_estado_display()
            except AttributeError:
                estado = getattr(v, 'estado', 'Completada')
            try:
                origen = v.get_origen_display()
            except AttributeError:
                origen = getattr(v, 'origen', 'Manual')
                
            writer.writerow([
                v.id, 
                v.fecha.strftime("%Y-%m-%d %H:%M"), 
                cliente_nombre, 
                v.subtotal, 
                v.descuento, 
                v.total, 
                estado,
                origen
            ])
        return response
        
    # 1.5 Exportación de Catálogo de Productos
    if tipo_exportacion in ['productos_csv', 'productos_excel']:
        estado_prod = request.GET.get('estado_prod', '')
        categoria_prod = request.GET.get('categoria_prod', '')
        precio_min = request.GET.get('precio_min', '')
        precio_max = request.GET.get('precio_max', '')
        
        productos = Producto.objects.filter(empresa=empresa)
        
        if estado_prod:
            productos = productos.filter(estado=estado_prod)
        if categoria_prod:
            productos = productos.filter(categoria__icontains=categoria_prod)
        if precio_min:
            try: productos = productos.filter(precio__gte=float(precio_min))
            except ValueError: pass
        if precio_max:
            try: productos = productos.filter(precio__lte=float(precio_max))
            except ValueError: pass
            
        productos = productos.select_related('tipo_producto').order_by('nombre')
        
        if tipo_exportacion == 'productos_excel':
            response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="catalogo_productos.xlsx"'
            
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Productos"
            
            # --- TÍTULOS SUPERIORES ---
            ws.append([f"CATÁLOGO DE PRODUCTOS - {empresa.nombre.upper()}"])
            est_txt = estado_prod.title() if estado_prod else "Todos"
            cat_txt = categoria_prod.title() if categoria_prod else "Todas"
            ws.append([f"Filtros -> Estado: {est_txt} | Categoría: {cat_txt}"])
            ws.append([])
            
            # --- CABECERAS DE TABLA ---
            headers = ['ID', 'Nombre', 'Tipo', 'Categoría', 'Variante', 'Marca', 'Color', 'Precio Venta', 'Precio Costo', 'Stock', 'Estado']
            ws.append(headers)
            
            # Estilos de Títulos y Cabeceras
            ws['A1'].font = Font(size=14, bold=True, color="1F2937")
            ws['A2'].font = Font(italic=True, color="6B7280")
            
            fill_header = PatternFill(start_color="10B981", end_color="10B981", fill_type="solid")
            font_header = Font(color="FFFFFF", bold=True)
            thin_border_prod = Border(left=Side(style='thin', color='10B981'), right=Side(style='thin', color='10B981'), top=Side(style='thin', color='10B981'), bottom=Side(style='thin', color='10B981'))
            
            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=4, column=col_num)
                cell.fill = fill_header
                cell.font = font_header
                cell.alignment = Alignment(horizontal='center', vertical='center')
                cell.border = thin_border_prod
                
            # Estilos estrictos para celdas de datos
            fill_blanco = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
            fill_gris = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
            borde_datos = Border(
                left=Side(style='thin', color='E5E7EB'), right=Side(style='thin', color='E5E7EB'), 
                top=Side(style='thin', color='E5E7EB'), bottom=Side(style='thin', color='E5E7EB')
            )
            align_datos = Alignment(horizontal='left', vertical='center', wrap_text=False)
            align_centro = Alignment(horizontal='center', vertical='center', wrap_text=False)
            
            for row_idx, p in enumerate(productos, start=5):
                tipo_nombre = p.tipo_producto.nombre if p.tipo_producto else 'General'
                
                try:
                    estado_prod = p.get_estado_display()
                except AttributeError:
                    estado_prod = getattr(p, 'estado', 'Disponible')
                    
                data_row = [
                    p.id, p.nombre, tipo_nombre, p.categoria, p.variante, p.marca, p.color, 
                    float(p.precio) if p.precio else 0, 
                    float(getattr(p, 'precio_costo', 0)) if getattr(p, 'precio_costo', 0) else 0, 
                    p.stock, estado_prod
                ]
                
                # Inyectamos una barrera invisible (espacio) al final de la fila
                data_row.append(" ")
                ws.append(data_row)
                
                # Aplicar color alternado (Zebra Striping)
                current_fill = fill_blanco if row_idx % 2 == 1 else fill_gris
                
                # Aplicar estilos, bordes y alineación a TODAS las celdas de la fila
                for col_num in range(1, len(headers) + 1):
                    cell = ws.cell(row=row_idx, column=col_num)
                    cell.fill = current_fill
                    cell.border = borde_datos
                    if col_num in [8, 9]:
                        cell.number_format = '"$"#,##0.00'
                        cell.alignment = align_centro
                    elif col_num in [1, 10, 11]:
                        cell.alignment = align_centro
                    else:
                        cell.alignment = align_datos
                        
            # Aplicar anchos estrictos y controlados para la tabla de Productos
            anchos = {'A': 8, 'B': 22, 'C': 15, 'D': 15, 'E': 15, 'F': 15, 'G': 15, 'H': 12, 'I': 12, 'J': 10, 'K': 12}
            for col, ancho in anchos.items():
                ws.column_dimensions[col].width = ancho
                
            wb.save(response)
            return response
        else:
            response = HttpResponse(content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="catalogo_productos.csv"'
            response.write(u'\ufeff'.encode('utf8'))  # BOM para tildes
            writer = csv.writer(response)
            
            # --- TÍTULOS SUPERIORES CSV ---
            est_txt = estado_prod.title() if estado_prod else "Todos"
            cat_txt = categoria_prod.title() if categoria_prod else "Todas"
            writer.writerow([f"CATÁLOGO DE PRODUCTOS - {empresa.nombre.upper()}"])
            writer.writerow([f"Filtros -> Estado: {est_txt} | Categoría: {cat_txt}"])
            writer.writerow([])
            writer.writerow(['ID', 'Nombre', 'Tipo', 'Categoría', 'Variante', 'Marca', 'Color', 'Precio Venta', 'Precio Costo', 'Stock', 'Estado'])
        
        for p in productos:
            tipo_nombre = p.tipo_producto.nombre if p.tipo_producto else 'General'
            writer.writerow([p.id, p.nombre, tipo_nombre, p.categoria, p.variante, p.marca, p.color, p.precio, getattr(p, 'precio_costo', 0), p.stock, p.get_estado_display() if hasattr(p, 'get_estado_display') else p.estado])
            
        return response
        
    # Filtrar ventas anuladas para los cálculos financieros
    ventas_validas = ventas_periodo.exclude(estado='anulada')

    # 2. KPIs Rápidos
    total_ingresos = ventas_validas.aggregate(Sum('total'))['total__sum'] or 0
    total_ventas = ventas_validas.count()
    ticket_promedio = (total_ingresos / total_ventas) if total_ventas > 0 else 0
    
    # 3. Gráfica de Ingresos Organizados y Rellenos
    fechas_chart, totales_chart = [], []
    
    hoy = timezone.now().date()
    if dias == 365:
        ventas_agrupadas = ventas_validas.annotate(mes=TruncMonth('fecha')).values('mes').annotate(total_mes=Sum('total')).order_by('mes')
        datos_dict = {v['mes'].strftime('%Y-%m'): float(v['total_mes']) for v in ventas_agrupadas if v['mes']}
        
        meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}
        
        for i in range(11, -1, -1):
            m = hoy.month - i
            y = hoy.year
            while m <= 0:
                m += 12
                y -= 1
                
            llave = f"{y}-{m:02d}"
            fechas_chart.append(f"{meses_es[m]} {y}")
            totales_chart.append(datos_dict.get(llave, 0.0))
    else:
        ventas_diarias = ventas_validas.values('fecha__date').annotate(total_dia=Sum('total')).order_by('fecha__date')
        fechas_dict = {v['fecha__date']: float(v['total_dia']) for v in ventas_diarias if v['fecha__date']}
        
        for i in range(dias - 1, -1, -1):
            fecha_iter = hoy - timedelta(days=i)
            fechas_chart.append(fecha_iter.strftime('%d %b'))
            totales_chart.append(fechas_dict.get(fecha_iter, 0.0))
        
    # 4. Top 10 Productos Más Exitosos
    top_productos = DetalleVenta.objects.filter(venta__empresa=empresa, venta__fecha__gte=fecha_inicio).exclude(venta__estado='anulada')\
        .values('producto__nombre', 'producto__tipo_producto__nombre')\
        .annotate(cantidad_vendida=Count('id'), ingresos=Sum('precio_unitario')).order_by('-cantidad_vendida')[:10]
        
    # 5. Top 10 Mejores Clientes
    top_clientes = ventas_validas.filter(cliente__isnull=False)\
        .values('cliente__nombre', 'cliente__ruc_cedula')\
        .annotate(num_compras=Count('id'), total_comprado=Sum('total')).order_by('-total_comprado')[:10]

    # 6. Categorías existentes para el autocompletado en el formulario de exportación
    categorias_existentes = list(Producto.objects.filter(empresa=empresa).exclude(categoria='').values_list('categoria', flat=True).distinct().order_by('categoria'))

    context = {
        'empresa': empresa, 'dias': dias, 'total_ingresos': total_ingresos, 'total_ventas': total_ventas,
        'ticket_promedio': ticket_promedio, 'top_productos': top_productos, 'top_clientes': top_clientes,
        'fechas_chart': json.dumps(fechas_chart), 'totales_chart': json.dumps(totales_chart),
        'categorias_existentes': json.dumps(categorias_existentes),
    }
    return render(request, 'dashboard/tenant_reportes.html', context)


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

    productos = Producto.objects.filter(empresa=empresa, estado='disponible').select_related('tipo_producto').order_by('-creado_en')[:20]
    
    context = {'empresa': empresa, 'productos': productos, 'suspendida': False}
    return render(request, 'dashboard/tienda_publica.html', context)
