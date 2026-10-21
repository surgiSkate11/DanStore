import json
import csv
import logging
from datetime import timedelta
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone
from ventas.models import Venta, DetalleVenta
from ventas.views import RUC_CONSUMIDOR_FINAL
from productos.models import Producto
from .models import Cliente
from .forms import ClienteForm
from empresas.mixins import requiere_modulo
from tiendita_project.utils import form_errors_to_messages

logger = logging.getLogger(__name__)


def clientes_de_empresa(empresa):
    """Clientes de la empresa, sin el consumidor final: es una sola fila compartida por todas."""
    if not empresa:
        # filter(empresas=None) devolvería los clientes sin empresa.
        return Cliente.objects.none()
    return Cliente.objects.filter(empresas=empresa).exclude(ruc_cedula=RUC_CONSUMIDOR_FINAL)


@login_required
@requiere_modulo('clientes', accion='crear')
def api_crear_cliente(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            
            # Usar el formulario para centralizar las validaciones (letras, números, longitudes)
            form = ClienteForm(data)
            
            if form.is_valid():
                ruc_cedula = form.cleaned_data['ruc_cedula']
                
                # Reutilizar únicamente clientes ya asociados a esta empresa.
                cliente = Cliente.objects.filter(
                    ruc_cedula=ruc_cedula,
                    empresas=request.empresa,
                ).first()
                
                if not cliente and Cliente.objects.filter(ruc_cedula=ruc_cedula).exists():
                    return JsonResponse({
                        'success': False,
                        'error': 'Ya existe un cliente con esa Cédula en otra empresa y sus datos no están disponibles.'
                    }, status=409)

                if not cliente:
                    cliente = form.save(commit=False)
                    cliente.save()
                    
                # Asociación multitenant
                if hasattr(request, 'empresa') and request.empresa:
                    cliente.empresas.add(request.empresa)
                
                return JsonResponse({'success': True, 'id': cliente.id, 'nombre': cliente.nombre, 'ruc_cedula': cliente.ruc_cedula, 'telefono': cliente.telefono})
            else:
                # Si el formulario no es válido, devolver los errores al frontend
                errores = {campo: mensajes[0] for campo, mensajes in form.errors.items()}
                return JsonResponse({'success': False, 'error': errores}, status=400)
                
        except Exception as e:
            logger.exception('Error inesperado en api_crear_cliente (empresa %s, usuario %s)', getattr(getattr(request, 'empresa', None), 'id', None), request.user.id)
            return JsonResponse({'success': False, 'error': 'Ocurrió un error inesperado. Intenta nuevamente o contacta al administrador.'}, status=500)
    return JsonResponse({'error': 'Método no permitido'}, status=405)

@login_required
@requiere_modulo('clientes')
def lista_clientes(request):
    """Dashboard unificado de clientes: top compradores, directorio y control de deudas."""
    empresa = getattr(request, 'empresa', None)
    
    if not empresa:
        return render(request, 'clientes/lista_clientes.html', {
            'clientes_data': [], 'clientes_incompletos': [], 'total_clientes': 0,
            'total_ventas': 0, 'total_deudas': 0, 'clientes_con_deuda': 0
        })
        
    clientes_qs = clientes_de_empresa(empresa)
    # OPTIMIZACIÓN DE MEMORIA RAM: Traer máximo los últimos 20 para no saturar la vista web
    clientes_incompletos = clientes_qs.filter(ruc_cedula__startswith='SYS-').order_by('-creado_en')[:20]
    
    # 1. Agrupar métricas de ventas por cliente (Top compradores)
    ventas_agrupadas = Venta.objects.filter(empresa=empresa).exclude(estado='anulada').values('cliente_id').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    )
    metricas_ventas = {v['cliente_id']: {'total': v['total'] or 0, 'cantidad': v['cantidad']} for v in ventas_agrupadas}
    
    # OPTIMIZACIÓN: Delegar sumatoria de deudas a la Base de Datos
    deudas_agrupadas = Producto.objects.filter(empresa=empresa, estado='reservado', vendido_a__isnull=False).exclude(vendido_a='').values('vendido_a').annotate(total=Sum('precio'))
    deudas_dict = {d['vendido_a']: float(d['total'] or 0) for d in deudas_agrupadas}
        
    clientes_data = []
    total_deuda_general = 0
    total_ventas_general = 0
    
    for c in clientes_qs:
        v_data = metricas_ventas.get(c.id, {'total': 0, 'cantidad': 0})
        deuda = deudas_dict.get(c.nombre, 0)
        
        total_deuda_general += deuda
        total_ventas_general += v_data['total']
        
        clientes_data.append({
            'cliente': c,
            'total_comprado': v_data['total'],
            'cantidad_compras': v_data['cantidad'],
            'deuda': deuda
        })
        
    # Ordenar por total comprado (Ranking Top)
    clientes_data.sort(key=lambda x: x['total_comprado'], reverse=True)
    for i, data in enumerate(clientes_data):
        data['ranking'] = i + 1
        
    context = {
        'clientes_data': clientes_data,
        'clientes_incompletos': clientes_incompletos,
        'total_clientes': len(clientes_data),
        'total_ventas': total_ventas_general,
        'total_deudas': total_deuda_general,
        'clientes_con_deuda': sum(1 for c in clientes_data if c['deuda'] > 0)
    }
    return render(request, 'clientes/lista_clientes.html', context)


@login_required
@requiere_modulo('clientes', accion='crear')
def crear_cliente(request):
    """Vista para crear un nuevo cliente desde un template dedicado (sin modal)."""
    if request.method == 'POST':
        form = ClienteForm(request.POST)
        if form.is_valid():
            # La validación de unicidad ahora está en el form. Simplemente guardamos.
            cliente = form.save()
            messages.success(request, f'Cliente "{cliente.nombre}" creado exitosamente.')

            # Asociar la empresa (multitenancy)
            if hasattr(request, 'empresa') and request.empresa:
                cliente.empresas.add(request.empresa)
            
            return redirect('lista_clientes')
        else:
            form_errors_to_messages(request, form)
    else:
        form = ClienteForm()

    return render(request, 'clientes/crear_cliente.html', {'form': form})

@login_required
@requiere_modulo('clientes')
def detalle_cliente(request, cliente_id):
    """Muestra la información de un cliente específico y su historial de compras."""
    empresa = getattr(request, 'empresa', None)
    cliente = get_object_or_404(clientes_de_empresa(empresa), id=cliente_id)

    # Obtener todas las ventas del cliente
    ventas_cliente = Venta.objects.filter(cliente=cliente, empresa=empresa).exclude(estado='anulada')

    # Lógica de filtrado por fecha
    filtro = request.GET.get('filtro', 'todos')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    today = timezone.now().date()

    if filtro == 'hoy':
        ventas_filtradas = ventas_cliente.filter(fecha__date=today)
    elif filtro == 'semana':
        start_of_week = today - timedelta(days=today.weekday())
        ventas_filtradas = ventas_cliente.filter(fecha__date__gte=start_of_week)
    elif filtro == 'mes':
        ventas_filtradas = ventas_cliente.filter(fecha__year=today.year, fecha__month=today.month)
    elif filtro == 'año':
        ventas_filtradas = ventas_cliente.filter(fecha__year=today.year)
    elif filtro == 'personalizado' and fecha_inicio and fecha_fin:
        ventas_filtradas = ventas_cliente.filter(fecha__date__range=[fecha_inicio, fecha_fin])
    else:
        ventas_filtradas = ventas_cliente

    # Obtener los productos de las ventas filtradas
    # OPTIMIZACIÓN: Cargar tipo de producto pre-asociado
    detalles_venta = DetalleVenta.objects.filter(venta__in=ventas_filtradas).select_related('producto', 'producto__tipo_producto')
    productos_comprados = [d.producto for d in detalles_venta]

    context = {
        'cliente': cliente,
        'productos': productos_comprados,
        'total_gastado': ventas_filtradas.aggregate(total=Sum('total'))['total'] or 0,
        'cantidad_productos': len(productos_comprados),
        'filtro_actual': filtro,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
        'today': today,
    }
    return render(request, 'clientes/detalle_cliente.html', context)

@login_required
@requiere_modulo('clientes')
def editar_cliente(request, cliente_id):
    """Permite editar los datos de un cliente temporal o existente."""
    empresa = getattr(request, 'empresa', None)
    cliente = get_object_or_404(clientes_de_empresa(empresa), id=cliente_id)

    if request.method == 'POST':
        form = ClienteForm(request.POST, instance=cliente)
        if form.is_valid():
            # La validación de unicidad ahora está en el form.
            form.save()
            messages.success(request, f'La información de "{cliente.nombre}" ha sido actualizada.')
            return redirect('lista_clientes')
        else:
            form_errors_to_messages(request, form)
    else:
        form = ClienteForm(instance=cliente)

    context = {
        'form': form,
        'cliente': cliente
    }
    return render(request, 'clientes/editar_cliente.html', context)


@login_required
@requiere_modulo('clientes', accion='eliminar')
def eliminar_cliente(request, cliente_id):
    """Elimina un cliente de forma segura, preservando el historial si es necesario."""
    if request.method == 'POST':
        empresa = getattr(request, 'empresa', None)
        cliente = get_object_or_404(clientes_de_empresa(empresa), id=cliente_id)
        
        ventas_count = Venta.objects.filter(cliente=cliente, empresa=empresa).count()
        nombre = cliente.nombre
        
        # Desvincular de la empresa en lugar de un borrado forzado para proteger la contabilidad
        cliente.empresas.remove(empresa)
        
        # Intentar borrar el registro global si ya no pertenece a ninguna empresa y no tiene ventas
        if cliente.empresas.count() == 0 and not Venta.objects.filter(cliente=cliente).exists():
            cliente.delete()
            messages.success(request, f'El cliente "{nombre}" ha sido eliminado completamente del sistema.')
        else:
            if ventas_count > 0:
                messages.success(request, f'El cliente "{nombre}" fue ocultado del directorio. Su historial de {ventas_count} venta(s) se conserva para tus reportes.')
            else:
                messages.success(request, f'El cliente "{nombre}" ha sido removido de tu directorio.')
                
        return redirect('lista_clientes')
    return redirect('lista_clientes')


@login_required
@requiere_modulo('clientes')
def exportar_clientes_csv(request):
    """Exportación profesional de datos para el Tenant"""
    empresa = getattr(request, 'empresa', None)
    if not empresa:
        messages.error(request, "No tienes una empresa activa.")
        return redirect('lista_clientes')
        
    # Configurar la respuesta HTTP para descargar un archivo
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f'clientes_{empresa.slug}_{timezone.now().strftime("%Y%m%d")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Escribir CSV
    response.write(u'\ufeff'.encode('utf8'))  # Forzar codificación UTF-8
    writer = csv.writer(response)
    
    # --- TÍTULOS SUPERIORES CSV ---
    writer.writerow([f"DIRECTORIO DE CLIENTES - {empresa.nombre.upper()}"])
    writer.writerow([f"Fecha de exportación: {timezone.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])
    
    writer.writerow(['Nombre', 'RUC/Cédula', 'Teléfono', 'Email', 'Total Gastado', 'Fecha de Registro'])
    
    # OPTIMIZACIÓN: Calcular el total gastado de TODOS los clientes en 1 sola consulta
    clientes = clientes_de_empresa(empresa).annotate(
        total_gastado=Sum('ventas__total', filter=Q(ventas__empresa=empresa) & ~Q(ventas__estado='anulada'))
    )
    
    for c in clientes:
        total_gastado = c.total_gastado or 0
        writer.writerow([c.nombre, c.ruc_cedula, c.telefono, c.email, total_gastado, c.creado_en.strftime("%Y-%m-%d")])
        
    return response