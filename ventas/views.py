from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML
from django.urls import reverse
import json
import re
from productos.models import Producto
from .models import Venta, DetalleVenta, ConfiguracionFactura
from clientes.models import Cliente
from decimal import Decimal
import io
import os
from empresas.mixins import requiere_modulo


# ── VISTAS DE VENTAS ──────────────────────────────────────────────────────────

@login_required
@requiere_modulo('ventas')
def lista_ventas(request):
    """Lista todas las ventas/facturas con estadísticas"""

    ventas = Venta.objects.select_related('cliente').prefetch_related(
        'detalles__producto__tipo_producto'
    ).order_by('-fecha')

    # Estadísticas — usando agregaciones en lugar de sum en Python
    total_ventas = Venta.objects.aggregate(
        total=Sum('total')
    )['total'] or 0

    total_facturas_pagadas = Venta.objects.filter(
        detalles__producto__estado='vendido'
    ).distinct().count()

    clientes_con_deuda = Producto.objects.filter(
        estado='reservado',
        vendido_a__isnull=False
    ).exclude(vendido_a='').values('vendido_a').distinct().count()

    context = {
        'ventas': ventas,
        'total_ventas': total_ventas,
        'total_facturas': total_facturas_pagadas,
        'total_pendientes': clientes_con_deuda,
    }

    return render(request, 'ventas/lista_ventas.html', context)


@login_required
@requiere_modulo('ventas')
def lista_deudas(request):
    """Muestra todos los productos separados agrupados por cliente"""
    from collections import defaultdict

    productos_separados = Producto.objects.filter(
        estado='reservado',
        vendido_a__isnull=False
    ).exclude(vendido_a='').select_related('tipo_producto').order_by('vendido_a', '-creado_en')

    deudas_por_cliente = defaultdict(lambda: {'productos': [], 'total': 0, 'cantidad': 0})

    for producto in productos_separados:
        nombre = producto.vendido_a
        deudas_por_cliente[nombre]['productos'].append(producto)
        deudas_por_cliente[nombre]['total'] += producto.precio or 0
        deudas_por_cliente[nombre]['cantidad'] += 1

    deudas_list = [
        {'cliente': cliente, 'productos': info['productos'],
         'total': info['total'], 'cantidad': info['cantidad']}
        for cliente, info in deudas_por_cliente.items()
    ]
    deudas_list.sort(key=lambda x: x['total'], reverse=True)

    empresa_id = getattr(request, 'empresa', None).id if getattr(request, 'empresa', None) else 1
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    context = {
        'deudas': deudas_list,
        'total_deudas': sum(d['total'] for d in deudas_list),
        'total_clientes': len(deudas_list),
        'config': config,
    }

    return render(request, 'ventas/lista_deudas.html', context)


@login_required
@requiere_modulo('ventas')
def crear_venta(request):
    """Crea una nueva venta/factura"""

    if request.method == 'POST':
        
        # Interceptar petición AJAX del modal de Creación de Cliente
        if request.POST.get('action') == 'crear_cliente':
            nombre = request.POST.get('nombre', '').strip()
            ruc_cedula = request.POST.get('ruc_cedula', '').strip()
            email = request.POST.get('email', '').strip().lower()
            telefono = request.POST.get('telefono', '').strip()
            direccion = request.POST.get('direccion', '').strip()
            
            if not nombre or not ruc_cedula:
                return JsonResponse({'success': False, 'error': 'El Nombre y RUC/Cédula son obligatorios.'})

            ruc_cedula = re.sub(r'[^a-zA-Z0-9-]', '', ruc_cedula)
            
            cliente = Cliente.objects.filter(ruc_cedula=ruc_cedula).first()
            if cliente:
                if hasattr(request, 'empresa') and request.empresa:
                    cliente.empresas.add(request.empresa)
                return JsonResponse({
                    'success': True,
                    'cliente': {
                        'nombre': cliente.nombre,
                        'ruc_cedula': cliente.ruc_cedula,
                        'telefono': cliente.telefono,
                        'direccion': cliente.direccion,
                        'compras': cliente.cantidad_ventas()
                    },
                    'mensaje': 'Cliente con esa Cédula existente asociado a tu empresa exitosamente.'
                })

            if email and not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                return JsonResponse({'success': False, 'error': 'Formato de correo electrónico inválido.'})

            try:
                cliente = Cliente.objects.create(
                    nombre=nombre,
                    ruc_cedula=ruc_cedula,
                    email=email if email else None,
                    telefono=telefono,
                    direccion=direccion
                )
                if hasattr(request, 'empresa') and request.empresa:
                    cliente.empresas.add(request.empresa)
                    
                return JsonResponse({
                    'success': True,
                    'cliente': {
                        'nombre': cliente.nombre,
                        'ruc_cedula': cliente.ruc_cedula,
                        'telefono': cliente.telefono,
                        'direccion': cliente.direccion,
                        'compras': 0
                    },
                    'mensaje': '¡Cliente creado exitosamente!'
                })
            except Exception as e:
                return JsonResponse({'success': False, 'error': str(e)})

        cliente_id_o_nombre = request.POST.get('cliente_id', '').strip()
        nombre_cliente = request.POST.get('nombre_cliente', '').strip()

        if cliente_id_o_nombre:
            if cliente_id_o_nombre.isdigit():
                try:
                    cliente = Cliente.objects.get(pk=cliente_id_o_nombre)
                except Cliente.DoesNotExist:
                    cliente, _ = Cliente.objects.get_or_create(nombre=cliente_id_o_nombre)
            else:
                cliente, _ = Cliente.objects.get_or_create(nombre=cliente_id_o_nombre)
        elif nombre_cliente:
            cliente, _ = Cliente.objects.get_or_create(nombre=nombre_cliente)
        else:
            messages.error(request, 'Debes seleccionar o crear un cliente')
            return redirect('crear_venta')
            
        empresa = getattr(request, 'empresa', None)
        if empresa:
            cliente.empresas.add(empresa)

        venta = Venta.objects.create(
            cliente=cliente,
            descuento=Decimal(request.POST.get('descuento', 0)),
            envio=Decimal(request.POST.get('envio', 0)),
            otros_gastos=Decimal(request.POST.get('otros_gastos', 0)),
            descripcion_otros=request.POST.get('descripcion_otros', ''),
            notas=request.POST.get('notas', ''),
            metodo_pago=request.POST.get('metodo_pago', 'efectivo'),
            ruc_cliente=request.POST.get('ruc_cliente', ''),
        )

        for producto_id in request.POST.getlist('productos'):
            try:
                producto = Producto.objects.get(pk=producto_id)
                DetalleVenta.objects.create(
                    venta=venta,
                    producto=producto,
                    precio_unitario=producto.precio or 0
                )
                producto.estado = 'vendido'
                producto.vendido_a = cliente.nombre
                producto.save()
            except Producto.DoesNotExist:
                continue

        venta.calcular_total()

        # CORRECTO: numero_factura es campo, sin paréntesis
        messages.success(request, f'Venta {venta.numero_factura} creada exitosamente')
        return redirect(f"{reverse('detalle_venta', args=[venta.id])}?auto_print=1")

    # GET
    cliente_nombre_param = request.GET.get('cliente')

    clientes_sheets = Producto.objects.filter(
        vendido_a__isnull=False
    ).exclude(vendido_a='').values('vendido_a').distinct().order_by('vendido_a')

    clientes = []
    for c in clientes_sheets:
        try:
            cliente_bd = Cliente.objects.get(nombre=c['vendido_a'])
            clientes.append({
                'nombre': c['vendido_a'],
                'telefono': cliente_bd.telefono or '',
                'direccion': cliente_bd.direccion or '',
                'ruc_cedula': cliente_bd.ruc_cedula or '',
                'compras': cliente_bd.cantidad_ventas()
            })
        except Cliente.DoesNotExist:
            clientes.append({'nombre': c['vendido_a'], 'telefono': '', 'direccion': '', 'ruc_cedula': '', 'compras': 0})

    for cliente_bd in Cliente.objects.filter(empresas=getattr(request, 'empresa', None)).order_by('nombre'):
        if not any(c['nombre'] == cliente_bd.nombre for c in clientes):
            clientes.append({
                'nombre': cliente_bd.nombre,
                'telefono': cliente_bd.telefono or '',
                'direccion': cliente_bd.direccion or '',
                'ruc_cedula': cliente_bd.ruc_cedula or '',
                'compras': cliente_bd.cantidad_ventas()
            })

    clientes = sorted(clientes, key=lambda x: x['nombre'])

    productos_cliente_ids = []
    if cliente_nombre_param:
        productos_cliente_ids = list(
            Producto.objects.filter(vendido_a=cliente_nombre_param).values_list('id', flat=True)
        )

    productos_disponibles = Producto.objects.filter(
        estado='disponible'
    ).select_related('tipo_producto').order_by('-creado_en')[:200]

    if productos_cliente_ids:
        productos_del_cliente = Producto.objects.filter(
            id__in=productos_cliente_ids
        ).select_related('tipo_producto')
        productos_unicos = {p.id: p for p in list(productos_del_cliente) + list(productos_disponibles)}
        productos = list(productos_unicos.values())
    else:
        productos = list(productos_disponibles)

    context = {
        'clientes': clientes,
        'productos': productos,
        'productos_cliente_ids': productos_cliente_ids,
        'cliente_seleccionado': cliente_nombre_param,
        'clientes_json': json.dumps(clientes),
    }

    return render(request, 'ventas/crear_venta.html', context)


@login_required
@requiere_modulo('ventas')
def editar_venta(request, venta_id):
    """Edita una venta existente"""
    venta = get_object_or_404(Venta, pk=venta_id)
    
    # Filosofía SaaS: Permitimos la edición para máxima flexibilidad, 
    # solo informamos al usuario si la factura es externa para que sea consciente.
    if getattr(venta, 'origen', '') == 'sheets' and request.method == 'GET':
        messages.info(request, 'Esta factura se sincronizó desde Google Sheets. Puedes ajustarla libremente, pero los cambios solo se reflejarán en este sistema.')

    if request.method == 'POST':
        venta.descuento = Decimal(request.POST.get('descuento', 0))
        venta.envio = Decimal(request.POST.get('envio', 0))
        venta.otros_gastos = Decimal(request.POST.get('otros_gastos', 0))
        venta.descripcion_otros = request.POST.get('descripcion_otros', '')
        venta.notas = request.POST.get('notas', '')
        venta.metodo_pago = request.POST.get('metodo_pago', venta.metodo_pago)

        # La edición de facturas ahora solo permite ajustar gastos adicionales y descuentos.
        # El listado de productos de la factura se mantiene intacto.

        venta.calcular_total()
        venta.save()

        # CORRECTO: numero_factura es campo, sin paréntesis
        messages.success(request, f'Venta {venta.numero_factura} actualizada exitosamente')
        return redirect('detalle_venta', venta_id=venta.id)

    # GET
    context = {
        'venta': venta,
        'cliente': venta.cliente,
        'modo_edicion': True,
    }

    return render(request, 'ventas/crear_venta.html', context)


@login_required
@requiere_modulo('ventas')
def detalle_venta(request, venta_id):
    """Detalle de una venta"""
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related(
            'detalles__producto__tipo_producto'
        ),
        pk=venta_id
    )
    return render(request, 'ventas/detalle_venta.html', {'venta': venta})


# ── PDF CON WEASYPRINT (vía template HTML) ────────────────────────────────────

@login_required
@requiere_modulo('ventas')
def factura_pdf(request, venta_id):
    """
    Genera PDF de factura usando WeasyPrint + template HTML.
    Esta es la función principal que usa ventas/urls.py.
    """
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related('detalles__producto'),
        pk=venta_id
    )
    empresa_id = getattr(request, 'empresa', None).id if getattr(request, 'empresa', None) else 1
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    html_string = render_to_string('ventas/factura_pdf.html', {
        'venta': venta,
        'config': config,
    })

    # Si la petición incluye ?html=1, devolvemos el HTML crudo para que el navegador ejecute window.print()
    if request.GET.get('html') == '1':
        return HttpResponse(html_string)

    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    # CORRECTO: numero_factura es campo, sin paréntesis
    response['Content-Disposition'] = f'attachment; filename="factura-{venta.numero_factura}.pdf"'
    return response


# ── PDF CON REPORTLAB (comprobante de deuda) ──────────────────────────────────

@login_required
@requiere_modulo('ventas')
def generar_factura_pdf(request, venta_id):
    """
    Genera PDF de ticket térmico usando pdfkit (formato de 80mm) y template HTML.
    """
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related(
            'detalles__producto__tipo_producto'
        ),
        pk=venta_id
    )
    empresa_id = getattr(request, 'empresa', None).id if getattr(request, 'empresa', None) else 1
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    html_string = render_to_string('ventas/factura_pdf.html', {
        'venta': venta,
        'config': config,
    }, request=request)

    # Si la petición incluye ?html=1, devolvemos el HTML crudo para que el navegador ejecute window.print()
    if request.GET.get('html') == '1':
        return HttpResponse(html_string)

    # Usar WeasyPrint: nativo de Python, sin errores de Windows ni archivos vacíos
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket_{venta.numero_factura}.pdf"'
    return response


@login_required
@requiere_modulo('ventas')
def generar_comprobante_deuda_pdf(request, cliente_nombre):
    """Genera PDF de comprobante de deuda para un cliente usando pdfkit (A4)"""
    from datetime import datetime

    productos = Producto.objects.filter(
        estado='reservado',
        vendido_a=cliente_nombre
    ).select_related('tipo_producto').order_by('-creado_en')

    if not productos.exists():
        messages.error(request, f'No hay productos separados para {cliente_nombre}')
        return redirect('lista_deudas')

    empresa_id = getattr(request, 'empresa', None).id if getattr(request, 'empresa', None) else 1
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    try:
        cliente = Cliente.objects.get(nombre=cliente_nombre)
    except Cliente.DoesNotExist:
        cliente = None
        
    total_deuda = sum(p.precio for p in productos if p.precio)

    context = {
        'cliente_nombre': cliente_nombre,
        'cliente': cliente,
        'productos': productos,
        'total_deuda': total_deuda,
        'config': config,
        'fecha_actual': datetime.now(),
    }

    html_string = render_to_string('ventas/comprobante_deuda_pdf.html', context, request=request)

    # Usar WeasyPrint: nativo de Python, sin errores de Windows ni archivos vacíos
    pdf = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf()

    response = HttpResponse(pdf, content_type='application/pdf')
    nombre_archivo = cliente_nombre.replace(' ', '_').replace('/', '_')
    response['Content-Disposition'] = f'attachment; filename="comprobante_deuda_{nombre_archivo}.pdf"'
    return response


# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────

@login_required
@requiere_modulo('ventas')
def configuracion_facturas(request):
    """Configura logo, colores y datos de la empresa para las facturas"""
    # Obtención segura de la empresa (fallback a id=1 si el middleware no la inyectó)
    empresa = getattr(request, 'empresa', None)
    empresa_id = empresa.id if empresa else 1

    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    if request.method == 'POST':
        nuevo_nombre = request.POST.get('nombre_empresa', '').strip()
        
        # Usar el nombre del perfil como respaldo si no hay empresa asignada
        nombre_base = empresa.nombre if empresa else getattr(request.user.profile, 'nombre_negocio', 'Tiendita')
        
        if nuevo_nombre:
            config.nombre_empresa = nuevo_nombre
            # Desacoplarlo si lo escribió diferente al nombre global del perfil
            config.nombre_personalizado = (nuevo_nombre != nombre_base)
        else:
            config.nombre_empresa = nombre_base
            config.nombre_personalizado = False
            
        config.direccion_empresa = request.POST.get('direccion_empresa', '')
        config.telefono_empresa = request.POST.get('telefono_empresa', '')
        config.email_empresa = request.POST.get('email_empresa', '')
        config.mensaje_factura = request.POST.get('mensaje_factura', '')
        config.mensaje_deuda = request.POST.get('mensaje_deuda', '')
        config.color_principal = request.POST.get('color_principal', '#667eea')
        config.color_borde = request.POST.get('color_borde', '#667eea')
        config.color_texto = request.POST.get('color_texto', '#333333')

        config.save()
        messages.success(request, 'Configuración actualizada correctamente')
        return redirect('configuracion_facturas')

    return render(request, 'ventas/configuracion_facturas.html', {'config': config})