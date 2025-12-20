from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count
from django.contrib import messages
from productos.models import Producto
from ventas.models import Cliente


@login_required
def top_clientes(request):
    """Vista para mostrar el ranking de mejores clientes desde vendido_a (Google Sheets dropdown)"""
    
    # Obtener clientes únicos del campo vendido_a de productos vendidos
    productos_vendidos = Producto.objects.filter(
        estado='vendido',
        vendido_a__isnull=False
    ).exclude(vendido_a='').values('vendido_a').annotate(
        total_compras=Sum('precio'),
        cantidad_productos=Count('id')
    ).order_by('-total_compras')
    
    # Convertir a lista de diccionarios con estructura esperada
    clientes = []
    for p in productos_vendidos:
        clientes.append({
            'nombre': p['vendido_a'],
            'total_compras': p['total_compras'],
            'cantidad_productos': p['cantidad_productos'],
        })
    
    # Calcular totales generales
    total_ventas = sum(c['total_compras'] for c in clientes)
    total_productos_vendidos = sum(c['cantidad_productos'] for c in clientes)
    
    context = {
        'clientes': clientes,
        'total_ventas': total_ventas,
        'total_ventas_count': len(clientes),
        'total_productos_vendidos': total_productos_vendidos,
    }
    
    return render(request, 'clientes/top_clientes.html', context)


@login_required
def detalle_cliente(request, cliente_nombre):
    """Vista para ver el detalle de compras de un cliente desde vendido_a field"""
    from datetime import datetime, timedelta
    from django.utils import timezone
    
    # Obtener filtros de fecha
    filtro = request.GET.get('filtro', 'todos')
    fecha_inicio = request.GET.get('fecha_inicio')
    fecha_fin = request.GET.get('fecha_fin')
    
    # Obtener productos vendidos a este cliente
    productos = Producto.objects.filter(
        vendido_a=cliente_nombre,
        estado='vendido'
    )
    
    # Aplicar filtros de fecha
    hoy = timezone.now().date()
    
    if filtro == 'hoy':
        productos = productos.filter(creado_en__date=hoy)
    elif filtro == 'semana':
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        productos = productos.filter(creado_en__date__gte=inicio_semana)
    elif filtro == 'mes':
        productos = productos.filter(
            creado_en__year=hoy.year,
            creado_en__month=hoy.month
        )
    elif filtro == 'año':
        productos = productos.filter(creado_en__year=hoy.year)
    elif filtro == 'personalizado' and fecha_inicio and fecha_fin:
        try:
            inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            productos = productos.filter(creado_en__date__range=[inicio, fin])
        except ValueError:
            messages.warning(request, 'Formato de fecha inválido')
    
    productos = productos.order_by('-creado_en')
    
    if not productos.exists() and filtro == 'todos':
        messages.error(request, f'No se encontraron productos para el cliente {cliente_nombre}')
        return redirect('top_clientes')
    
    # Calcular estadísticas
    total_gastado = productos.aggregate(total=Sum('precio'))['total'] or 0
    cantidad_productos = productos.count()
    
    # Intentar obtener información adicional del cliente desde la BD de ventas
    try:
        cliente_info = Cliente.objects.get(nombre=cliente_nombre)
    except Cliente.DoesNotExist:
        cliente_info = None
    
    context = {
        'nombre_cliente': cliente_nombre,
        'productos': productos,
        'total_gastado': total_gastado,
        'cantidad_productos': cantidad_productos,
        'cliente_info': cliente_info,
        'filtro_actual': filtro,
        'fecha_inicio': fecha_inicio,
        'fecha_fin': fecha_fin,
    }
    
    return render(request, 'clientes/detalle_cliente.html', context)


@login_required
def editar_info_cliente(request, cliente_nombre):
    """Vista para editar teléfono y dirección de un cliente"""
    
    if request.method == 'POST':
        telefono = request.POST.get('telefono', '').strip()
        direccion = request.POST.get('direccion', '').strip()
        email = request.POST.get('email', '').strip()
        notas = request.POST.get('notas', '').strip()
        
        # Crear o actualizar cliente en BD
        cliente, created = Cliente.objects.get_or_create(nombre=cliente_nombre)
        cliente.telefono = telefono
        cliente.direccion = direccion
        cliente.email = email
        cliente.notas = notas
        cliente.save()
        
        if created:
            messages.success(request, f'Información de {cliente_nombre} guardada exitosamente')
        else:
            messages.success(request, f'Información de {cliente_nombre} actualizada exitosamente')
        
        return redirect('detalle_cliente', cliente_nombre=cliente_nombre)
    
    # GET: Mostrar formulario
    try:
        cliente = Cliente.objects.get(nombre=cliente_nombre)
    except Cliente.DoesNotExist:
        cliente = None
    
    context = {
        'nombre_cliente': cliente_nombre,
        'cliente': cliente,
    }
    
    return render(request, 'clientes/editar_info_cliente.html', context)
