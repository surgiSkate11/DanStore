from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.db.models import Q
from django.conf import settings
from django.contrib import messages
from productos.models import Producto
from productos.forms import ProductoFiltroForm
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch, cm
from reportlab.platypus import SimpleDocTemplate, Image, Paragraph, Table, TableStyle, Spacer, PageBreak, PageTemplate, Frame
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.pdfgen import canvas
import io
import os
import json
from PIL import Image as PILImage
from PyPDF2 import PdfReader, PdfWriter


@login_required
def generar_catalogo(request):
    """Vista para configurar y generar catálogo PDF"""
    filtro_form = ProductoFiltroForm(request.GET or None, empresa=request.empresa)
    
    # Obtener productos según filtros
    # Excluir productos vendidos y separados (no deben aparecer en catálogo público)
    productos = Producto.objects.filter(empresa=request.empresa).exclude(estado__in=['vendido', 'separado'])
    
    if filtro_form.is_valid():
        if filtro_form.cleaned_data.get('categoria'):
            productos = productos.filter(
                categoria=filtro_form.cleaned_data['categoria']
            )
        
        if filtro_form.cleaned_data.get('tipo_producto'):
            productos = productos.filter(
                tipo_producto=filtro_form.cleaned_data['tipo_producto']
            )
        
        if filtro_form.cleaned_data.get('busqueda'):
            busqueda = filtro_form.cleaned_data['busqueda']
            productos = productos.filter(
                Q(descripcion__icontains=busqueda)
            )
    
    context = {
        'filtro_form': filtro_form,
        'total_productos': productos.count(),
    }
    
    return render(request, 'catalogos/generar_catalogo.html', context)


@login_required
def preview_catalogo(request):
    """Vista para mostrar previsualización HTML del catálogo antes de descargar PDF"""
    
    # Obtener productos según filtros
    productos = Producto.objects.filter(empresa=request.empresa).exclude(estado__in=['vendido', 'separado'])
    
    # Aplicar filtros
    categoria = request.GET.get('categoria')
    tipo_producto_id = request.GET.get('tipo_producto')
    busqueda = request.GET.get('busqueda')
    
    if categoria:
        productos = productos.filter(categoria=categoria)
    
    if tipo_producto_id:
        productos = productos.filter(tipo_producto_id=tipo_producto_id)
    
    if busqueda:
        productos = productos.filter(Q(descripcion__icontains=busqueda))
    
    # Ordenar por categoría y precio
    productos = productos.order_by('categoria', 'tipo_producto', 'precio')
    
    # Query string para descargar
    query_string = request.GET.urlencode()
    
    context = {
        'productos': productos,
        'total_productos': productos.count(),
        'query_string': query_string,
        'categoria': categoria,
        'tipo_producto_id': tipo_producto_id,
        'busqueda': busqueda,
    }
    
    return render(request, 'catalogos/preview_catalogo.html', context)


def get_fondo_pagina_callback(catalogo_dir):
    """Fábrica de callbacks para inyectar el directorio correcto del tenant"""
    def agregar_fondo_pagina(canvas_obj, doc):
        # Buscar portada
        portada_path = None
        for ext in ['png', 'jpg', 'jpeg']:
            path = os.path.join(catalogo_dir, f'portada.{ext}')
            if os.path.exists(path):
                portada_path = path
                break
        
        # Buscar bordes
        bordes_path = None
        for ext in ['png', 'jpg', 'jpeg']:
            path = os.path.join(catalogo_dir, f'bordes.{ext}')
            if os.path.exists(path):
                bordes_path = path
                break
        
        # doc.page es el número de página actual (empezando en 1)
        page_num = doc.page - 1  # Convertir a 0-indexed
        
        # Página 0: Portada (sin número de página)
        if page_num == 0 and portada_path:
            try:
                canvas_obj.drawImage(portada_path, 0, 0, width=A4[0], height=A4[1], preserveAspectRatio=False)
            except Exception as e:
                print(f"Error al cargar portada: {e}")
        
        # Páginas 1+: Bordes y número de página
        elif page_num > 0 and bordes_path:
            try:
                canvas_obj.drawImage(bordes_path, 0, 0, width=A4[0], height=A4[1], preserveAspectRatio=False)
            except Exception as e:
                print(f"Error al cargar bordes: {e}")
            
            numero_pagina_catalogo = page_num + 1
            canvas_obj.setFont("Helvetica", 10)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawRightString(A4[0] - 1.5*cm, 1.2*cm, str(numero_pagina_catalogo))
        
        # Si no hay bordes pero es página de contenido, agregar número de página
        elif page_num > 0:
            numero_pagina_catalogo = page_num + 1
            canvas_obj.setFont("Helvetica", 10)
            canvas_obj.setFillColor(colors.HexColor('#666666'))
            canvas_obj.drawRightString(A4[0] - 1.5*cm, 1.2*cm, str(numero_pagina_catalogo))
            
    return agregar_fondo_pagina


@login_required
def descargar_catalogo(request):
    """Vista para generar y descargar el PDF del catálogo con diseño personalizado"""
    
    # Obtener productos según filtros
    # IMPORTANTE: Solo productos disponibles (excluir vendidos y separados)
    productos = Producto.objects.filter(empresa=request.empresa).exclude(estado__in=['vendido', 'separado'])
    catalogo_dir = os.path.join(settings.MEDIA_ROOT, f'catalogo_tenant_{request.empresa.id}')
    
    # Aplicar filtros de la query string
    categoria = request.GET.get('categoria')
    tipo_producto_id = request.GET.get('tipo_producto')
    busqueda = request.GET.get('busqueda')
    
    if categoria:
        productos = productos.filter(categoria=categoria)
    
    if tipo_producto_id:
        productos = productos.filter(tipo_producto_id=tipo_producto_id)
    
    if busqueda:
        productos = productos.filter(Q(descripcion__icontains=busqueda))
    
    # Ordenar productos por categoría y tipo para mejor organización del catálogo
    productos = productos.order_by('categoria', 'tipo_producto', 'id')
    
    # Cargar configuración de diseño para obtener productos_por_pagina
    config_file = os.path.join(catalogo_dir, 'config_diseno.json')
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config_diseno_temp = json.load(f)
    else:
        config_diseno_temp = {}
    
    productos_por_pagina_config = config_diseno_temp.get('productos_por_pagina', 3)
    
    # Márgenes dinámicos según cantidad de productos por página
    # 2 productos: aumentar margen superior para aprovechar espacio inferior sobrante
    # 3 productos: margen normal
    # 4 productos: usar el mismo margen que 3 para encajar perfectamente
    if productos_por_pagina_config == 2:
        margen_superior = 4.0*cm  # Aumentado para centrar mejor verticalmente
        margen_inferior = 1.4*cm
    elif productos_por_pagina_config == 3:
        margen_superior = 2.0*cm  
        margen_inferior = 1.4*cm
    else:  # 4 productos
        margen_superior = 1.8*cm  
        margen_inferior = 1.4*cm
    
    # Crear el PDF con tamaño A4 y márgenes dinámicos
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=0.8*cm,
        leftMargin=0.8*cm,
        topMargin=margen_superior,  # Margen superior dinámico
        bottomMargin=margen_inferior  # Margen inferior balanceado
    )
    
    # Contenedor para los elementos del PDF
    elements = []
    
    # Cargar configuración de diseño
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config_diseno = json.load(f)
    else:
        config_diseno = {
            'color_principal': '#e94560',
            'color_precio': '#27ae60',
            'color_texto': '#555555',
            'color_titulo': '#1a1a2e',
            'color_borde': '#e94560',
            'grosor_borde': 2,
            'estilo_precio': 'moderno',
            'nombre_negocio': 'Mi Tienda',
            'subtitulo_negocio': 'Productos de Excelente Calidad',
            'lema_negocio': 'Calidad y Estilo'
        }
    
    # Estilos con colores personalizados
    styles = getSampleStyleSheet()
    
    style_titulo = ParagraphStyle(
        'PortadaTitulo',
        parent=styles['Heading1'],
        fontSize=32,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=30,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    style_subtitulo = ParagraphStyle(
        'PortadaSubtitulo',
        parent=styles['Heading2'],
        fontSize=18,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Registrar fuentes personalizadas si existen
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    
    fuente_titulo_nombre = 'Helvetica-Bold'
    fuente_texto_nombre = 'Helvetica'
    
    # Registrar fuente de título
    if config_diseno.get('fuente_titulo_path') and os.path.exists(config_diseno['fuente_titulo_path']):
        try:
            pdfmetrics.registerFont(TTFont('TituloCustom', config_diseno['fuente_titulo_path']))
            fuente_titulo_nombre = 'TituloCustom'
        except Exception as e:
            print(f"Error al registrar fuente de título: {e}")
    
    # Registrar fuente de texto
    if config_diseno.get('fuente_texto_path') and os.path.exists(config_diseno['fuente_texto_path']):
        try:
            pdfmetrics.registerFont(TTFont('TextoCustom', config_diseno['fuente_texto_path']))
            fuente_texto_nombre = 'TextoCustom'
        except Exception as e:
            print(f"Error al registrar fuente de texto: {e}")
    
    # Tamaños de fuente OPTIMIZADOS según productos por página
    productos_por_pagina = config_diseno.get('productos_por_pagina', 3)
    
    if productos_por_pagina == 1:
        tamano_descripcion = 20
        tamano_titulo = 28
        tamano_precio = 36
    elif productos_por_pagina == 2:
        tamano_descripcion = 17  # Aumentado
        tamano_titulo = 26  # Aumentado
        tamano_precio = 24  # Ligeramente reducido para evitar desbordamiento
    elif productos_por_pagina == 3:
        tamano_descripcion = 14
        tamano_titulo = 20
        tamano_precio = 26  # Perfecto
    else:  # 4
        tamano_descripcion = 12
        tamano_titulo = 17
        tamano_precio = 20  # Solo se reduce en 4 productos
    
    style_descripcion = ParagraphStyle(
        'ProductoDescripcion',
        parent=styles['BodyText'],
        fontSize=tamano_descripcion,
        leading=tamano_descripcion + 2,  # Interlineado mínimo
        textColor=colors.HexColor(config_diseno.get('color_texto', '#333333')),
        spaceAfter=0,  # Sin espacio después
        spaceBefore=0,  # Sin espacio antes
        alignment=TA_CENTER,
        fontName=fuente_texto_nombre
    )
    
    style_categoria = ParagraphStyle(
        'ProductoCategoria',
        parent=styles['BodyText'],
        fontSize=tamano_descripcion - 1,
        textColor=colors.HexColor(config_diseno.get('color_principal', '#e94560')),
        fontName=fuente_titulo_nombre,
        alignment=TA_CENTER,
        spaceAfter=0,
        spaceBefore=0,
        leading=tamano_descripcion - 1  # Leading mínimo igual al tamaño de fuente
    )
    
    style_titulo_producto = ParagraphStyle(
        'ProductoTitulo',
        parent=styles['Heading1'],
        fontSize=tamano_titulo,
        textColor=colors.HexColor(config_diseno.get('color_titulo', '#1a1a2e')),
        fontName=fuente_titulo_nombre,
        spaceAfter=0,  # Sin espacio después
        spaceBefore=0,  # Sin espacio antes
        alignment=TA_CENTER,
        leading=tamano_titulo  # Leading mínimo igual al tamaño de fuente
    )
    
    style_precio = ParagraphStyle(
        'ProductoPrecio',
        parent=styles['BodyText'],
        fontSize=tamano_precio,
        leading=tamano_precio,  # Leading mínimo igual al tamaño de fuente
        textColor=colors.HexColor(config_diseno.get('color_precio', '#27ae60')),
        fontName=fuente_titulo_nombre,
        spaceBefore=0,  # Sin espacio antes
        spaceAfter=0,  # Sin espacio después
        alignment=TA_CENTER
    )
    
    # Verificar si hay portada personalizada
    portada_path = os.path.join(catalogo_dir, 'portada.jpg')
    portada_png = os.path.join(catalogo_dir, 'portada.png')
    tiene_portada = os.path.exists(portada_path) or os.path.exists(portada_png)
    
    if not tiene_portada:
        # Si no hay portada personalizada, crear una simple
        elements.append(Spacer(1, 3*cm))
        titulo = Paragraph("<b>Catálogo de Productos</b>", style_titulo)
        elements.append(titulo)
        elements.append(Spacer(1, 1*cm))
        
        subtitulo = Paragraph(f"<b>{productos.count()} productos disponibles</b>", style_subtitulo)
        elements.append(subtitulo)
        elements.append(Spacer(1, 2*cm))
        
        info_html = f"<b>{config_diseno.get('nombre_negocio', 'Mi Tienda')}</b><br/>{config_diseno.get('subtitulo_negocio', 'Productos de Excelente Calidad')}"
        lema = config_diseno.get('lema_negocio', '')
        if lema:
            info_html += f"<br/>{lema}"
            
        info = Paragraph(
            info_html,
            style_subtitulo
        )
        elements.append(info)
        elements.append(PageBreak())
    else:
        # Si hay portada personalizada, agregar spacer para crear la página de portada
        elements.append(Spacer(1, 20*cm))
        elements.append(PageBreak())
    
    # Generar páginas con layout personalizado y OPTIMIZADO
    productos_lista = list(productos)
    
    # Obtener configuración de layout
    productos_por_pagina = config_diseno.get('productos_por_pagina', 3)
    alineacion_imagen = config_diseno.get('alineacion_imagen', 'alternada')
    
    # ===== CÁLCULO AUTOMÁTICO DINÁMICO Y OPTIMIZADO =====
    altura_pagina = A4[1]  # 29.7 cm = 842 puntos
    # Altura disponible considerando márgenes dinámicos
    altura_disponible = altura_pagina - margen_superior - margen_inferior
    
    # Configuración automática DINÁMICA según cantidad de productos
    # OPTIMIZADO para evitar sobreposición y maximizar espacio vertical
    if productos_por_pagina == 1:
        espacio_entre_productos = 0  # Sin productos adicionales
        ancho_imagen_config = 12.0  # Imagen MUY grande
        padding_imagen_lateral = 0.4
        padding_contenedor = 1.2 * cm  # Padding generoso dentro del contenedor
    elif productos_por_pagina == 2:
        espacio_entre_productos = 2.2 * cm  # Separación MÁXIMA para llenar espacio vertical
        ancho_imagen_config = 8.2  # Reducido para que el precio encaje perfectamente
        padding_imagen_lateral = 0.3
        padding_contenedor = 0.8 * cm  # Padding balanceado
    elif productos_por_pagina == 3:
        espacio_entre_productos = 1.0 * cm  # Separación generosa
        ancho_imagen_config = 8.0  # Imagen grande
        padding_imagen_lateral = 0.3
        padding_contenedor = 0.6 * cm
    else:  # 4 productos
        espacio_entre_productos = 0.6 * cm  # Separación moderada
        ancho_imagen_config = 6.8  # Imagen moderada
        padding_imagen_lateral = 0.25
        padding_contenedor = 0.4 * cm
    
    # Calcular altura exacta por producto maximizando el espacio
    espacio_total_entre = espacio_entre_productos * (productos_por_pagina - 1)
    # Restar padding_contenedor*2 para tener espacio interno en cada contenedor
    altura_producto = (altura_disponible - espacio_total_entre) / productos_por_pagina
    
    # Ancho disponible para contenido (A4 width = 21cm con márgenes reducidos)
    ancho_disponible = A4[0] - 0.8*cm - 0.8*cm  # ~19.4cm disponibles
    
    for i in range(0, len(productos_lista), productos_por_pagina):
        productos_pagina = productos_lista[i:i+productos_por_pagina]
        
        for idx, producto in enumerate(productos_pagina):
            # Determinar posición según configuración
            if alineacion_imagen == 'izquierda':
                es_izquierda = True
            elif alineacion_imagen == 'derecha':
                es_izquierda = False
            else:  # alternada
                es_izquierda = idx % 2 == 0
            
            # ===== PREPARAR IMAGEN CON OPTIMIZACIÓN DE ESPACIO =====
            img = None
            img_error = None
            
            # Calcular tamaño de imagen MAXIMIZADO - aprovechar el espacio vertical disponible
            img_ancho_max = (ancho_imagen_config - padding_imagen_lateral) * cm
            img_alto_max = altura_producto - (padding_contenedor * 0.5)  # Padding dinámico
            
            # Usar el más pequeño para mantener proporción cuadrada
            img_size = min(img_ancho_max, img_alto_max)
            
            if producto.imagen and hasattr(producto.imagen, 'path') and os.path.exists(producto.imagen.path):
                try:
                    img = Image(producto.imagen.path, width=img_size, height=img_size)
                    img.hAlign = 'CENTER'
                    img.vAlign = 'TOP'  # Alineación al borde superior
                except Exception as e1:
                    img_error = str(e1)
                    try:
                        # Intento 2: Usar PIL para convertir primero
                        import tempfile
                        pil_img = PILImage.open(producto.imagen.path)
                        # Convertir a RGB si es necesario
                        if pil_img.mode not in ('RGB', 'RGBA'):
                            pil_img = pil_img.convert('RGB')
                        # Guardar temporalmente y cargar con ReportLab
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                            temp_path = tmp.name
                            pil_img.save(temp_path, 'JPEG')
                            img = Image(temp_path, width=img_size, height=img_size)
                            img.hAlign = 'CENTER'
                            img.vAlign = 'TOP'  # Alineación al borde superior
                        os.unlink(temp_path)
                    except Exception as e2:
                        img_error = f"Error 1: {e1}\nError 2: {e2}"
                        img = Paragraph(
                            f'<b style="color: red;">ERROR AL CARGAR IMAGEN</b><br/>'
                            f'<i style="font-size: 8px;">{os.path.basename(producto.imagen.path)}</i><br/>'
                            f'<i style="font-size: 7px;">Verifica que el archivo exista y esté en formato válido</i>',
                            style_descripcion
                        )
            else:
                # Producto sin imagen o archivo inexistente
                # Dibujar un recuadro o texto que indique que no hay imagen
                from reportlab.platypus import Spacer
                # Creamos una tabla con un "icono" de no imagen
                no_img_data = [[Paragraph('<b style="color: #9ca3af; font-size: 14px;"><br/><br/><br/><br/>Sin Imagen</b>', style_precio)]]
                from reportlab.platypus import Table, TableStyle
                img = Table(no_img_data, colWidths=[img_size], rowHeights=[img_size])
                img.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f3f4f6')),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#e5e7eb')),
                ]))
            
            # ===== PREPARAR DESCRIPCIÓN CON DISEÑO OPTIMIZADO =====
            # Categoría destacada
            categoria_html = f'<b>★ {producto.categoria.upper() if producto.categoria else "General"} ★</b>'
            categoria_para = Paragraph(categoria_html, style_categoria)
            
            # Título del producto
            titulo_html = f'<b>{str(producto.tipo_producto).upper() if producto.tipo_producto else producto.nombre.upper()}</b>'
            titulo_para = Paragraph(titulo_html, style_titulo_producto)
            
            # Detalles compactos
            detalles = []
            
            if hasattr(producto, 'marca') and producto.marca:
                detalles.append(f'<b>✦ Marca:</b> {producto.marca}')
            
            if hasattr(producto, 'color') and producto.color:
                detalles.append(f'<b>◆ Color:</b> {producto.color}')
            
            if hasattr(producto, 'variante') and producto.variante:
                detalles.append(f'<b>◈ Variante:</b> {producto.variante}')
            
            detalles_html = '<br/>'.join(detalles)
            detalles_para = Paragraph(detalles_html, style_descripcion)
            
            # ===== PRECIO CON FONDO DECORATIVO (SI EXISTE) =====
            fondo_precio_path = None
            for ext in ['png', 'jpg', 'jpeg']:
                path_fondo = os.path.join(catalogo_dir, f'fondo_precio.{ext}')
                if os.path.exists(path_fondo):
                    fondo_precio_path = path_fondo
                    break
            
            # Crear precio con o sin fondo
            if fondo_precio_path:
                try:
                    # Tamaño ajustado del fondo según productos por página - PERFECTO
                    if productos_por_pagina == 1:
                        fondo_width, fondo_height = 9*cm, 4.5*cm
                    elif productos_por_pagina == 2:
                        fondo_width, fondo_height = 6.0*cm, 3.0*cm  # Ajustado para evitar desbordamiento
                    elif productos_por_pagina == 3:
                        fondo_width, fondo_height = 6.5*cm, 3.2*cm  # Perfecto
                    else:
                        fondo_width, fondo_height = 5.0*cm, 2.5*cm  # Reducido solo en 4
                    
                    fondo_img = Image(fondo_precio_path, width=fondo_width, height=fondo_height, kind='proportional')
                    fondo_img.hAlign = 'CENTER'
                    
                    precio_html = f'<b>${producto.precio:.2f}</b>'
                    precio_para = Paragraph(precio_html, style_precio)
                    
                    # Tabla de fondo
                    precio_fondo_table = Table([[fondo_img]], colWidths=[fondo_width], rowHeights=[fondo_height])
                    precio_fondo_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    # Tabla de texto
                    precio_text_table = Table([[precio_para]], colWidths=[fondo_width], rowHeights=[fondo_height])
                    precio_text_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                    
                    precio_element = [precio_fondo_table, Spacer(1, -fondo_height), precio_text_table]
                    
                except Exception as e:
                    print(f"Error al cargar fondo de precio: {e}")
                    precio_html = f'<b>${producto.precio:.2f}</b>'
                    precio_element = [Paragraph(precio_html, style_precio)]
            else:
                precio_html = f'<b>${producto.precio:.2f}</b>'
                precio_element = [Paragraph(precio_html, style_precio)]
            
            # ===== LAYOUT HORIZONTAL MEJORADO: Detalles a la izquierda, Precio a la derecha =====
            precio_col = precio_element
            
            # Ancho OPTIMIZADO para que todo encaje perfectamente
            if productos_por_pagina == 1:
                ancho_detalles, ancho_precio = 8.5*cm, 8.5*cm
            elif productos_por_pagina == 2:
                ancho_detalles, ancho_precio = 6.2*cm, 5.8*cm  # Reducido para mejor encaje
            elif productos_por_pagina == 3:
                ancho_detalles, ancho_precio = 6.5*cm, 6.5*cm  # Perfecto
            else:
                ancho_detalles, ancho_precio = 5.2*cm, 5.0*cm  # Ajustado solo en 4
            
            detalles_precio_data = [[detalles_para, precio_col]]
            detalles_precio_table = Table(detalles_precio_data, colWidths=[ancho_detalles, ancho_precio])
            detalles_precio_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Centrado vertical
                ('ALIGN', (0, 0), (0, 0), 'CENTER'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),  # Precio alineado a la derecha
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (1, 0), (1, 0), 0.5*cm),  # Padding derecho para el precio
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
            ]))
            
            # Crear columna de texto con espaciado estratégico OPTIMIZADO
            # Ajustar espaciado según productos por página
            if productos_por_pagina == 1:
                spacer_titulo_detalles = 0.8 * cm
            elif productos_por_pagina == 2:
                spacer_titulo_detalles = 0.6 * cm  # Balanceado para que el precio encaje
            elif productos_por_pagina == 3:
                spacer_titulo_detalles = 0.5 * cm
            else:
                spacer_titulo_detalles = 0.4 * cm
            
            texto_elements = [
                categoria_para,
                titulo_para,
                Spacer(1, spacer_titulo_detalles),  # Separación dinámica entre título y detalles/precio
                detalles_precio_table
            ]
            
            # ===== LAYOUT FINAL CON PADDING OPTIMIZADO =====
            # Ajustar anchos para usar TODO el espacio disponible
            ancho_img_col = img_size  # Usar el tamaño exacto de la imagen
            ancho_texto_col = ancho_disponible - ancho_img_col
            
            if es_izquierda:
                data = [[img, texto_elements]]
                col_widths = [ancho_img_col, ancho_texto_col]
            else:
                data = [[texto_elements, img]]
                col_widths = [ancho_texto_col, ancho_img_col]
            
            # Tabla principal con diseño PROFESIONAL y OPTIMIZADO - SIN PADDING
            # rowHeights=None para que el contenedor se ajuste automáticamente al contenido
            table = Table(data, colWidths=col_widths)
            table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),  # Centrado vertical para alinear imagen y textos
                # PADDING COMPLETAMENTE ELIMINADO
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                # Fondo blanco
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
                # Borde elegante
                ('BOX', (0, 0), (-1, -1), config_diseno.get('grosor_borde', 2), colors.HexColor(config_diseno.get('color_borde', '#e94560'))),
                ('ROUNDEDCORNERS', [10, 10, 10, 10]),
            ]))
            
            # Para 2 productos por página, asegurar que la tabla use todo el ancho y esté centrada
            if productos_por_pagina == 2:
                table.hAlign = 'CENTER'  # Centrar la tabla horizontalmente
            
            elements.append(table)
            
            # Espacio entre productos (excepto después del último)
            if idx < len(productos_pagina) - 1:
                elements.append(Spacer(1, espacio_entre_productos))
        
        # Page break después de cada grupo (SOLO si hay más productos después)
        if i + productos_por_pagina < len(productos_lista):
            elements.append(PageBreak())
    
    # Generar PDF con callback onPage para agregar fondos
    callback_fondo = get_fondo_pagina_callback(catalogo_dir)
    doc.build(elements, onFirstPage=callback_fondo, onLaterPages=callback_fondo)
    
    # Si hay PDFs personalizados, combinarlos
    portada_pdf = os.path.join(catalogo_dir, 'portada.pdf')
    bordes_pdf = os.path.join(catalogo_dir, 'bordes.pdf')
    
    tiene_portada_pdf = os.path.exists(portada_pdf)
    tiene_bordes_pdf = os.path.exists(bordes_pdf)
    
    if tiene_portada_pdf or tiene_bordes_pdf:
        # Combinar PDFs
        buffer.seek(0)
        catalogo_generado = PdfReader(buffer)
        writer = PdfWriter()
        
        # 1. Agregar portada PDF si existe
        if tiene_portada_pdf:
            try:
                portada_reader = PdfReader(portada_pdf)
                writer.add_page(portada_reader.pages[0])
            except Exception as e:
                print(f"Error al agregar portada PDF: {e}")
        
        # 2. Procesar páginas del catálogo generado
        for i, page in enumerate(catalogo_generado.pages):
            if i == 0 and tiene_portada_pdf:
                continue
            
            if tiene_bordes_pdf and i > 0:
                try:
                    bordes_reader = PdfReader(bordes_pdf)
                    bordes_page = bordes_reader.pages[0]
                    bordes_page.merge_page(page)
                    writer.add_page(bordes_page)
                except Exception as e:
                    print(f"Error al aplicar bordes PDF: {e}")
                    writer.add_page(page)
            else:
                writer.add_page(page)
        
        final_buffer = io.BytesIO()
        writer.write(final_buffer)
        final_buffer.seek(0)
        
        response = HttpResponse(final_buffer, content_type='application/pdf')
        filename = f"catalogo_{config_diseno.get('nombre_negocio', 'empresa').replace(' ', '_').lower()}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    
    # Si no hay PDFs personalizados, usar el generado normalmente
    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/pdf')
    filename = f"catalogo_{config_diseno.get('nombre_negocio', 'empresa').replace(' ', '_').lower()}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@login_required
def personalizar_catalogo(request):
    """Vista para subir y gestionar las imágenes personalizadas del catálogo"""
    
    catalogo_dir = os.path.join(settings.MEDIA_ROOT, f'catalogo_tenant_{request.empresa.id}')
    os.makedirs(catalogo_dir, exist_ok=True)
    
    config_file = os.path.join(catalogo_dir, 'config_diseno.json')
    
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config_diseno = json.load(f)
    else:
        config_diseno = {
            'color_principal': '#e94560',
            'color_precio': '#27ae60',
            'color_texto': '#555555',
            'color_titulo': '#1a1a2e',
            'color_borde': '#e94560',
            'grosor_borde': 2,
            'estilo_precio': 'moderno',
            'productos_por_pagina': 3,
            'ancho_imagen': 7,
            'alto_producto': 9,
            'espaciado_productos': 0.5,
            'alineacion_imagen': 'alternada',
            'tamano_titulo': 18,
            'tamano_precio': 24,
            'tamano_descripcion': 11,
            'fuente_titulo': 'Helvetica-Bold',
            'fuente_texto': 'Helvetica',
            'nombre_negocio': 'Mi Tienda',
            'subtitulo_negocio': 'Productos de Excelente Calidad',
            'lema_negocio': 'Calidad y Estilo'
        }
    
    # Buscar archivos en diferentes formatos
    portada_existe = False
    bordes_existe = False
    portada_url = None
    bordes_url = None
    portada_formato = None
    bordes_formato = None
    portada_es_pdf = False
    bordes_es_pdf = False
    
    for ext in ['pdf', 'png', 'jpg', 'jpeg']:
        path = os.path.join(catalogo_dir, f'portada.{ext}')
        if os.path.exists(path):
            portada_existe = True
            portada_formato = ext.upper()
            portada_es_pdf = (ext == 'pdf')
            portada_url = f"{settings.MEDIA_URL}catalogo_tenant_{request.empresa.id}/portada.{ext}"
            break
    
    for ext in ['pdf', 'png', 'jpg', 'jpeg']:
        path = os.path.join(catalogo_dir, f'bordes.{ext}')
        if os.path.exists(path):
            bordes_existe = True
            bordes_formato = ext.upper()
            bordes_es_pdf = (ext == 'pdf')
            bordes_url = f"{settings.MEDIA_URL}catalogo_tenant_{request.empresa.id}/bordes.{ext}"
            break
    
    if request.method == 'POST':
        if 'portada' in request.FILES:
            archivo = request.FILES['portada']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension in ['jpg', 'jpeg', 'png', 'pdf']:
                for ext in ['jpg', 'jpeg', 'png', 'pdf']:
                    path = os.path.join(catalogo_dir, f'portada.{ext}')
                    if os.path.exists(path):
                        os.remove(path)
                
                if extension == 'jpeg':
                    extension = 'jpg'
                ruta_destino = os.path.join(catalogo_dir, f'portada.{extension}')
                
                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                
                messages.success(request, f'Portada actualizada correctamente ({extension.upper()})')
            else:
                messages.error(request, 'Solo se permiten archivos JPG, PNG o PDF')
        
        elif 'bordes' in request.FILES:
            archivo = request.FILES['bordes']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension in ['jpg', 'jpeg', 'png', 'pdf']:
                for ext in ['jpg', 'jpeg', 'png', 'pdf']:
                    path = os.path.join(catalogo_dir, f'bordes.{ext}')
                    if os.path.exists(path):
                        os.remove(path)
                
                if extension == 'jpeg':
                    extension = 'jpg'
                ruta_destino = os.path.join(catalogo_dir, f'bordes.{extension}')
                
                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                
                messages.success(request, f'Bordes actualizados correctamente ({extension.upper()})')
            else:
                messages.error(request, 'Solo se permiten archivos JPG, PNG o PDF')
        
        elif 'fondo_precio' in request.FILES:
            archivo = request.FILES['fondo_precio']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension in ['jpg', 'jpeg', 'png']:
                for ext in ['jpg', 'jpeg', 'png']:
                    path = os.path.join(catalogo_dir, f'fondo_precio.{ext}')
                    if os.path.exists(path):
                        os.remove(path)
                
                if extension == 'jpeg':
                    extension = 'jpg'
                ruta_destino = os.path.join(catalogo_dir, f'fondo_precio.{extension}')
                
                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                
                messages.success(request, f'Fondo de precio actualizado correctamente')
            else:
                messages.error(request, 'Solo se permiten archivos JPG o PNG')
        
        elif 'guardar_colores' in request.POST:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_diseno = json.load(f)
            else:
                config_diseno = {}
            
            config_diseno['color_principal'] = request.POST.get('color_principal', '#e94560')
            config_diseno['color_precio'] = request.POST.get('color_precio', '#27ae60')
            config_diseno['color_texto'] = request.POST.get('color_texto', '#555555')
            config_diseno['color_titulo'] = request.POST.get('color_titulo', '#1a1a2e')
            config_diseno['color_borde'] = request.POST.get('color_borde', '#e94560')
            config_diseno['grosor_borde'] = int(request.POST.get('grosor_borde', 2))
            config_diseno['estilo_precio'] = request.POST.get('estilo_precio', 'moderno')
            config_diseno['tamano_titulo'] = int(request.POST.get('tamano_titulo', 18))
            config_diseno['tamano_precio'] = int(request.POST.get('tamano_precio', 24))
            config_diseno['tamano_descripcion'] = int(request.POST.get('tamano_descripcion', 11))
            
            # Incorporamos los campos de texto
            config_diseno['nombre_negocio'] = request.POST.get('nombre_negocio', 'Mi Tienda')
            config_diseno['subtitulo_negocio'] = request.POST.get('subtitulo_negocio', 'Productos de Excelente Calidad')
            config_diseno['lema_negocio'] = request.POST.get('lema_negocio', 'Calidad y Estilo')
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_diseno, f, indent=4, ensure_ascii=False)
            
            messages.success(request, 'Configuración de diseño guardada correctamente')
        
        elif 'guardar_layout' in request.POST:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_diseno = json.load(f)
            else:
                config_diseno = {}
            
            config_diseno['productos_por_pagina'] = int(request.POST.get('productos_por_pagina', 3))
            config_diseno['ancho_imagen'] = float(request.POST.get('ancho_imagen', 7))
            config_diseno['alto_producto'] = float(request.POST.get('alto_producto', 9))
            config_diseno['espaciado_productos'] = float(request.POST.get('espaciado_productos', 0.5))
            config_diseno['alineacion_imagen'] = request.POST.get('alineacion_imagen', 'alternada')
            
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config_diseno, f, indent=4, ensure_ascii=False)
            
            messages.success(request, 'Configuración de layout guardada correctamente')
        
        elif 'eliminar_fondo_precio' in request.POST:
            for ext in ['jpg', 'jpeg', 'png']:
                path = os.path.join(catalogo_dir, f'fondo_precio.{ext}')
                if os.path.exists(path):
                    os.remove(path)
            messages.success(request, 'Fondo de precio eliminado correctamente')
        
        elif 'fuente_titulo' in request.FILES:
            archivo = request.FILES['fuente_titulo']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension in ['ttf', 'otf']:
                fonts_dir = os.path.join(catalogo_dir, 'fonts')
                os.makedirs(fonts_dir, exist_ok=True)
                
                ruta_destino = os.path.join(fonts_dir, f'titulo.{extension}')
                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_diseno = json.load(f)
                else:
                    config_diseno = {}
                
                config_diseno['fuente_titulo'] = 'TituloCustom'
                config_diseno['fuente_titulo_path'] = ruta_destino
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_diseno, f, indent=4, ensure_ascii=False)
                
                messages.success(request, f'Fuente para títulos subida correctamente')
            else:
                messages.error(request, 'Solo se permiten archivos TTF u OTF')
        
        elif 'fuente_texto' in request.FILES:
            archivo = request.FILES['fuente_texto']
            extension = archivo.name.split('.')[-1].lower()
            
            if extension in ['ttf', 'otf']:
                fonts_dir = os.path.join(catalogo_dir, 'fonts')
                os.makedirs(fonts_dir, exist_ok=True)
                
                ruta_destino = os.path.join(fonts_dir, f'texto.{extension}')
                with open(ruta_destino, 'wb+') as destino:
                    for chunk in archivo.chunks():
                        destino.write(chunk)
                
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_diseno = json.load(f)
                else:
                    config_diseno = {}
                
                config_diseno['fuente_texto'] = 'TextoCustom'
                config_diseno['fuente_texto_path'] = ruta_destino
                
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_diseno, f, indent=4, ensure_ascii=False)
                
                messages.success(request, f'Fuente para texto subida correctamente')
            else:
                messages.error(request, 'Solo se permiten archivos TTF u OTF')
        
        elif 'eliminar_portada' in request.POST:
            for ext in ['jpg', 'jpeg', 'png', 'pdf']:
                path = os.path.join(catalogo_dir, f'portada.{ext}')
                if os.path.exists(path):
                    os.remove(path)
            messages.success(request, 'Portada eliminada correctamente')
        
        elif 'eliminar_bordes' in request.POST:
            for ext in ['jpg', 'jpeg', 'png', 'pdf']:
                path = os.path.join(catalogo_dir, f'bordes.{ext}')
                if os.path.exists(path):
                    os.remove(path)
            messages.success(request, 'Bordes eliminados correctamente')
        
        return redirect('personalizar_catalogo')
    
    # Buscar imagen de fondo para precio
    fondo_precio_existe = False
    fondo_precio_url = None
    for ext in ['png', 'jpg', 'jpeg']:
        path = os.path.join(catalogo_dir, f'fondo_precio.{ext}')
        if os.path.exists(path):
            fondo_precio_existe = True
            fondo_precio_url = f"{settings.MEDIA_URL}catalogo/fondo_precio.{ext}"
            break
    
    # Buscar fuentes personalizadas
    fonts_dir = os.path.join(catalogo_dir, 'fonts')
    fuente_titulo_existe = False
    fuente_texto_existe = False
    fuente_titulo_nombre = 'Helvetica-Bold (por defecto)'
    fuente_texto_nombre = 'Helvetica (por defecto)'
    
    if os.path.exists(fonts_dir):
        for ext in ['ttf', 'otf']:
            titulo_path = os.path.join(fonts_dir, f'titulo.{ext}')
            if os.path.exists(titulo_path):
                fuente_titulo_existe = True
                fuente_titulo_nombre = f'Fuente personalizada ({ext.upper()})'
                break
        
        for ext in ['ttf', 'otf']:
            texto_path = os.path.join(fonts_dir, f'texto.{ext}')
            if os.path.exists(texto_path):
                fuente_texto_existe = True
                fuente_texto_nombre = f'Fuente personalizada ({ext.upper()})'
                break
    
    context = {
        'portada_existe': portada_existe,
        'bordes_existe': bordes_existe,
        'portada_url': portada_url,
        'bordes_url': bordes_url,
        'portada_formato': portada_formato,
        'bordes_formato': bordes_formato,
        'portada_es_pdf': portada_es_pdf,
        'bordes_es_pdf': bordes_es_pdf,
        'fondo_precio_existe': fondo_precio_existe,
        'fondo_precio_url': fondo_precio_url,
        'fuente_titulo_existe': fuente_titulo_existe,
        'fuente_texto_existe': fuente_texto_existe,
        'fuente_titulo_nombre': fuente_titulo_nombre,
        'fuente_texto_nombre': fuente_texto_nombre,
        'config_diseno': config_diseno,
    }
    
    return render(request, 'catalogos/personalizar_catalogo.html', context)