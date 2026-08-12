import io
import os

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from empresas.mixins import requiere_modulo
from .forms import CatalogoFilterForm
from . import utils


@login_required
@requiere_modulo('catalogos')
def contar_productos_catalogo(request):
    """
    Devuelve solo el conteo de productos que matchean los filtros actuales,
    en JSON. La usa generar_catalogo.html para mostrar '¿cuántos productos
    voy a exportar?' en vivo mientras se escribe/marca filtros, sin recargar
    la página ni navegar a otra vista.

    Reutiliza exactamente el mismo apply_catalog_filters que usan
    generar_catalogo/preview_catalogo/descargar_catalogo, así que el número
    que ves acá siempre va a coincidir con lo que realmente se exporta.
    """
    form = CatalogoFilterForm(request.GET or None, empresa=request.empresa)
    productos_qs = utils.apply_catalog_filters(request, form, include_excluded=False)

    data = form.cleaned_data if form.is_valid() else {}
    if data.get('mas_vendidos') or data.get('mayor_rentabilidad'):
        # Estos dos dependen de datos calculados en Python (ventas, margen),
        # no se pueden contar con un simple .count() de la base de datos.
        sort_by = data.get('sort_by') or 'categoria'
        productos = utils.enrich_and_sort_products(request, list(productos_qs), sort_by)
        productos = utils.apply_special_filters(productos, data)
        total = len(productos)
    else:
        total = productos_qs.count()

    return JsonResponse({'total': total})


@login_required
@requiere_modulo('catalogos')
def generar_catalogo(request):
    """Vista para configurar y generar catálogo PDF"""
    
    form = CatalogoFilterForm(request.GET or None, empresa=request.empresa)

    # Por defecto solo se muestran productos disponibles (no vendidos ni
    # reservados). El checkbox "activos" del formulario queda como filtro
    # redundante/explícito para el usuario, pero la regla de negocio real
    # (un catálogo no debe listar productos ya vendidos) se aplica siempre.
    productos_qs = utils.apply_catalog_filters(request, form, include_excluded=False)

    if form.is_valid():
        sort_by = form.cleaned_data.get('sort_by')
        if sort_by and sort_by not in ('mas_vendidos', 'rentabilidad'):
            productos_qs = productos_qs.order_by(sort_by)

    # El formulario para la plantilla
    context = {
        'form': form,
        'productos': productos_qs,
        'total_productos': productos_qs.count(),
    }
    
    return render(request, 'catalogos/generar_catalogo.html', context)


@login_required
@requiere_modulo('catalogos')
def preview_catalogo(request):
    """Vista para mostrar previsualización HTML del catálogo antes de descargar PDF"""
    
    form = CatalogoFilterForm(request.GET or None, empresa=request.empresa)

    productos_qs = utils.apply_catalog_filters(request, form, include_excluded=False)
    sort_by = form.cleaned_data.get('sort_by') if form.is_valid() else 'categoria'

    # Enriquecemos SIEMPRE (no solo para descargar el PDF): así la vista
    # previa web también muestra precio de oferta real, badge de destacado
    # y respeta "más vendidos" / "mayor rentabilidad", que antes solo
    # funcionaban (a medias) en el PDF.
    productos = utils.enrich_and_sort_products(request, list(productos_qs), sort_by or 'categoria')
    if form.is_valid():
        productos = utils.apply_special_filters(productos, form.cleaned_data)

    group_by = form.cleaned_data.get('group_by') if form.is_valid() else request.GET.get('group_by')
    productos_agrupados = dict(utils.group_products(productos, group_by))

    # Query string para descargar
    query_string = request.GET.urlencode()

    context = {
        'productos_agrupados': productos_agrupados,
        'total_productos': len(productos),
        'query_string': query_string,
    }

    return render(request, 'catalogos/preview_catalogo.html', context)


@login_required
@requiere_modulo('catalogos')
def descargar_catalogo(request):
    """
    Genera y descarga el PDF del catálogo.

    Antes esta vista tenía ~560 líneas con todo el layout hardcodeado
    (tamaños "mágicos" según productos_por_pagina == 2/3/4, márgenes fijos,
    un esquema de configuración viejo). Ahora reutiliza el motor de
    utils.render_catalog_pdf, que lee la configuración real guardada en
    "Personalizar Diseño" (columnas, colores, tipografía, plantilla, etc.)
    """
    catalogo_dir_path = utils.catalogo_dir(request.empresa.id)
    os.makedirs(catalogo_dir_path, exist_ok=True)
    config = utils.load_catalogo_config(catalogo_dir_path)

    form = CatalogoFilterForm(request.GET or None, empresa=request.empresa)
    productos_qs = utils.apply_catalog_filters(request, form, include_excluded=False)
    sort_by = form.cleaned_data.get('sort_by') if form.is_valid() else config.get('ordenar_por', 'categoria')

    productos = utils.enrich_and_sort_products(request, list(productos_qs), sort_by or 'categoria')
    if form.is_valid():
        productos = utils.apply_special_filters(productos, form.cleaned_data)
        group_by = form.cleaned_data.get('group_by')
        if group_by:
            config = dict(config)
            config['agrupar_por'] = group_by

    if not productos:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=utils.page_size(config))
        styles = getSampleStyleSheet()
        doc.build([Spacer(1, 4 * cm), Paragraph('No hay productos para generar el catálogo con estos filtros.', styles['Title'])])
        buffer.seek(0)
        response = HttpResponse(buffer, content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="catalogo_vacio.pdf"'
        return response

    buffer = utils.render_catalog_pdf(request, productos, config, catalogo_dir_path)
    filename = f"catalogo_{config.get('nombre_negocio', 'empresa').replace(' ', '_').lower()}.pdf"
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ─────────────────────────────────────────────────────────────────────────
# Personalizar Diseño del Catálogo — editor visual completo
# ─────────────────────────────────────────────────────────────────────────

# Assets tipo imagen/pdf que se pueden subir tal cual (nombre de campo del
# formulario == nombre base del archivo en disco).
ASSETS_IMAGEN = {
    'logo_principal': ['png', 'jpg', 'jpeg'],
    'logo_secundario': ['png', 'jpg', 'jpeg'],
    'banner_encabezado': ['png', 'jpg', 'jpeg'],
    'portada': ['png', 'jpg', 'jpeg', 'pdf'],
    'bordes': ['png', 'jpg', 'jpeg', 'pdf'],
}

# Fuentes personalizadas: se guardan en disco Y se registra su ruta en el
# config JSON (fuente_titulo_path / fuente_texto_path), porque
# render_catalog_pdf necesita saber dónde está el .ttf/.otf para incrustarlo.
FUENTES_PERSONALIZADAS = {
    'fuente_titulo_archivo': 'fuente_titulo_path',
    'fuente_texto_archivo': 'fuente_texto_path',
}


def _config_desde_post(request, config):
    """Vuelca al dict de config todos los campos del editor que llegaron por POST."""
    post = request.POST
    nueva = dict(config)

    campos_texto = [
        'nombre_negocio', 'slogan', 'direccion', 'telefonos', 'correo',
        'sitio_web', 'redes_sociales', 'qr_texto', 'fecha_emision', 'pie_pagina',
        'moneda', 'color_encabezado', 'color_categoria', 'color_etiqueta',
        'color_precio', 'color_fondo', 'color_tarjeta', 'color_texto', 'color_borde',
        'fuente_titulo', 'fuente_texto', 'modo_precios', 'agrupar_por', 'ordenar_por',
        'orientation', 'page_size',
    ]
    for campo in campos_texto:
        if campo in post:
            nueva[campo] = post.get(campo, '').strip()

    campos_enteros = ['columnas', 'productos_por_pagina', 'tamano_titulo', 'tamano_precio', 'tamano_descripcion']
    for campo in campos_enteros:
        valor = post.get(campo)
        if valor not in (None, ''):
            try:
                nueva[campo] = int(valor)
            except ValueError:
                pass

    campos_decimales = ['margen', 'espaciado_productos', 'espaciado_categorias', 'separacion_columnas']
    for campo in campos_decimales:
        valor = post.get(campo)
        if valor not in (None, ''):
            try:
                nueva[campo] = float(valor)
            except ValueError:
                pass

    # Checkboxes: si el campo no viene en el POST, el checkbox estaba
    # desmarcado (así funciona HTML). Por eso se recorre explícitamente
    # la lista completa, no solo lo que llegó.
    campos_booleanos = [
        'repetir_encabezado', 'numerar_paginas', 'mostrar_codigo', 'mostrar_sku',
        'mostrar_categoria', 'mostrar_marca', 'mostrar_descripcion', 'mostrar_stock',
        'mostrar_precio_anterior', 'mostrar_descuento', 'mostrar_porcentaje_descuento',
        'ajustar_imagen_automaticamente', 'mantener_proporcion', 'recortar_imagen',
        'centrar_imagen', 'fondo_blanco_auto', 'bordes_redondeados', 'sombras',
    ]
    for campo in campos_booleanos:
        nueva[campo] = campo in post

    return nueva


@login_required
@requiere_modulo('catalogos')
def personalizar_catalogo(request):
    """Editor visual completo del catálogo: cabecera, encabezado, tarjetas,
    colores, tipografía, distribución, imágenes, precios, numeración y
    plantillas prediseñadas. Todo se guarda en un único config JSON por
    empresa (utils.CATALOGO_DEFAULT_CONFIG define el esquema completo)."""

    catalogo_dir_path = utils.catalogo_dir(request.empresa.id)
    os.makedirs(catalogo_dir_path, exist_ok=True)
    config = utils.load_catalogo_config(catalogo_dir_path)

    if request.method == 'POST':
        # 1) Subida de assets (logos, portada, bordes)
        for campo, exts in ASSETS_IMAGEN.items():
            if campo in request.FILES:
                ok, resultado = utils.save_uploaded_asset(request, catalogo_dir_path, campo, campo, exts)
                if ok:
                    messages.success(request, f'{campo.replace("_", " ").title()} actualizado correctamente')
                else:
                    messages.error(request, resultado)
                return redirect('personalizar_catalogo')

        # 2) Subida de fuentes personalizadas
        for campo, config_key in FUENTES_PERSONALIZADAS.items():
            if campo in request.FILES:
                ok, resultado = utils.save_uploaded_asset(request, catalogo_dir_path, campo, campo, ['ttf', 'otf'])
                if ok:
                    config[config_key] = resultado
                    utils.save_catalogo_config(catalogo_dir_path, config)
                    messages.success(request, 'Fuente personalizada actualizada correctamente')
                else:
                    messages.error(request, resultado)
                return redirect('personalizar_catalogo')

        # 3) Eliminar un asset (logo/portada/bordes/fuente)
        if 'eliminar_asset' in request.POST:
            base_name = request.POST.get('eliminar_asset', '')
            if base_name in list(ASSETS_IMAGEN.keys()) + list(FUENTES_PERSONALIZADAS.keys()):
                for ext in ['png', 'jpg', 'jpeg', 'pdf', 'ttf', 'otf']:
                    path = os.path.join(catalogo_dir_path, f'{base_name}.{ext}')
                    if os.path.exists(path):
                        os.remove(path)
                messages.success(request, 'Archivo eliminado correctamente')
            return redirect('personalizar_catalogo')

        # 4) Aplicar una plantilla prediseñada
        if 'aplicar_plantilla' in request.POST:
            plantilla_id = request.POST.get('aplicar_plantilla')
            config = utils.aplicar_plantilla(config, plantilla_id)
            utils.save_catalogo_config(catalogo_dir_path, config)
            nombre_plantilla = utils.CATALOGO_PLANTILLAS.get(plantilla_id, {}).get('label', plantilla_id)
            messages.success(request, f'Plantilla "{nombre_plantilla}" aplicada. Puedes seguir personalizando cualquier detalle debajo.')
            return redirect('personalizar_catalogo')

        # 5) Guardar la configuración completa del editor
        if 'guardar_configuracion' in request.POST:
            config = _config_desde_post(request, config)
            utils.save_catalogo_config(catalogo_dir_path, config)
            messages.success(request, 'Diseño del catálogo actualizado correctamente')
            return redirect('personalizar_catalogo')

    # Estado de los assets para mostrar previews en la plantilla
    assets = {}
    for base_name, exts in ASSETS_IMAGEN.items():
        path, ext = utils.find_asset(catalogo_dir_path, base_name, exts)
        assets[base_name] = {
            'existe': bool(path),
            'url': utils.asset_url(request.empresa.id, base_name, ext) if path else None,
            'formato': ext.upper() if ext else None,
            'es_pdf': ext == 'pdf',
        }

    fuentes = {}
    for campo, config_key in FUENTES_PERSONALIZADAS.items():
        ruta = config.get(config_key)
        # 'campo' (ej. 'fuente_titulo_archivo') es el mismo base_name con el
        # que se guardó el archivo en save_uploaded_asset, así que sirve para
        # reconstruir su URL pública y poder cargarla como @font-face en el
        # navegador (la vista previa en vivo la necesita).
        asset_path, asset_ext = utils.find_asset(catalogo_dir_path, campo, ['ttf', 'otf'])
        fuentes[config_key] = {
            'existe': bool(ruta and os.path.exists(ruta)),
            'nombre': os.path.basename(ruta) if ruta else None,
            'url': utils.asset_url(request.empresa.id, campo, asset_ext) if asset_path else None,
            'formato': asset_ext,
        }

    # Listas usadas por el template para pintar checkboxes/colores/archivos
    # sin repetir el mismo bloque HTML 8 o 10 veces (recorridas con {% for %}
    # + el filtro get_item, ya que Django no permite {{ config.campo_var }}
    # con una clave que es una variable).
    tarjeta_checks = [
        ('mostrar_codigo', 'Código'),
        ('mostrar_sku', 'SKU'),
        ('mostrar_categoria', 'Categoría'),
        ('mostrar_marca', 'Marca / Proveedor'),
        ('mostrar_descripcion', 'Descripción corta'),
        ('mostrar_stock', 'Stock'),
    ]
    color_fields = [
        ('color_encabezado', 'Encabezado'),
        ('color_categoria', 'Categorías'),
        ('color_etiqueta', 'Etiquetas'),
        ('color_precio', 'Precio'),
        ('color_fondo', 'Fondo de página'),
        ('color_tarjeta', 'Fondo de tarjeta'),
        ('color_texto', 'Texto'),
        ('color_borde', 'Bordes'),
    ]
    imagen_checks = [
        ('ajustar_imagen_automaticamente', 'Ajustar automáticamente'),
        ('mantener_proporcion', 'Mantener proporción'),
        ('recortar_imagen', 'Recortar para llenar el marco'),
        ('centrar_imagen', 'Centrar imagen'),
        ('fondo_blanco_auto', 'Fondo blanco automático'),
        ('bordes_redondeados', 'Bordes redondeados'),
        ('sombras', 'Sombras'),
    ]
    asset_specs = [
        ('logo_principal', 'Logo principal', 'image/png,image/jpeg'),
        ('logo_secundario', 'Logo secundario', 'image/png,image/jpeg'),
        ('banner_encabezado', 'Banner de encabezado', 'image/png,image/jpeg'),
        ('portada', 'Portada (primera página)', 'image/png,image/jpeg,application/pdf'),
        ('bordes', 'Fondo de páginas internas', 'image/png,image/jpeg,application/pdf'),
    ]

    context = {
        'config': config,
        'assets': assets,
        'fuentes': fuentes,
        'plantillas': utils.CATALOGO_PLANTILLAS,
        'plantilla_actual': config.get('plantilla', 'moderna'),
        'tarjeta_checks': tarjeta_checks,
        'color_fields': color_fields,
        'imagen_checks': imagen_checks,
        'asset_specs': asset_specs,
    }
    return render(request, 'catalogos/personalizar_catalogo.html', context)