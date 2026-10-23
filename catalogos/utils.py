"""
Helpers reutilizables para el generador de catálogos.

lógica reutilizable: filtros, enriquecimiento de
productos, agrupación y generación del PDF. Todos los campos que se leen del
modelo Producto están verificados contra productos/models.py real:

- destacado          -> BooleanField real 
- precio_oferta      -> DecimalField real 
- marca              -> el modelo NO tiene 'proveedor' separado, es el mismo
                         campo ("Marca / Proveedor" en el propio modelo)
- margen()/porcentaje_margen() -> ya existen como métodos del modelo, se
                         reutilizan en vez de reimplementar el cálculo
- codigo / sku       -> el modelo NO tiene estos campos dedicados; si se
                         necesitan, deben guardarse dentro del JSONField
                         'atributos' (se documenta explícitamente abajo)
"""

import io
import json
import os
from collections import OrderedDict
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4, letter, legal, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from pypdf import PdfReader, PdfWriter

from productos.models import Producto

CATALOGO_DEFAULT_CONFIG = {
    'plantilla': 'moderna',
    'page_size': 'A4',
    'orientation': 'vertical',
    'columnas': 3,
    'productos_por_pagina': 6,
    'agrupar_por': 'categoria',
    'ordenar_por': 'categoria',
    'repetir_encabezado': True,
    'numerar_paginas': True,
    'moneda': '$',
    'mostrar_codigo': True,
    'mostrar_sku': True,
    'mostrar_categoria': True,
    'mostrar_marca': True,
    'mostrar_descripcion': True,
    'mostrar_stock': True,
    'mostrar_precio_anterior': True,
    'mostrar_descuento': True,
    'mostrar_porcentaje_descuento': True,
    'modo_precios': 'ambos',
    'fuente_titulo': 'Helvetica-Bold',
    'fuente_texto': 'Helvetica',
    'tamano_titulo': 18,
    'tamano_precio': 24,
    'tamano_descripcion': 10,
    'color_encabezado': '#0f172a',
    'color_categoria': '#2563eb',
    'color_etiqueta': '#1d4ed8',
    'color_precio': '#15803d',
    'color_fondo': '#f8fafc',
    'color_tarjeta': '#ffffff',
    'color_texto': '#334155',
    'color_borde': '#dbeafe',
    'margen': 0.75,
    'espaciado_productos': 0.5,
    'espaciado_categorias': 1.0,
    'separacion_columnas': 0.4,
    'ajustar_imagen_automaticamente': True,
    'mantener_proporcion': True,
    'recortar_imagen': False,
    'centrar_imagen': True,
    'fondo_blanco_auto': True,
    'bordes_redondeados': True,
    'sombras': True,
    'nombre_negocio': 'Mi Tienda',
    'slogan': 'Productos de Excelente Calidad',
    'direccion': '',
    'telefonos': '',
    'correo': '',
    'sitio_web': '',
    'redes_sociales': '',
    'qr_texto': '',
    'fecha_emision': '',
    'pie_pagina': '',
}

PAGE_SIZE_MAP = {
    'A4': A4,
    'Carta': letter,
    'Oficio': legal,
}


CATALOGO_PLANTILLAS = {
    'minimalista': {
        'label': 'Minimalista',
        'descripcion': 'Blanco y negro, mucho espacio en blanco, tipografía limpia.',
        'columnas': 3, 'productos_por_pagina': 6,
        'color_encabezado': '#111111', 'color_categoria': '#111111', 'color_etiqueta': '#111111',
        'color_precio': '#111111', 'color_fondo': '#ffffff', 'color_tarjeta': '#ffffff',
        'color_texto': '#333333', 'color_borde': '#e5e5e5',
        'bordes_redondeados': False, 'sombras': False,
        'fuente_titulo': 'Helvetica-Bold', 'fuente_texto': 'Helvetica',
    },
    'comercial': {
        'label': 'Comercial',
        'descripcion': 'Colores vivos, precios grandes, ideal para ventas directas.',
        'columnas': 3, 'productos_por_pagina': 6,
        'color_encabezado': '#dc2626', 'color_categoria': '#dc2626', 'color_etiqueta': '#dc2626',
        'color_precio': '#dc2626', 'color_fondo': '#fff7ed', 'color_tarjeta': '#ffffff',
        'color_texto': '#1f2937', 'color_borde': '#fecaca',
        'tamano_precio': 26, 'bordes_redondeados': True, 'sombras': True,
    },
    'moderna': {
        'label': 'Moderna',
        'descripcion': 'Paleta índigo/azul, tarjetas con sombra, look tipo SaaS.',
        'columnas': 3, 'productos_por_pagina': 6,
        'color_encabezado': '#0f172a', 'color_categoria': '#2563eb', 'color_etiqueta': '#1d4ed8',
        'color_precio': '#15803d', 'color_fondo': '#f8fafc', 'color_tarjeta': '#ffffff',
        'color_texto': '#334155', 'color_borde': '#dbeafe',
        'bordes_redondeados': True, 'sombras': True,
    },
    'supermercado': {
        'label': 'Supermercado',
        'descripcion': 'Muchos productos por página, precios muy visibles, poco texto.',
        'columnas': 4, 'productos_por_pagina': 12,
        'color_encabezado': '#16a34a', 'color_categoria': '#16a34a', 'color_etiqueta': '#16a34a',
        'color_precio': '#dc2626', 'color_fondo': '#ffffff', 'color_tarjeta': '#ffffff',
        'color_texto': '#1f2937', 'color_borde': '#d1fae5',
        'mostrar_descripcion': False, 'tamano_precio': 22,
    },
    'mayorista': {
        'label': 'Mayorista',
        'descripcion': 'Prioriza código, SKU y stock; pensado para pedidos por volumen.',
        'columnas': 4, 'productos_por_pagina': 8,
        'color_encabezado': '#1e293b', 'color_categoria': '#334155', 'color_etiqueta': '#334155',
        'color_precio': '#0f172a', 'color_fondo': '#f1f5f9', 'color_tarjeta': '#ffffff',
        'color_texto': '#334155', 'color_borde': '#cbd5e1',
        'mostrar_codigo': True, 'mostrar_sku': True, 'mostrar_stock': True,
        'mostrar_descripcion': False,
    },
    'catalogo_ejecutivo': {
        'label': 'Catálogo Ejecutivo',
        'descripcion': 'Pocas columnas, imágenes grandes, texto elegante.',
        'columnas': 2, 'productos_por_pagina': 4,
        'color_encabezado': '#1a1a2e', 'color_categoria': '#c9a15a', 'color_etiqueta': '#c9a15a',
        'color_precio': '#1a1a2e', 'color_fondo': '#faf9f6', 'color_tarjeta': '#ffffff',
        'color_texto': '#2c2c2c', 'color_borde': '#e5ded0',
        'tamano_titulo': 20, 'tamano_precio': 26,
    },
    'catalogo_corporativo': {
        'label': 'Catálogo Corporativo',
        'descripcion': 'Colores neutros, foco en marca y datos técnicos.',
        'columnas': 3, 'productos_por_pagina': 6,
        'color_encabezado': '#0b3d91', 'color_categoria': '#0b3d91', 'color_etiqueta': '#0b3d91',
        'color_precio': '#111827', 'color_fondo': '#ffffff', 'color_tarjeta': '#f9fafb',
        'color_texto': '#374151', 'color_borde': '#e5e7eb',
        'mostrar_marca': True, 'mostrar_codigo': True,
    },
    'promociones': {
        'label': 'Promociones',
        'descripcion': 'Resalta ofertas: descuentos y precio anterior siempre visibles.',
        'columnas': 3, 'productos_por_pagina': 6,
        'color_encabezado': '#be123c', 'color_categoria': '#be123c', 'color_etiqueta': '#be123c',
        'color_precio': '#be123c', 'color_fondo': '#fff1f2', 'color_tarjeta': '#ffffff',
        'color_texto': '#1f2937', 'color_borde': '#fecdd3',
        'mostrar_precio_anterior': True, 'mostrar_descuento': True, 'mostrar_porcentaje_descuento': True,
        'tamano_precio': 26,
    },
}


def aplicar_plantilla(config, plantilla_id):
    """Aplica los overrides de una plantilla prediseñada sobre una config existente."""
    preset = CATALOGO_PLANTILLAS.get(plantilla_id)
    if not preset:
        return config
    nueva_config = dict(config)
    for clave, valor in preset.items():
        if clave in ('label', 'descripcion'):
            continue
        nueva_config[clave] = valor
    nueva_config['plantilla'] = plantilla_id
    return nueva_config


# ─────────────────────────────────────────────────────────────────────────
# Configuración / assets en disco
# ─────────────────────────────────────────────────────────────────────────

def catalogo_dir(empresa_id):
    return os.path.join(settings.MEDIA_ROOT, f'catalogo_tenant_{empresa_id}')


def config_file(catalogo_dir_path):
    return os.path.join(catalogo_dir_path, 'config_diseno.json')


def load_catalogo_config(catalogo_dir_path):
    config = dict(CATALOGO_DEFAULT_CONFIG)
    archivo = config_file(catalogo_dir_path)
    if os.path.exists(archivo):
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
        except Exception:
            pass
    return config


def save_catalogo_config(catalogo_dir_path, config):
    os.makedirs(catalogo_dir_path, exist_ok=True)
    with open(config_file(catalogo_dir_path), 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def find_asset(catalogo_dir_path, base_name, exts):
    for ext in exts:
        path = os.path.join(catalogo_dir_path, f'{base_name}.{ext}')
        if os.path.exists(path):
            return path, ext
    return None, None


def asset_url(empresa_id, base_name, ext):
    return f"{settings.MEDIA_URL}catalogo_tenant_{empresa_id}/{base_name}.{ext}"


def parse_decimal(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '.').replace('$', '').strip())
    except ValueError:
        return None


def csv_ids(value):
    if not value:
        return []
    result = []
    for part in str(value).split(','):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result


def save_uploaded_asset(request, catalogo_dir_path, field_name, base_name, allowed_exts):
    archivo = request.FILES[field_name]
    extension = archivo.name.split('.')[-1].lower()
    if extension == 'jpeg':
        extension = 'jpg'
    if extension not in allowed_exts:
        return False, f"Solo se permiten archivos {', '.join(ext.upper() for ext in allowed_exts)}"

    os.makedirs(catalogo_dir_path, exist_ok=True)
    for ext in allowed_exts:
        path = os.path.join(catalogo_dir_path, f'{base_name}.{ext}')
        if os.path.exists(path):
            os.remove(path)

    destination_path = os.path.join(catalogo_dir_path, f'{base_name}.{extension}')
    with open(destination_path, 'wb+') as destino:
        for chunk in archivo.chunks():
            destino.write(chunk)
    return True, destination_path


# ─────────────────────────────────────────────────────────────────────────
# Filtros / agrupación / orden — mapeados contra CatalogoFilterForm real
# ─────────────────────────────────────────────────────────────────────────

def apply_catalog_filters(request, form=None, include_excluded=False):
    """
    Filtra el queryset de productos a nivel de base de datos.

    Todo lo que SÍ es un campo real del modelo se filtra aquí (rápido, en
    SQL). Lo que depende de datos calculados en Python (ventas, rentabilidad)
    se deja para apply_special_filters, después de enrich_and_sort_products.
    """
    queryset = Producto.objects.filter(empresa=request.empresa).select_related('tipo_producto')
    if not include_excluded:
        queryset = queryset.exclude(estado__in=['vendido', 'reservado'])

    data = form.cleaned_data if form and form.is_valid() else {}

    categorias = data.get('categorias')
    if categorias:
        queryset = queryset.filter(categoria__in=categorias)

    marcas = data.get('marcas')
    if marcas:
        queryset = queryset.filter(marca__in=marcas)

    tipos_producto = data.get('tipos_producto')
    if tipos_producto:
        queryset = queryset.filter(tipo_producto__in=tipos_producto)

    precio_min = parse_decimal(data.get('precio_min'))
    precio_max = parse_decimal(data.get('precio_max'))
    if precio_min is not None:
        queryset = queryset.filter(precio__gte=precio_min)
    if precio_max is not None:
        queryset = queryset.filter(precio__lte=precio_max)

    busqueda = data.get('busqueda')
    if busqueda:
        queryset = queryset.filter(
            Q(nombre__icontains=busqueda)
            | Q(descripcion__icontains=busqueda)
            | Q(marca__icontains=busqueda)
            | Q(categoria__icontains=busqueda)
            | Q(variante__icontains=busqueda)
        )

    if data.get('activos'):
        queryset = queryset.filter(estado='disponible')
    if data.get('con_stock'):
        queryset = queryset.filter(stock__gt=0)
    if data.get('sin_stock'):
        queryset = queryset.filter(stock=0)
    if data.get('destacados'):
        queryset = queryset.filter(destacado=True)
    if data.get('en_oferta'):
        queryset = queryset.filter(precio_oferta__isnull=False)
    if data.get('nuevos'):
        queryset = queryset.filter(creado_en__gte=timezone.now() - timedelta(days=30))

    seleccion = csv_ids(data.get('seleccion'))
    if seleccion:
        queryset = queryset.filter(id__in=seleccion)
    excluir = csv_ids(data.get('excluir'))
    if excluir:
        queryset = queryset.exclude(id__in=excluir)

    return queryset


def enrich_product(producto, sales_by_product):
    """
    Agrega al objeto producto los atributos calculados que necesita el
    catálogo (ventas, rentabilidad, oferta, badges), usando siempre campos
    reales del modelo como fuente de verdad.
    """
    producto.ventas_count = int(sales_by_product.get(producto.id, 0))

    # Rentabilidad: reutiliza los métodos que ya existen en el modelo,
    # en vez de reimplementar el cálculo aquí.
    producto.utilidad = producto.margen()
    producto.porcentaje_utilidad = producto.porcentaje_margen()

    producto.es_nuevo = producto.creado_en >= timezone.now() - timedelta(days=30)

    # Antes esto se leía de 'atributos' (casi siempre vacío). El modelo ya
    # tiene 'destacado' como BooleanField real.
    producto.es_destacado = bool(producto.destacado)

    # Antes 'oferta' se buscaba en atributos. El modelo ya tiene
    # 'precio_oferta' como campo real: si existe y es menor al precio
    # normal, es una oferta de verdad.
    tiene_oferta = (
        producto.precio_oferta is not None
        and producto.precio is not None
        and float(producto.precio_oferta) < float(producto.precio)
    )
    producto.es_oferta = tiene_oferta
    if tiene_oferta:
        producto.precio_anterior = producto.precio
        producto.descuento_catalogo = float(producto.precio) - float(producto.precio_oferta)
        producto.porcentaje_descuento = round(
            (producto.descuento_catalogo / float(producto.precio)) * 100, 1
        )
    else:
        producto.precio_anterior = None
        producto.descuento_catalogo = None
        producto.porcentaje_descuento = None

    # El modelo no tiene 'codigo' ni 'sku' como campos propios. Si el
    # negocio los necesita, deben guardarse dentro de 'atributos' (ej.
    # {"codigo": "PRD-001", "sku": "ABC123"}). Mientras tanto, se usa el ID
    # interno como código de respaldo para que el catálogo nunca quede sin
    # identificador.
    producto.codigo_catalogo = producto.atributos.get('codigo') or producto.id
    producto.sku_catalogo = producto.atributos.get('sku') or ''

    return producto


def enrich_and_sort_products(request, productos, sort_by):
    from ventas.models import DetalleVenta

    sales_by_product = dict(
        DetalleVenta.objects.filter(venta__empresa=request.empresa, venta__estado='completada')
        .values('producto_id')
        .annotate(total=Count('id'))
        .values_list('producto_id', 'total')
    )
    productos = [enrich_product(producto, sales_by_product) for producto in productos]

    sort_keys = {
        'categoria': lambda p: ((p.categoria or '').lower(), (p.nombre or '').lower(), p.id),
        'nombre': lambda p: ((p.nombre or '').lower(), p.id),
        '-nombre': lambda p: ((p.nombre or '').lower(), p.id),
        'precio': lambda p: (p.precio is None, float(p.precio or 0), p.id),
        '-precio': lambda p: (p.precio is None, -(float(p.precio or 0)), p.id),
        'marca': lambda p: ((p.marca or '').lower(), (p.nombre or '').lower(), p.id),
        '-creado_en': lambda p: (-p.creado_en.timestamp(), p.id),
        'creado_en': lambda p: (p.creado_en.timestamp(), p.id),
        'mas_vendidos': lambda p: (-p.ventas_count, (p.nombre or '').lower(), p.id),
        'rentabilidad': lambda p: (p.utilidad is None, -(p.utilidad or 0), p.id),
    }
    key = sort_keys.get(sort_by, sort_keys['categoria'])
    reverse = sort_by == '-nombre'
    return sorted(productos, key=key, reverse=reverse)


def apply_special_filters(productos, data):
    """
    Filtros que solo se pueden aplicar después de enriquecer los productos
    en Python (dependen de datos calculados: ventas, margen).
    """
    if data.get('mas_vendidos'):
        productos = [p for p in productos if p.ventas_count > 0]
    if data.get('mayor_rentabilidad'):
        productos = [p for p in productos if p.utilidad is not None and p.utilidad > 0]
        productos = sorted(productos, key=lambda p: -(p.utilidad or 0))
    return productos


def product_group_label(producto, agrupar_por):
    if agrupar_por in ('marca', 'proveedor'):
        # El modelo no separa proveedor de marca; 'proveedor' se mantiene
        # como alias por compatibilidad con configuraciones guardadas antes.
        return producto.marca or producto.atributos.get('proveedor') or 'Sin marca/proveedor'
    if agrupar_por == 'tipo_producto':
        return str(producto.tipo_producto) if producto.tipo_producto else 'Sin tipo'
    if agrupar_por == 'subcategoria':
        return producto.variante or producto.atributos.get('subcategoria') or 'Sin subcategoría'
    return producto.categoria or 'Sin categoría'


def group_products(productos, agrupar_por):
    if not agrupar_por:
        return [('Todos los productos', productos)]
    grupos = OrderedDict()
    for producto in productos:
        label = product_group_label(producto, agrupar_por)
        grupos.setdefault(label, []).append(producto)
    return list(grupos.items())


def page_size(config):
    base = PAGE_SIZE_MAP.get(config.get('page_size', 'A4'), A4)
    return landscape(base) if config.get('orientation', 'vertical') == 'horizontal' else base


# ─────────────────────────────────────────────────────────────────────────
# Generación del PDF
# ─────────────────────────────────────────────────────────────────────────

def draw_qr(canvas_obj, value, x, y, size=1.6 * cm):
    if not value:
        return
    try:
        qr = QrCodeWidget(value)
        bounds = qr.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
        drawing.add(qr)
        renderPDF.draw(drawing, canvas_obj, x, y)
    except Exception:
        pass


def draw_header_footer(canvas_obj, doc, config, catalogo_dir_path):
    page_width, page_height = doc.pagesize
    page_num = canvas_obj.getPageNumber()

    portada_img, _ = find_asset(catalogo_dir_path, 'portada', ['png', 'jpg', 'jpeg'])
    bordes_img, _ = find_asset(catalogo_dir_path, 'bordes', ['png', 'jpg', 'jpeg'])

    if page_num == 1 and portada_img:
        try:
            canvas_obj.drawImage(portada_img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=False, mask='auto')
        except Exception:
            pass
        return

    if bordes_img:
        try:
            canvas_obj.drawImage(bordes_img, 0, 0, width=page_width, height=page_height, preserveAspectRatio=False, mask='auto')
        except Exception:
            pass

    if config.get('repetir_encabezado', True):
        logo_principal, _ = find_asset(catalogo_dir_path, 'logo_principal', ['png', 'jpg', 'jpeg'])
        logo_secundario, _ = find_asset(catalogo_dir_path, 'logo_secundario', ['png', 'jpg', 'jpeg'])
        banner, _ = find_asset(catalogo_dir_path, 'banner_encabezado', ['png', 'jpg', 'jpeg'])

        canvas_obj.setFillColor(colors.HexColor(config.get('color_encabezado', '#0f172a')))
        canvas_obj.rect(0, page_height - 2.1 * cm, page_width, 2.1 * cm, fill=1, stroke=0)
        if banner:
            try:
                canvas_obj.drawImage(banner, 0, page_height - 2.1 * cm, width=page_width, height=2.1 * cm, preserveAspectRatio=False, mask='auto')
            except Exception:
                pass
        if logo_principal:
            try:
                canvas_obj.drawImage(logo_principal, 0.8 * cm, page_height - 1.8 * cm, width=1.2 * cm, height=1.2 * cm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        if logo_secundario:
            try:
                canvas_obj.drawImage(logo_secundario, page_width - 2.0 * cm, page_height - 1.8 * cm, width=1.2 * cm, height=1.2 * cm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        canvas_obj.setFillColor(colors.white)
        canvas_obj.setFont('Helvetica-Bold', 11)
        canvas_obj.drawString(2.4 * cm, page_height - 0.9 * cm, config.get('nombre_negocio', 'Mi Tienda'))
        canvas_obj.setFont('Helvetica', 8)
        canvas_obj.drawString(2.4 * cm, page_height - 1.35 * cm, config.get('slogan', ''))
        meta = ' • '.join(filter(None, [config.get('telefonos', ''), config.get('correo', ''), config.get('sitio_web', '')]))
        if meta:
            canvas_obj.drawString(2.4 * cm, page_height - 1.75 * cm, meta)
        if config.get('qr_texto'):
            draw_qr(canvas_obj, config['qr_texto'], page_width - 3.0 * cm, page_height - 2.0 * cm, size=1.4 * cm)

    if config.get('numerar_paginas', True):
        canvas_obj.setFillColor(colors.HexColor('#64748b'))
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.drawRightString(page_width - 1.0 * cm, 0.8 * cm, str(page_num))

    if config.get('pie_pagina'):
        canvas_obj.setFillColor(colors.HexColor('#64748b'))
        canvas_obj.setFont('Helvetica', 7)
        canvas_obj.drawCentredString(page_width / 2, 0.5 * cm, config['pie_pagina'])


def product_card(producto, config, styles, catalogo_dir_path, page_width):
    color_categoria = colors.HexColor(config.get('color_categoria', '#2563eb'))
    color_texto = colors.HexColor(config.get('color_texto', '#334155'))
    color_precio = colors.HexColor(config.get('color_precio', '#15803d'))
    color_borde = colors.HexColor(config.get('color_borde', '#dbeafe'))
    color_tarjeta = colors.HexColor(config.get('color_tarjeta', '#ffffff'))
    fuente_titulo = config.get('fuente_titulo', 'Helvetica-Bold')
    fuente_texto = config.get('fuente_texto', 'Helvetica')
    columnas = max(1, int(config.get('columnas', 3)))
    card_width = (page_width - 2.0 * cm) / columnas
    image_height = 5.0 * cm if columnas <= 2 else 4.2 * cm

    title_style = ParagraphStyle('CardTitle', parent=styles['Heading3'], fontName=fuente_titulo, fontSize=int(config.get('tamano_titulo', 18)), textColor=color_texto, alignment=TA_CENTER, leading=int(config.get('tamano_titulo', 18)) + 1)
    body_style = ParagraphStyle('CardBody', parent=styles['BodyText'], fontName=fuente_texto, fontSize=int(config.get('tamano_descripcion', 10)), textColor=color_texto, alignment=TA_CENTER, leading=int(config.get('tamano_descripcion', 10)) + 2)
    section_style = ParagraphStyle('CardSection', parent=styles['BodyText'], fontName=fuente_titulo, fontSize=9, textColor=color_categoria, alignment=TA_CENTER)
    price_style = ParagraphStyle('CardPrice', parent=styles['BodyText'], fontName=fuente_titulo, fontSize=int(config.get('tamano_precio', 24)), textColor=color_precio, alignment=TA_CENTER, leading=int(config.get('tamano_precio', 24)) + 1)

    image_path = producto.imagen.path if producto.imagen and hasattr(producto.imagen, 'path') and os.path.exists(producto.imagen.path) else None
    if image_path:
        try:
            image = Image(image_path, width=card_width - 0.4 * cm, height=image_height, kind='proportional')
        except Exception:
            image = Paragraph('Sin imagen', body_style)
    else:
        image = Paragraph('Sin imagen', body_style)

    categoria = Paragraph(f"<b>{(producto.categoria or 'General').upper()}</b>", section_style) if config.get('mostrar_categoria', True) else Spacer(1, 0.1 * cm)
    nombre = Paragraph(f"<b>{(producto.nombre or str(producto.tipo_producto) or 'Producto').upper()}</b>", title_style)

    detalles = []
    if config.get('mostrar_marca', True) and producto.marca:
        detalles.append(f"<b>Marca/Proveedor:</b> {producto.marca}")
    if config.get('mostrar_codigo', True):
        detalles.append(f"<b>Código:</b> {producto.codigo_catalogo}")
    if config.get('mostrar_sku', True) and producto.sku_catalogo:
        detalles.append(f"<b>SKU:</b> {producto.sku_catalogo}")
    if producto.variante:
        detalles.append(f"<b>Variante:</b> {producto.variante}")
    if config.get('mostrar_stock', True):
        detalles.append(f"<b>Stock:</b> {producto.stock}")
    if config.get('mostrar_descripcion', True) and producto.descripcion:
        detalles.append(producto.descripcion[:120])
    descripcion = Paragraph('<br/>'.join(detalles), body_style) if detalles else Spacer(1, 0.1 * cm)

    moneda = config.get('moneda', '$')
    modo_precios = config.get('modo_precios', 'ambos')
    precio_html = ''
    precio_a_mostrar = producto.precio_oferta if (producto.es_oferta and modo_precios in ('oferta', 'ambos')) else producto.precio
    if modo_precios != 'oculto' and precio_a_mostrar is not None:
        precio_html += f"<b>{moneda}{float(precio_a_mostrar):.2f}</b>"
        if producto.es_oferta and config.get('mostrar_precio_anterior', True) and producto.precio_anterior:
            precio_html += f"<br/><font size='9' color='#94a3b8'><strike>{moneda}{float(producto.precio_anterior):.2f}</strike></font>"
        if producto.es_oferta and config.get('mostrar_descuento', True) and producto.descuento_catalogo:
            precio_html += f"<br/><font size='9'>Ahorras: {moneda}{producto.descuento_catalogo:.2f}</font>"
        if producto.es_oferta and config.get('mostrar_porcentaje_descuento', True) and producto.porcentaje_descuento:
            precio_html += f"<br/><font size='9'>-{producto.porcentaje_descuento}%</font>"
    precio = Paragraph(precio_html or '&nbsp;', price_style)

    card = Table([[image], [categoria], [nombre], [descripcion], [precio]], colWidths=[card_width - 0.4 * cm])
    card.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color_tarjeta),
        ('BOX', (0, 0), (-1, -1), 1, color_borde),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    return card


def render_catalog_pdf(request, productos, config, catalogo_dir_path):
    page_size_value = page_size(config)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size_value,
        rightMargin=0.9 * cm,
        leftMargin=0.9 * cm,
        topMargin=2.6 * cm if config.get('repetir_encabezado', True) else 1.5 * cm,
        bottomMargin=1.3 * cm,
    )

    styles = getSampleStyleSheet()
    fuente_titulo_path = config.get('fuente_titulo_path')
    fuente_texto_path = config.get('fuente_texto_path')
    if fuente_titulo_path and os.path.exists(fuente_titulo_path):
        try:
            pdfmetrics.registerFont(TTFont('TituloCustom', fuente_titulo_path))
            config['fuente_titulo'] = 'TituloCustom'
        except Exception:
            pass
    if fuente_texto_path and os.path.exists(fuente_texto_path):
        try:
            pdfmetrics.registerFont(TTFont('TextoCustom', fuente_texto_path))
            config['fuente_texto'] = 'TextoCustom'
        except Exception:
            pass

    elements = []
    portada_pdf = os.path.join(catalogo_dir_path, 'portada.pdf')
    if not any(os.path.exists(os.path.join(catalogo_dir_path, f'portada.{ext}')) for ext in ['png', 'jpg', 'jpeg']) and not os.path.exists(portada_pdf):
        title_style = ParagraphStyle('CatalogTitle', parent=styles['Title'], fontName=config.get('fuente_titulo', 'Helvetica-Bold'), fontSize=28, alignment=TA_CENTER, textColor=colors.HexColor(config.get('color_encabezado', '#0f172a')))
        subtitle_style = ParagraphStyle('CatalogSubtitle', parent=styles['Heading2'], fontName=config.get('fuente_texto', 'Helvetica'), fontSize=13, alignment=TA_CENTER, textColor=colors.HexColor(config.get('color_texto', '#334155')))
        elements.extend([
            Spacer(1, 2.3 * cm),
            Paragraph(f"<b>{config.get('nombre_negocio', 'Mi Tienda')}</b>", title_style),
            Spacer(1, 0.4 * cm),
            Paragraph(config.get('slogan', ''), subtitle_style),
            Spacer(1, 0.5 * cm),
            Paragraph(f"{len(productos)} productos listos para catálogo", subtitle_style),
            PageBreak(),
        ])
    else:
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(PageBreak())

    grupos = group_products(productos, config.get('agrupar_por', 'categoria'))
    columnas = max(1, int(config.get('columnas', 3)))
    productos_por_pagina = max(1, int(config.get('productos_por_pagina', 6)))
    page_width = page_size_value[0]

    for group_index, (group_name, items) in enumerate(grupos):
        header_style = ParagraphStyle('GroupHeader', parent=styles['Heading2'], fontName=config.get('fuente_titulo', 'Helvetica-Bold'), fontSize=14, textColor=colors.HexColor(config.get('color_categoria', '#2563eb')), alignment=TA_LEFT)
        elements.append(Paragraph(group_name, header_style))
        elements.append(Spacer(1, config.get('espaciado_categorias', 1.0) * cm))

        for start in range(0, len(items), productos_por_pagina):
            page_items = items[start:start + productos_por_pagina]
            rows = []
            row = []
            for producto in page_items:
                row.append(product_card(producto, config, styles, catalogo_dir_path, page_width))
                if len(row) == columnas:
                    rows.append(row)
                    row = []
            if row:
                while len(row) < columnas:
                    row.append('')
                rows.append(row)

            if rows:
                grid = Table(rows, colWidths=[(page_width - 2.0 * cm) / columnas] * columnas, hAlign='CENTER')
                grid.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), config.get('separacion_columnas', 0.4) * cm),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), config.get('espaciado_productos', 0.5) * cm),
                ]))
                elements.append(grid)
                elements.append(Spacer(1, 0.4 * cm))

        if group_index < len(grupos) - 1:
            elements.append(PageBreak())

    doc.build(
        elements,
        onFirstPage=lambda canvas_obj, doc_obj: draw_header_footer(canvas_obj, doc_obj, config, catalogo_dir_path),
        onLaterPages=lambda canvas_obj, doc_obj: draw_header_footer(canvas_obj, doc_obj, config, catalogo_dir_path),
    )

    buffer.seek(0)
    portada_pdf_path = os.path.join(catalogo_dir_path, 'portada.pdf')
    bordes_pdf_path = os.path.join(catalogo_dir_path, 'bordes.pdf')
    if os.path.exists(portada_pdf_path) or os.path.exists(bordes_pdf_path):
        generated = PdfReader(buffer)
        writer = PdfWriter()
        if os.path.exists(portada_pdf_path):
            try:
                writer.add_page(PdfReader(portada_pdf_path).pages[0])
            except Exception:
                pass
        for index, page in enumerate(generated.pages):
            if index == 0 and os.path.exists(portada_pdf_path):
                continue
            if os.path.exists(bordes_pdf_path) and index > 0:
                try:
                    border_page = PdfReader(bordes_pdf_path).pages[0]
                    border_page.merge_page(page)
                    writer.add_page(border_page)
                except Exception:
                    writer.add_page(page)
            else:
                writer.add_page(page)
        final_buffer = io.BytesIO()
        writer.write(final_buffer)
        final_buffer.seek(0)
        return final_buffer

    return buffer