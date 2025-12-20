from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.http import HttpResponse
from django.contrib import messages
from django.conf import settings
import json
from productos.models import Producto
from .models import Cliente, Venta, DetalleVenta, ConfiguracionFactura
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from decimal import Decimal
import io
import os


@login_required
def lista_ventas(request):
    """Vista para listar todas las ventas/facturas"""
    
    # OPTIMIZACIÓN: select_related para cliente, prefetch_related para detalles
    ventas = Venta.objects.select_related('cliente').prefetch_related(
        'detalles__producto__tipo_prenda'
    ).order_by('-fecha')
    
    # Estadísticas
    from productos.models import Producto
    
    # Total de ventas: Sumar productos vendidos Y separados (todo lo facturado)
    productos_facturados = Producto.objects.filter(estado__in=['vendido', 'separado'])
    total_ventas = sum([p.precio or 0 for p in productos_facturados])
    
    # Facturas pagadas: Contar ventas que tienen productos vendidos
    total_facturas_pagadas = Venta.objects.filter(
        detalles__producto__estado='vendido'
    ).distinct().count()
    
    # Clientes con deuda: Contar clientes únicos que tienen productos en estado 'separado'
    clientes_con_deuda = Producto.objects.filter(
        estado='separado',
        vendido_a__isnull=False
    ).exclude(
        vendido_a=''
    ).values('vendido_a').distinct().count()
    
    context = {
        'ventas': ventas,
        'total_ventas': total_ventas,
        'total_facturas': total_facturas_pagadas,
        'total_pendientes': clientes_con_deuda,
    }
    
    return render(request, 'ventas/lista_ventas.html', context)


@login_required
def lista_deudas(request):
    """Vista para mostrar el detalle de todas las deudas (productos separados)"""
    from productos.models import Producto
    from collections import defaultdict
    
    # Obtener todos los productos separados con cliente asignado
    productos_separados = Producto.objects.filter(
        estado='separado',
        vendido_a__isnull=False
    ).exclude(
        vendido_a=''
    ).select_related('tipo_prenda').order_by('vendido_a', '-creado_en')
    
    # Agrupar por cliente
    deudas_por_cliente = defaultdict(lambda: {'productos': [], 'total': 0, 'cantidad': 0})
    
    for producto in productos_separados:
        cliente_nombre = producto.vendido_a
        deudas_por_cliente[cliente_nombre]['productos'].append(producto)
        deudas_por_cliente[cliente_nombre]['total'] += producto.precio or 0
        deudas_por_cliente[cliente_nombre]['cantidad'] += 1
    
    # Convertir a lista ordenada por total de deuda (mayor a menor)
    deudas_list = [
        {
            'cliente': cliente,
            'productos': info['productos'],
            'total': info['total'],
            'cantidad': info['cantidad']
        }
        for cliente, info in deudas_por_cliente.items()
    ]
    deudas_list.sort(key=lambda x: x['total'], reverse=True)
    
    # Calcular total general
    total_deudas = sum([d['total'] for d in deudas_list])
    
    context = {
        'deudas': deudas_list,
        'total_deudas': total_deudas,
        'total_clientes': len(deudas_list),
    }
    
    return render(request, 'ventas/lista_deudas.html', context)


@login_required
def crear_venta(request):
    """Vista para crear una nueva venta/factura"""
    
    if request.method == 'POST':
        # Obtener o crear cliente
        cliente_id_o_nombre = request.POST.get('cliente_id', '').strip()
        nombre_cliente = request.POST.get('nombre_cliente', '').strip()
        
        # Priorizar cliente seleccionado de la búsqueda
        if cliente_id_o_nombre:
            # Intentar obtener por ID primero (si es numérico)
            if cliente_id_o_nombre.isdigit():
                try:
                    cliente = Cliente.objects.get(pk=cliente_id_o_nombre)
                except Cliente.DoesNotExist:
                    cliente, created = Cliente.objects.get_or_create(nombre=cliente_id_o_nombre)
            else:
                # Es un nombre de cliente de Google Sheets, crear o obtener
                cliente, created = Cliente.objects.get_or_create(nombre=cliente_id_o_nombre)
        elif nombre_cliente:
            # Cliente nuevo escrito manualmente (solo para factura local)
            cliente, created = Cliente.objects.get_or_create(nombre=nombre_cliente)
        else:
            messages.error(request, 'Debes seleccionar o crear un cliente')
            return redirect('crear_venta')
        
        # Crear venta (solo se crea cuando hay pago)
        venta = Venta.objects.create(
            cliente=cliente,
            descuento=Decimal(request.POST.get('descuento', 0)),
            envio=Decimal(request.POST.get('envio', 0)),
            otros_gastos=Decimal(request.POST.get('otros_gastos', 0)),
            descripcion_otros=request.POST.get('descripcion_otros', ''),
            notas=request.POST.get('notas', '')
        )
        
        # Agregar productos
        productos_ids = request.POST.getlist('productos')
        for producto_id in productos_ids:
            try:
                producto = Producto.objects.get(pk=producto_id)
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    precio_unitario=producto.precio or 0
                )
                # Marcar producto como vendido
                producto.estado = 'vendido'
                producto.vendido_a = cliente.nombre
                producto.save()
            except Producto.DoesNotExist:
                continue
        
        # Calcular total
        venta.calcular_total()
        
        messages.success(request, f'Venta {venta.numero_factura()} creada exitosamente')
        return redirect('detalle_venta', venta_id=venta.id)
    
    # GET: Mostrar formulario
    # Obtener cliente seleccionado si viene de parámetro
    cliente_nombre_param = request.GET.get('cliente')
    
    # Obtener clientes únicos desde Google Sheets (campo vendido_a)
    clientes_sheets = Producto.objects.filter(
        vendido_a__isnull=False
    ).exclude(
        vendido_a=''
    ).values('vendido_a').distinct().order_by('vendido_a')
    
    # Convertir a formato esperado por el template con datos completos
    clientes = []
    for c in clientes_sheets:
        # Buscar si existe en BD para obtener teléfono/dirección
        try:
            cliente_bd = Cliente.objects.get(nombre=c['vendido_a'])
            clientes.append({
                'nombre': c['vendido_a'],
                'telefono': cliente_bd.telefono or '',
                'direccion': cliente_bd.direccion or ''
            })
        except Cliente.DoesNotExist:
            clientes.append({
                'nombre': c['vendido_a'],
                'telefono': '',
                'direccion': ''
            })
    
    # También incluir clientes de la base de datos (ventas) que no estén en Sheets
    clientes_bd = Cliente.objects.all().order_by('nombre')
    for cliente_bd in clientes_bd:
        # Agregar solo si no existe ya en la lista de Google Sheets
        if not any(c['nombre'] == cliente_bd.nombre for c in clientes):
            clientes.append({
                'nombre': cliente_bd.nombre,
                'telefono': cliente_bd.telefono or '',
                'direccion': cliente_bd.direccion or ''
            })
    
    # Ordenar alfabéticamente
    clientes = sorted(clientes, key=lambda x: x['nombre'])
    
    # Obtener productos del cliente si hay uno seleccionado
    productos_cliente_ids = []
    if cliente_nombre_param:
        # Productos que ya fueron vendidos/separados a este cliente
        productos_cliente = Producto.objects.filter(
            vendido_a=cliente_nombre_param
        ).values_list('id', flat=True)
        productos_cliente_ids = list(productos_cliente)
    
    # OPTIMIZACIÓN: Cargar solo campos necesarios de productos disponibles o del cliente
    productos_disponibles = Producto.objects.filter(
        estado='disponible'
    ).select_related('tipo_prenda').order_by('-creado_en')[:200]
    
    # Si hay productos del cliente, agregarlos a la lista
    if productos_cliente_ids:
        productos_del_cliente = Producto.objects.filter(
            id__in=productos_cliente_ids
        ).select_related('tipo_prenda')
        # Combinar productos disponibles con los del cliente
        productos_todos = list(productos_del_cliente) + list(productos_disponibles)
        # Eliminar duplicados
        productos_unicos = {p.id: p for p in productos_todos}
        productos = list(productos_unicos.values())
    else:
        productos = list(productos_disponibles)
    
    context = {
        'clientes': clientes,
        'productos': productos,
        'productos_cliente_ids': productos_cliente_ids,
        'cliente_seleccionado': cliente_nombre_param,
        'clientes_json': json.dumps(clientes),  # Para JavaScript
    }
    
    return render(request, 'ventas/crear_venta.html', context)


@login_required
def editar_venta(request, venta_id):
    """Vista para editar una venta existente"""
    venta = get_object_or_404(Venta, pk=venta_id)
    
    if request.method == 'POST':
        # Actualizar datos de la venta
        venta.descuento = Decimal(request.POST.get('descuento', 0))
        venta.envio = Decimal(request.POST.get('envio', 0))
        venta.otros_gastos = Decimal(request.POST.get('otros_gastos', 0))
        venta.descripcion_otros = request.POST.get('descripcion_otros', '')
        venta.notas = request.POST.get('notas', '')
        
        # Obtener productos actuales de la venta
        productos_actuales = set(venta.detalles.values_list('producto_id', flat=True))
        productos_nuevos = set(int(pid) for pid in request.POST.getlist('productos'))
        
        # Productos a eliminar (estaban pero ya no están seleccionados)
        productos_a_eliminar = productos_actuales - productos_nuevos
        for producto_id in productos_a_eliminar:
            DetalleVenta.objects.filter(venta=venta, producto_id=producto_id).delete()
            # Devolver producto a disponible
            producto = Producto.objects.get(pk=producto_id)
            producto.estado = 'disponible'
            producto.vendido_a = None
            producto.save()
        
        # Productos a agregar (nuevos que no estaban)
        productos_a_agregar = productos_nuevos - productos_actuales
        for producto_id in productos_a_agregar:
            try:
                producto = Producto.objects.get(pk=producto_id)
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    precio_unitario=producto.precio or 0
                )
                # Marcar producto como vendido
                producto.estado = 'vendido'
                producto.vendido_a = venta.cliente.nombre
                producto.save()
            except Producto.DoesNotExist:
                continue
        
        # Recalcular total
        venta.calcular_total()
        venta.save()
        
        messages.success(request, f'Venta {venta.numero_factura()} actualizada exitosamente')
        return redirect('detalle_venta', venta_id=venta.id)
    
    # GET: Mostrar formulario con datos actuales
    # Obtener productos de la venta
    productos_venta = venta.detalles.all().select_related('producto')
    productos_venta_ids = [d.producto.id for d in productos_venta]
    
    # Productos disponibles para agregar
    productos_disponibles = Producto.objects.filter(
        estado='disponible'
    ).select_related('tipo_prenda').order_by('-creado_en')[:200]
    
    # Combinar productos actuales de la venta con disponibles
    productos_opciones = list(productos_disponibles)
    for detalle in productos_venta:
        if detalle.producto not in productos_opciones:
            productos_opciones.insert(0, detalle.producto)
    
    context = {
        'venta': venta,
        'cliente': venta.cliente,
        'productos': productos_opciones,
        'productos_seleccionados': productos_venta_ids,
        'modo_edicion': True,
    }
    
    return render(request, 'ventas/crear_venta.html', context)


@login_required
def detalle_venta(request, venta_id):
    """Vista para ver detalle de una venta"""
    
    # OPTIMIZACIÓN: prefetch_related para cargar productos con una sola query adicional
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related(
            'detalles__producto__tipo_prenda'
        ),
        pk=venta_id
    )
    
    context = {
        'venta': venta,
    }
    
    return render(request, 'ventas/detalle_venta.html', context)


@login_required
def generar_factura_pdf(request, venta_id):
    """Genera PDF de factura con diseño profesional y personalizable"""
    
    # OPTIMIZACIÓN: Cargar venta con todas las relaciones necesarias
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related(
            'detalles__producto__tipo_prenda'
        ),
        pk=venta_id
    )
    config = ConfiguracionFactura.obtener_configuracion()
    
    # Crear buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                           leftMargin=2*cm, rightMargin=2*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Colores personalizados
    color_principal = colors.HexColor(config.color_principal)
    color_borde = colors.HexColor(config.color_borde)
    color_texto = colors.HexColor(config.color_texto)
    
    # Estilos personalizados
    style_titulo = ParagraphStyle(
        'Titulo',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=color_principal,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    style_normal = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=color_texto
    )
    
    # === ENCABEZADO CON LOGO Y INFO EMPRESA ===
    encabezado_data = []
    
    # Logo (si existe)
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, str(config.logo))
            logo = RLImage(logo_path, width=3*cm, height=3*cm)
            info_empresa = [
                Paragraph(f"<b>{config.nombre_empresa}</b>", style_titulo),
                Paragraph(config.direccion_empresa or '', style_normal),
                Paragraph(f"Tel: {config.telefono_empresa}" if config.telefono_empresa else '', style_normal),
                Paragraph(config.email_empresa or '', style_normal),
            ]
            encabezado_data = [[logo, info_empresa]]
        except:
            pass
    
    if not encabezado_data:
        # Sin logo
        elements.append(Paragraph(f"<b>{config.nombre_empresa}</b>", style_titulo))
        if config.direccion_empresa:
            elements.append(Paragraph(config.direccion_empresa, style_normal))
        elements.append(Spacer(1, 0.5*cm))
    else:
        table_encabezado = Table(encabezado_data, colWidths=[4*cm, 12*cm])
        table_encabezado.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Centrado vertical
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(table_encabezado)
        elements.append(Spacer(1, 0.5*cm))
    
    # === LÍNEA DECORATIVA CON COLOR PERSONALIZADO ===
    line_table = Table([['']], colWidths=[17*cm])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color_borde),
        ('LINEABOVE', (0, 0), (-1, -1), 4, color_borde),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # === INFO FACTURA Y CLIENTE ===
    # Construir info dinámicamente según datos disponibles
    info_data = [
        [Paragraph(f"<b>FACTURA: {venta.numero_factura()}</b>", style_normal),
         Paragraph(f"<b>Cliente:</b> {venta.cliente.nombre}", style_normal)],
    ]
    
    # Segunda fila: Fecha (siempre) y Teléfono (si existe)
    segunda_fila = [Paragraph(f"<b>Fecha:</b> {venta.fecha.strftime('%d/%m/%Y %H:%M:%S')}", style_normal)]
    if venta.cliente.telefono:
        segunda_fila.append(Paragraph(f"<b>Tel:</b> {venta.cliente.telefono}", style_normal))
    else:
        segunda_fila.append(Paragraph("", style_normal))
    info_data.append(segunda_fila)
    
    # Tercera fila: Dirección (solo si existe)
    if venta.cliente.direccion:
        info_data.append([
            Paragraph(f"<b>Dirección:</b> {venta.cliente.direccion}", style_normal),
            Paragraph("", style_normal)
        ])
    
    info_table = Table(info_data, colWidths=[8.5*cm, 8.5*cm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.8*cm))
    
    # === TABLA DE PRODUCTOS ===
    productos_data = [['#', 'Producto', 'Categoría', 'Talla', 'Precio']]
    
    for idx, detalle in enumerate(venta.detalles.all(), 1):
        producto = detalle.producto
        productos_data.append([
            str(idx),
            str(producto.tipo_prenda),
            producto.get_categoria_grupo_display(),
            producto.rango_edad or 'N/A',
            f"${detalle.precio_unitario:.2f}"
        ])
    
    productos_table = Table(productos_data, colWidths=[1*cm, 7*cm, 3.5*cm, 2.5*cm, 3*cm])
    productos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), color_principal),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # # centrado
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Producto a la izquierda
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Categoría centrada
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Talla centrada
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),  # Precio centrado
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Alineación vertical centrada
    ]))
    elements.append(productos_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # === TOTALES ===
    totales_data = [
        ['Subtotal:', f"${venta.subtotal:.2f}"],
    ]
    
    if venta.descuento > 0:
        totales_data.append(['Descuento:', f"-${venta.descuento:.2f}"])
    
    if venta.envio > 0:
        totales_data.append(['Envío:', f"${venta.envio:.2f}"])
    
    if venta.otros_gastos > 0:
        desc = venta.descripcion_otros or 'Otros gastos'
        totales_data.append([f'{desc}:', f"${venta.otros_gastos:.2f}"])
    
    totales_data.append([Paragraph('<b>TOTAL:</b>', style_normal), 
                         Paragraph(f'<b>${venta.total:.2f}</b>', style_normal)])
    
    totales_table = Table(totales_data, colWidths=[14*cm, 3*cm])
    totales_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, -1), (-1, -1), 2, color_principal),
        ('TOPPADDING', (0, -1), (-1, -1), 10),
        ('FONTSIZE', (0, -1), (-1, -1), 12),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(totales_table)
    
    # === MENSAJE PIE DE PÁGINA ===
    if config.mensaje_factura:
        elements.append(Spacer(1, 1*cm))
        elements.append(Paragraph(config.mensaje_factura, style_normal))
    
    # Generar PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="factura_{venta.numero_factura()}.pdf"'
    
    return response


@login_required
def generar_comprobante_deuda_pdf(request, cliente_nombre):
    """Generar PDF de comprobante de deuda para un cliente específico"""
    from productos.models import Producto
    from datetime import datetime
    
    # Obtener productos separados del cliente
    productos = Producto.objects.filter(
        estado='separado',
        vendido_a=cliente_nombre
    ).select_related('tipo_prenda').order_by('-creado_en')
    
    if not productos.exists():
        messages.error(request, f'No hay productos separados para el cliente {cliente_nombre}')
        return redirect('lista_deudas')
    
    # Obtener configuración
    config = ConfiguracionFactura.obtener_configuracion()
    
    # Intentar obtener información del cliente de la BD
    try:
        cliente = Cliente.objects.get(nombre=cliente_nombre)
        telefono_cliente = cliente.telefono or ''
        direccion_cliente = cliente.direccion or ''
    except Cliente.DoesNotExist:
        telefono_cliente = ''
        direccion_cliente = ''
    
    # Crear buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                           leftMargin=2*cm, rightMargin=2*cm)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Colores personalizados
    color_principal = colors.HexColor(config.color_principal)
    color_borde = colors.HexColor(config.color_borde)
    color_texto = colors.HexColor(config.color_texto)
    color_alerta = colors.HexColor('#764ba2')  # Morado del sistema para indicar deuda
    
    # Estilos personalizados
    style_titulo = ParagraphStyle(
        'Titulo',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=color_principal,
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    style_normal = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontSize=10,
        textColor=color_texto
    )
    
    # === ENCABEZADO CON LOGO Y INFO EMPRESA ===
    encabezado_data = []
    
    # Logo (si existe)
    if config.logo:
        try:
            logo_path = os.path.join(settings.MEDIA_ROOT, str(config.logo))
            logo = RLImage(logo_path, width=3*cm, height=3*cm)
            info_empresa = [
                Paragraph(f"<b>{config.nombre_empresa}</b>", style_titulo),
                Paragraph(config.direccion_empresa or '', style_normal),
                Paragraph(f"Tel: {config.telefono_empresa}" if config.telefono_empresa else '', style_normal),
                Paragraph(config.email_empresa or '', style_normal),
            ]
            encabezado_data = [[logo, info_empresa]]
        except:
            pass
    
    if not encabezado_data:
        # Sin logo
        elements.append(Paragraph(f"<b>{config.nombre_empresa}</b>", style_titulo))
        if config.direccion_empresa:
            elements.append(Paragraph(config.direccion_empresa, style_normal))
        elements.append(Spacer(1, 0.5*cm))
    else:
        table_encabezado = Table(encabezado_data, colWidths=[4*cm, 12*cm])
        table_encabezado.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(table_encabezado)
        elements.append(Spacer(1, 0.5*cm))
    
    # === LÍNEA DECORATIVA CON COLOR PERSONALIZADO ===
    line_table = Table([['']], colWidths=[17*cm])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color_borde),
        ('LINEABOVE', (0, 0), (-1, -1), 4, color_borde),
    ]))
    elements.append(line_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # === TÍTULO DEL DOCUMENTO ===
    style_comprobante = ParagraphStyle(
        'Comprobante',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=color_principal,
        spaceAfter=12,
        fontName='Helvetica-Bold',
        alignment=1  # Centrado
    )
    elements.append(Paragraph("<b>COMPROBANTE DE PRODUCTOS SEPARADOS</b>", style_comprobante))
    elements.append(Spacer(1, 0.3*cm))
    
    # === INFO CLIENTE Y FECHA ===
    info_data = [
        [Paragraph(f"<b>Cliente:</b> {cliente_nombre}", style_normal),
         Paragraph(f"<b>Fecha:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", style_normal)],
    ]
    
    # Segunda fila: Teléfono (si existe)
    if telefono_cliente:
        segunda_fila = [Paragraph(f"<b>Tel:</b> {telefono_cliente}", style_normal), Paragraph("", style_normal)]
        info_data.append(segunda_fila)
    
    # Tercera fila: Dirección (solo si existe)
    if direccion_cliente:
        info_data.append([
            Paragraph(f"<b>Dirección:</b> {direccion_cliente}", style_normal),
            Paragraph("", style_normal)
        ])
    
    info_table = Table(info_data, colWidths=[8.5*cm, 8.5*cm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.8*cm))
    
    # === TABLA DE PRODUCTOS SEPARADOS ===
    productos_data = [['#', 'Producto', 'Categoría', 'Talla', 'Fecha Separado', 'Precio']]
    
    total_deuda = 0
    for idx, producto in enumerate(productos, 1):
        productos_data.append([
            str(idx),
            str(producto.tipo_prenda),
            producto.get_categoria_grupo_display(),
            producto.rango_edad or 'N/A',
            producto.creado_en.strftime('%d/%m/%Y'),
            f"${producto.precio:.2f}"
        ])
        total_deuda += producto.precio or 0
    
    productos_table = Table(productos_data, colWidths=[1*cm, 5*cm, 2.8*cm, 1.8*cm, 3.2*cm, 3.2*cm])
    productos_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), color_principal),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),  # # centrado
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),    # Producto a la izquierda
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),  # Categoría centrada
        ('ALIGN', (3, 0), (3, -1), 'CENTER'),  # Talla centrada
        ('ALIGN', (4, 0), (4, -1), 'CENTER'),  # Fecha centrada
        ('ALIGN', (5, 0), (5, -1), 'CENTER'),  # Precio centrado
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(productos_table)
    elements.append(Spacer(1, 0.5*cm))
    
    # === TOTAL DE DEUDA ===
    style_total = ParagraphStyle(
        'Total',
        parent=styles['Normal'],
        fontSize=14,
        fontName='Helvetica-Bold',
        textColor=color_alerta
    )
    
    totales_data = [
        [Paragraph('<b>TOTAL A PAGAR:</b>', style_total), 
         Paragraph(f'<b>${total_deuda:.2f}</b>', style_total)]
    ]
    
    totales_table = Table(totales_data, colWidths=[14*cm, 3*cm])
    totales_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('LINEABOVE', (0, 0), (-1, 0), 2, color_alerta),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8f9ff')),  # Fondo lavanda
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elements.append(totales_table)
    
    # === NOTA IMPORTANTE ===
    elements.append(Spacer(1, 0.8*cm))
    style_nota = ParagraphStyle(
        'Nota',
        parent=styles['Normal'],
        fontSize=9,
        textColor=color_texto,
        alignment=1  # Centrado
    )
  
    # === MENSAJE PIE DE PÁGINA ===
    if config.mensaje_factura:
        elements.append(Spacer(1, 0.5*cm))
        elements.append(Paragraph(config.mensaje_factura, style_normal))
    
    # Generar PDF
    doc.build(elements)
    buffer.seek(0)
    
    response = HttpResponse(buffer, content_type='application/pdf')
    # Sanitizar nombre del cliente para el nombre del archivo
    nombre_archivo = cliente_nombre.replace(' ', '_').replace('/', '_')
    response['Content-Disposition'] = f'attachment; filename="comprobante_deuda_{nombre_archivo}.pdf"'
    
    return response


@login_required
def configuracion_facturas(request):
    """Vista para configurar logo y colores de facturas"""
    
    config = ConfiguracionFactura.obtener_configuracion()
    
    if request.method == 'POST':
        # Actualizar datos de empresa
        config.nombre_empresa = request.POST.get('nombre_empresa', 'Tiendita')
        config.direccion_empresa = request.POST.get('direccion_empresa', '')
        config.telefono_empresa = request.POST.get('telefono_empresa', '')
        config.email_empresa = request.POST.get('email_empresa', '')
        config.mensaje_factura = request.POST.get('mensaje_factura', '')
        
        # Actualizar colores
        config.color_principal = request.POST.get('color_principal', '#667eea')
        config.color_borde = request.POST.get('color_borde', '#667eea')
        config.color_texto = request.POST.get('color_texto', '#333333')
        
        # Subir logo si existe
        if 'logo' in request.FILES:
            config.logo = request.FILES['logo']
        
        config.save()
        messages.success(request, 'Configuración actualizada correctamente')
        return redirect('configuracion_facturas')
    
    context = {
        'config': config,
    }
    
    return render(request, 'ventas/configuracion_facturas.html', context)
