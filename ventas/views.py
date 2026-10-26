import json
import logging
import re
import uuid
from decimal import Decimal
from datetime import datetime
from collections import defaultdict

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from weasyprint import HTML
from django.urls import reverse
from django.views.decorators.http import require_GET
from productos.models import Producto, normalizar_busqueda
from .forms import PorcentajeIvaForm, leer_gastos
from .models import Venta, DetalleVenta, ConfiguracionFactura
from clientes.models import Cliente
from empresas.mixins import requiere_modulo

RUC_CONSUMIDOR_FINAL = '9999999999'
LIMITE_BUSQUEDA_PRODUCTOS = 20

logger = logging.getLogger(__name__)


# ── VISTAS DE VENTAS ──────────────────────────────────────────────────────────

@login_required
@requiere_modulo('ventas', accion='ver')
def lista_ventas(request):
    """Lista todas las ventas/facturas con estadísticas"""

    empresa = getattr(request, 'empresa', None)
    ventas = Venta.objects.filter(empresa=empresa).select_related('cliente').prefetch_related(
        'detalles__producto__tipo_producto'
    ).order_by('-fecha')

    # Estadísticas — usando agregaciones en lugar de sum en Python
    total_ventas = Venta.objects.filter(empresa=empresa).aggregate(
        total=Sum('total')
    )['total'] or 0

    total_facturas_pagadas = Venta.objects.filter(
        empresa=empresa,
        detalles__producto__estado='vendido'
    ).distinct().count()

    clientes_con_deuda = Producto.objects.filter(
        empresa=empresa,
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
@requiere_modulo('ventas', accion='ver')
def lista_deudas(request):
    """Muestra todos los productos separados agrupados por cliente"""
    empresa = getattr(request, 'empresa', None)
    productos_separados = Producto.objects.filter(
        empresa=empresa,
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

    empresa_id = empresa.id if empresa else None
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    context = {
        'deudas': deudas_list,
        'total_deudas': sum(d['total'] for d in deudas_list),
        'total_clientes': len(deudas_list),
        'config': config,
    }

    return render(request, 'ventas/lista_deudas.html', context)


class VentaRechazada(Exception):
    """La venta no se puede guardar; el mensaje (en español) se muestra al usuario."""


def _leer_token_envio(post):
    """UUID del envío, o None si falta o no es válido (la venta se acepta igual, pero se avisa)."""
    crudo = post.get('token_envio', '')
    try:
        return uuid.UUID(crudo)
    except ValueError:
        logger.warning('Venta enviada sin token_envio válido (valor recibido: %r)', crudo[:50])
        return None


def _venta_con_token(empresa, token):
    return Venta.objects.filter(empresa=empresa, token_envio=token).first()


def _venta_ya_registrada(request, venta):
    messages.info(request, 'Esta venta ya se registró.')
    return redirect('detalle_venta', venta_id=venta.id)


@transaction.atomic
def _registrar_venta(request, empresa, config, token):
    """Cliente, venta, detalles y stock en una sola transacción (S5).

    Si algo falla se revierte todo: ni venta, ni detalles, ni cliente nuevo, ni cambio de stock.
    Lanza VentaRechazada o ValidationError con el mensaje que ve el usuario.
    """
    factura_sin_datos = request.POST.get('factura_sin_datos') == '1'
    cliente_id_o_nombre = request.POST.get('cliente_id', '').strip()
    nombre_cliente = request.POST.get('nombre_cliente', '').strip()

    if factura_sin_datos:
        cliente_nombre = (config.texto_consumidor_final or 'CONSUMIDOR FINAL').strip() or 'CONSUMIDOR FINAL'
        cliente_ruc = (request.POST.get('ruc_cliente') or config.id_consumidor_final or '9999999999').strip() or '9999999999'
        # El RUC viene del POST: solo se reutiliza un cliente ya ligado a esta empresa.
        # El RUC genérico de consumidor final es el único que se comparte entre empresas.
        cliente = Cliente.objects.filter(ruc_cedula=cliente_ruc, empresas=empresa).first()
        if not cliente:
            existente = Cliente.objects.filter(ruc_cedula=cliente_ruc).first()
            if existente is None:
                cliente = Cliente.objects.create(
                    ruc_cedula=cliente_ruc, nombre=cliente_nombre,
                    telefono='', direccion='', email=None,
                )
            elif cliente_ruc == RUC_CONSUMIDOR_FINAL:
                cliente = existente
            else:
                raise VentaRechazada('Ya existe un cliente con ese RUC/Cédula en otra empresa y sus datos no están disponibles.')
        # El consumidor final es una sola fila para todas las empresas: nunca se renombra,
        # cada venta guarda su propio nombre. Los demás clientes solo se renombran si son
        # exclusivos de esta empresa.
        if (
            cliente.ruc_cedula != RUC_CONSUMIDOR_FINAL
            and cliente.nombre != cliente_nombre
            and cliente.empresas.exclude(pk=getattr(empresa, 'pk', None)).count() == 0
        ):
            cliente.nombre = cliente_nombre
            cliente.save(update_fields=['nombre'])
    elif cliente_id_o_nombre:
        if cliente_id_o_nombre.isdigit():
            try:
                cliente = Cliente.objects.get(
                    pk=cliente_id_o_nombre,
                    empresas=empresa,
                )
            except Cliente.DoesNotExist:
                raise VentaRechazada('El cliente seleccionado no pertenece a tu empresa.')
        else:
            cliente = Cliente.objects.filter(
                nombre=cliente_id_o_nombre,
                empresas=empresa,
            ).first()
            if not cliente:
                cliente = Cliente.objects.create(nombre=cliente_id_o_nombre)
    elif nombre_cliente:
        cliente = Cliente.objects.filter(
            nombre=nombre_cliente,
            empresas=empresa,
        ).first()
        if not cliente:
            cliente = Cliente.objects.create(nombre=nombre_cliente)
    else:
        raise VentaRechazada('Debes seleccionar o crear un cliente')

    if empresa:
        cliente.empresas.add(empresa)

    # Nombre con el que se factura: el de la empresa para el consumidor final, no el de la fila compartida.
    nombre_en_venta = cliente_nombre if factura_sin_datos else cliente.nombre

    productos_seleccionados = request.POST.getlist('productos')
    if not productos_seleccionados:
        raise VentaRechazada('Debes seleccionar al menos un producto para la venta.')

    # Se leen de nuevo con bloqueo de fila: el stock que se valida es el que se descuenta.
    ids = [int(i) for i in productos_seleccionados if i.isascii() and i.isdigit()]
    bloqueados = {
        p.id: p
        for p in Producto.objects.select_for_update().filter(pk__in=ids, empresa=empresa).order_by('pk')
    }
    productos_a_vender = [bloqueados[i] for i in ids if i in bloqueados]

    for producto in productos_a_vender:
        if producto.estado != 'disponible':
            raise VentaRechazada(f'El producto "{producto.nombre}" ya no está disponible.')

    if not productos_a_vender:
        raise VentaRechazada('Los productos seleccionados no están disponibles.')

    cantidades = {}
    for producto in productos_a_vender:
        cantidades[producto.id] = cantidades.get(producto.id, 0) + 1
    for producto_id, cantidad in cantidades.items():
        producto = bloqueados[producto_id]
        if producto.stock and cantidad > producto.stock:
            raise VentaRechazada(f'No puedes vender {cantidad} unidades de "{producto.nombre}" porque solo quedan {producto.stock} en stock.')

    gastos = leer_gastos(request.POST, sum(Decimal(p.precio or 0) for p in productos_a_vender))

    venta = Venta.objects.create(
        empresa=empresa,
        cliente=cliente,
        token_envio=token,
        **gastos,
        descripcion_otros=request.POST.get('descripcion_otros', ''),
        notas=request.POST.get('notas', ''),
        metodo_pago=request.POST.get('metodo_pago', 'efectivo'),
        nombre_cliente=nombre_en_venta,
        ruc_cliente=request.POST.get('ruc_cliente', '') or (config.id_consumidor_final if factura_sin_datos else ''),
    )

    for producto in productos_a_vender:
        DetalleVenta.objects.create(
            venta=venta,
            producto=producto,
            precio_unitario=producto.precio or 0
        )

        nuevo_stock = max(0, producto.stock - 1)
        producto.stock = nuevo_stock

        if nuevo_stock <= 0:
            producto.estado = 'vendido'
            producto.vendido_a = nombre_en_venta
        else:
            producto.estado = 'disponible'
            producto.vendido_a = ''

        producto.save(update_fields=['estado', 'stock', 'vendido_a', 'actualizado_en'])

    venta.calcular_total()
    return venta


@login_required
@requiere_modulo('ventas', accion='crear')
def crear_venta(request):
    """Crea una nueva venta/factura"""

    if request.method == 'POST':
        # Sin empresa no se crea nada: nunca caer en los datos de otra empresa.
        if not getattr(request, 'empresa', None):
            messages.error(request, 'Tu usuario no tiene una empresa asignada para registrar ventas.')
            return redirect('lista_ventas')

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

            cliente = Cliente.objects.filter(
                ruc_cedula=ruc_cedula,
                empresas=request.empresa,
            ).first()
            if cliente:
                return JsonResponse({
                    'success': True,
                    'cliente': {
                        'nombre': cliente.nombre,
                        'ruc_cedula': cliente.ruc_cedula,
                        'telefono': cliente.telefono,
                        'direccion': cliente.direccion,
                        'compras': Venta.objects.filter(cliente=cliente, empresa=request.empresa).count()
                    },
                    'mensaje': 'Cliente con esa Cédula existente asociado a tu empresa exitosamente.'
                })

            if Cliente.objects.filter(ruc_cedula=ruc_cedula).exists():
                return JsonResponse({
                    'success': False,
                    'error': 'Ya existe un cliente con esa Cédula en otra empresa y sus datos no están disponibles.'
                }, status=409)

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
            except IntegrityError:
                logger.exception('No se pudo crear el cliente (empresa %s)', request.empresa.id)
                return JsonResponse({'success': False, 'error': 'No se pudo crear el cliente. Intenta de nuevo.'})

        empresa = request.empresa
        config = ConfiguracionFactura.obtener_configuracion(empresa.id)

        # Un envío repetido (doble clic, reintento del navegador) no crea otra venta.
        token = _leer_token_envio(request.POST)
        if token:
            ya_registrada = _venta_con_token(empresa, token)
            if ya_registrada:
                return _venta_ya_registrada(request, ya_registrada)

        try:
            venta = _registrar_venta(request, empresa, config, token)
        except VentaRechazada as error:
            messages.error(request, str(error))
            return redirect('crear_venta')
        except ValidationError as error:
            messages.error(request, error.message)
            return redirect('crear_venta')
        except IntegrityError:
            # Dos envíos con el mismo token a la vez: gana el primero que confirma.
            ya_registrada = _venta_con_token(empresa, token) if token else None
            if ya_registrada is None:
                raise
            return _venta_ya_registrada(request, ya_registrada)

        messages.success(request, f'Venta {venta.numero_factura} creada exitosamente')
        return redirect('detalle_venta', venta_id=venta.id)

    # GET
    cliente_nombre_param = request.GET.get('cliente')

    # OPTIMIZACIÓN: Cargar clientes sin N+1 Queries y calcular compras masivamente
    empresa = getattr(request, 'empresa', None)
    config = ConfiguracionFactura.obtener_configuracion(empresa.id) if empresa else None
    # El consumidor final es compartido entre empresas: no se ofrece como cliente.
    clientes_bd = Cliente.objects.filter(empresas=empresa).exclude(ruc_cedula=RUC_CONSUMIDOR_FINAL).annotate(
        num_compras=Count('ventas', filter=Q(ventas__empresa=empresa) & ~Q(ventas__estado='anulada'))
    )
    
    clientes_dict = {}
    for c in clientes_bd:
        clientes_dict[c.nombre] = {
            'nombre': c.nombre,
            'telefono': c.telefono or '',
            'direccion': c.direccion or '',
            'ruc_cedula': c.ruc_cedula or '',
            'compras': c.num_compras
        }
        
    nombres_sheets = Producto.objects.filter(empresa=empresa, vendido_a__isnull=False).exclude(vendido_a='').values_list('vendido_a', flat=True).distinct()
    for nombre in nombres_sheets:
        if nombre not in clientes_dict:
            clientes_dict[nombre] = {'nombre': nombre, 'telefono': '', 'direccion': '', 'ruc_cedula': '', 'compras': 0}
            
    clientes = sorted(list(clientes_dict.values()), key=lambda x: x['nombre'])

    productos_cliente_ids = []
    if cliente_nombre_param:
        productos_cliente_ids = list(
            Producto.objects.filter(
                empresa=empresa,
                vendido_a=cliente_nombre_param,
            ).values_list('id', flat=True)
        )

    productos_disponibles = Producto.objects.filter(
        empresa=empresa,
        estado='disponible'
    ).select_related('tipo_producto').order_by('-creado_en')[:200]

    if productos_cliente_ids:
        productos_del_cliente = Producto.objects.filter(
            id__in=productos_cliente_ids,
            empresa=empresa,
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
        'token_envio': uuid.uuid4(),
        # El % que la pantalla usa para mostrar el IVA: el de la configuración de la empresa.
        'config': config,
        'porcentaje_iva': config.porcentaje_iva if config else Decimal('15.00'),
    }

    return render(request, 'ventas/crear_venta.html', context)


@login_required
@requiere_modulo('ventas', accion='crear')
@require_GET
def api_buscar_productos(request):
    """Productos que se pueden vender ahora, de la empresa del usuario (S7/S8).

    Sin texto devuelve los más recientes. Solo expone lo que la caja necesita: nunca costos.
    """
    productos = Producto.objects.filter(
        empresa=request.empresa, estado='disponible', stock__gt=0,
    )
    for termino in normalizar_busqueda(request.GET.get('q', '')).split():
        productos = productos.filter(texto_busqueda__icontains=termino)

    return JsonResponse([
        {
            'id': p.id,
            'nombre': p.nombre,
            'precio': f'{p.precio:.2f}',
            'stock': p.stock,
            'categoria': p.categoria,
        }
        for p in productos.order_by('-creado_en', '-id')[:LIMITE_BUSQUEDA_PRODUCTOS]
    ], safe=False)


@login_required
@requiere_modulo('ventas', accion='editar')
def editar_venta(request, venta_id):
    """Edita una venta existente"""
    venta = get_object_or_404(Venta, pk=venta_id, empresa=request.empresa)
    
    # Filosofía SaaS: Permitimos la edición para máxima flexibilidad, 
    # solo informamos al usuario si la factura es externa para que sea consciente.
    if getattr(venta, 'origen', '') == 'sheets' and request.method == 'GET':
        messages.info(request, 'Esta factura se sincronizó desde Google Sheets. Puedes ajustarla libremente, pero los cambios solo se reflejarán en este sistema.')

    if request.method == 'POST':
        try:
            with transaction.atomic():
                # La venta queda bloqueada mientras se recalcula: dos ediciones a la vez no se pisan.
                venta = get_object_or_404(Venta.objects.select_for_update(), pk=venta_id, empresa=request.empresa)
                gastos = leer_gastos(request.POST, venta.detalles.aggregate(s=Sum('precio_unitario'))['s'])

                venta.descuento = gastos['descuento']
                venta.envio = gastos['envio']
                venta.otros_gastos = gastos['otros_gastos']
                venta.descripcion_otros = request.POST.get('descripcion_otros', '')
                venta.notas = request.POST.get('notas', '')
                venta.metodo_pago = request.POST.get('metodo_pago', venta.metodo_pago)

                # La edición de facturas ahora solo permite ajustar gastos adicionales y descuentos.
                # El listado de productos de la factura se mantiene intacto.

                venta.calcular_total()
                venta.save()
        except ValidationError as error:
            messages.error(request, error.message)
            return redirect('editar_venta', venta_id=venta_id)

        # CORRECTO: numero_factura es campo, sin paréntesis
        messages.success(request, f'Venta {venta.numero_factura} actualizada exitosamente')
        return redirect('detalle_venta', venta_id=venta.id)

    # GET
    config = ConfiguracionFactura.obtener_configuracion(request.empresa.id)
    context = {
        'venta': venta,
        'cliente': venta.cliente,
        'modo_edicion': True,
        'config': config,
        # Una venta se muestra con el % con que se guardó; la configuración solo cubre las que no lo tienen.
        'porcentaje_iva': venta.porcentaje_iva if venta.porcentaje_iva is not None else config.porcentaje_iva,
    }

    return render(request, 'ventas/crear_venta.html', context)


@login_required
@requiere_modulo('ventas', accion='ver')
def detalle_venta(request, venta_id):
    """Detalle de una venta"""
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related(
            'detalles__producto__tipo_producto'
        ),
        pk=venta_id,
        empresa=request.empresa,
    )
    return render(request, 'ventas/detalle_venta.html', {'venta': venta})


# ── PDF CON WEASYPRINT (vía template HTML) ────────────────────────────────────

@login_required
@requiere_modulo('ventas', accion='ver')
def factura_pdf(request, venta_id):
    """
    Genera PDF de factura usando WeasyPrint + template HTML.
    Esta es la función principal que usa ventas/urls.py.
    """
    venta = get_object_or_404(
        Venta.objects.select_related('cliente').prefetch_related('detalles__producto'),
        pk=venta_id,
        empresa=request.empresa,
    )
    empresa_id = request.empresa.id
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
@requiere_modulo('ventas', accion='ver')
def generar_comprobante_deuda_pdf(request, cliente_nombre):
    """Genera PDF de comprobante de deuda para un cliente (A4)"""
    productos = Producto.objects.filter(
        empresa=request.empresa,
        estado='reservado',
        vendido_a=cliente_nombre
    ).select_related('tipo_producto').order_by('-creado_en')

    if not productos.exists():
        messages.error(request, f'No hay productos separados para {cliente_nombre}')
        return redirect('lista_deudas')

    empresa_id = request.empresa.id
    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    try:
        cliente = Cliente.objects.get(nombre=cliente_nombre, empresas=request.empresa)
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
@requiere_modulo('ventas', accion='editar')
def configuracion_facturas(request):
    """Configura logo, colores y datos de la empresa para las facturas"""
    empresa = request.empresa
    empresa_id = empresa.id

    config = ConfiguracionFactura.obtener_configuracion(empresa_id)

    if request.method == 'POST':
        datos = request.POST.copy()
        if 'porcentaje_iva' not in datos:
            datos['porcentaje_iva'] = config.porcentaje_iva
        form_iva = PorcentajeIvaForm(datos, instance=config)
        if not form_iva.is_valid():
            # Nada se guarda: el formulario vuelve a mostrarse con el error y lo que escribió el usuario.
            messages.error(request, form_iva.errors['porcentaje_iva'][0])
            return render(request, 'ventas/configuracion_facturas.html', {
                'config': config,
                'iva_ingresado': datos['porcentaje_iva'],
            })

        nuevo_nombre = request.POST.get('nombre_empresa', '').strip()

        nombre_base = empresa.nombre if empresa else getattr(request.user.profile, 'nombre_negocio', 'Tiendita')

        if nuevo_nombre:
            config.nombre_empresa = nuevo_nombre
            config.nombre_personalizado = (nuevo_nombre != nombre_base)
        else:
            config.nombre_empresa = nombre_base
            config.nombre_personalizado = False

        config.direccion_empresa = request.POST.get('direccion_empresa', '')
        config.telefono_empresa = request.POST.get('telefono_empresa', '')
        config.email_empresa = request.POST.get('email_empresa', '')
        config.mensaje_factura = request.POST.get('mensaje_factura', '')
        config.mensaje_deuda = request.POST.get('mensaje_deuda', '')
        config.porcentaje_iva = form_iva.cleaned_data['porcentaje_iva']
        config.texto_consumidor_final = request.POST.get('texto_consumidor_final', config.texto_consumidor_final or 'CONSUMIDOR FINAL')
        config.id_consumidor_final = request.POST.get('id_consumidor_final', config.id_consumidor_final or '9999999999')

        config.save()
        messages.success(request, 'Configuración actualizada correctamente')
        return redirect('configuracion_facturas')

    return render(request, 'ventas/configuracion_facturas.html', {'config': config})