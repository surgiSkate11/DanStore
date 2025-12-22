import gspread
from google.oauth2.service_account import Credentials
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django.db import models
from django.utils import timezone
from productos.models import Producto, TipoPrenda
import os
import json
import re


def limpiar_precio(valor):
    """
    Limpia el formato de precio: $3.50 → 3.50
    """
    if not valor:
        return None
    
    # Si ya es número, devolverlo
    if isinstance(valor, (int, float)):
        return valor
    
    # Si es string, limpiar símbolos
    if isinstance(valor, str):
        # Eliminar $, espacios, comas
        valor_limpio = re.sub(r'[$,\s]', '', valor.strip())
        try:
            return float(valor_limpio)
        except ValueError:
            return None
    
    return None


def conectar_google_sheets():
    """Conecta con Google Sheets usando credenciales (solo lectura)"""
    try:
        # Configurar scopes (lectura y escritura)
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',  # Lectura y escritura
            'https://www.googleapis.com/auth/drive'  # Lectura y escritura Drive
        ]

        credentials_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if credentials_json:
            credentials_dict = json.loads(credentials_json)
            creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        else:
            credentials_path = os.path.join(settings.BASE_DIR, 'credentials.json')
            if not os.path.exists(credentials_path):
                return None, "No se encontró el archivo credentials.json"
            creds = Credentials.from_service_account_file(credentials_path, scopes=scopes)

        client = gspread.authorize(creds)
        return client, None
    except Exception as e:
        return None, f"Error de conexión: {str(e)}"


@login_required
def sincronizar_sheets(request):
    """Vista para sincronizar productos desde Google Sheets"""
    
    if request.method == 'POST':
        sheet_url = request.POST.get('sheet_url', '').strip()
        rango_celdas = request.POST.get('rango_celdas', '').strip()
        
        if not sheet_url:
            messages.error(request, 'Debes proporcionar la URL de Google Sheets')
            return redirect('sincronizar_sheets')
        
        # Guardar URL del sheet para uso posterior
        guardar_sheet_url(sheet_url)
        
        # Conectar con Google Sheets
        client, error = conectar_google_sheets()
        if error:
            messages.error(request, f'{error}')
            return redirect('sincronizar_sheets')
        
        try:
            # Abrir la hoja
            sheet = client.open_by_url(sheet_url)
            worksheet = sheet.get_worksheet(0)  # Primera hoja
            
            # Obtener valores directamente (como lista de listas)
            if rango_celdas:
                valores = worksheet.get(rango_celdas)
            else:
                valores = worksheet.get_all_values()
            
            if not valores or len(valores) < 2:
                messages.error(request, 'No se encontraron datos')
                return redirect('sincronizar_sheets')
            
            productos_creados = 0
            productos_actualizados = 0
            errores = []
            
            # Primera fila = encabezados
            headers = valores[0]
            
            # Buscar índices de columnas por NOMBRE (no por posición)
            # El orden de las columnas puede cambiar, pero los nombres deben existir
            idx_tipo = next((i for i, h in enumerate(headers) if 'tipo' in h.lower()), None)
            idx_categoria = next((i for i, h in enumerate(headers) if 'categoria' in h.lower() or 'categoría' in h.lower()), None)
            idx_marca = next((i for i, h in enumerate(headers) if 'marca' in h.lower()), None)
            idx_color = next((i for i, h in enumerate(headers) if 'color' in h.lower()), None)
            idx_talla = next((i for i, h in enumerate(headers) if 'talla' in h.lower()), None)
            idx_precio = next((i for i, h in enumerate(headers) if 'precio venta' in h.lower()), None)  # Columna "Precio Venta"
            idx_observacion = next((i for i, h in enumerate(headers) if 'observación' in h.lower() or 'observacion' in h.lower()), None)
            idx_vendido_a = next((i for i, h in enumerate(headers) if 'vendido' in h.lower()), None)  # Columna "Vendido a"
            idx_precio_real = next((i for i, h in enumerate(headers) if 'precio real' in h.lower()), None)  # Columna "Precio Real"
            idx_estado = next((i for i, h in enumerate(headers) if 'estado' in h.lower()), None)  # Columna "Estado"
            
            if idx_tipo is None or idx_categoria is None or idx_talla is None or idx_precio is None:
                messages.error(request, f'Faltan columnas obligatorias. Ajusta el rango para incluir: Tipo, Categoría, Talla, Precio Venta')
                return redirect('sincronizar_sheets')
            
            # VALIDACIÓN: Verificar si hay productos existentes y advertir sobre columnas faltantes
            productos_existentes_count = Producto.objects.filter(google_sheets_row__isnull=False).count()
            
            if productos_existentes_count > 0:
                # Si ya hay productos sincronizados, validar que no falten columnas importantes
                columnas_faltantes = []
                if idx_estado is None:
                    columnas_faltantes.append('Estado')
                if idx_vendido_a is None:
                    columnas_faltantes.append('Vendido A')
                if idx_precio_real is None:
                    columnas_faltantes.append('Precio Real')
                
                if columnas_faltantes:
                    messages.warning(request, f'Columnas no encontradas: {", ".join(columnas_faltantes)}. Verifica que los nombres de las columnas sean correctos. Esto puede causar pérdida de información.')
                    # Preguntar al usuario si desea continuar
                    if not request.POST.get('confirmar_sin_columnas'):
                        messages.error(request, f'Sincronización cancelada. Tienes {productos_existentes_count} productos sincronizados que podrían perder información si continúas sin las columnas: {", ".join(columnas_faltantes)}')
                        return redirect('sincronizar_sheets')
            
            # OPTIMIZACIÓN: Obtener todos los productos existentes de una sola vez
            productos_existentes = {p.google_sheets_row: p for p in Producto.objects.filter(google_sheets_row__isnull=False).select_related('tipo_prenda')}
            
            # OPTIMIZACIÓN: Obtener o crear todos los tipos de prenda de una vez
            tipos_prenda_cache = {tp.nombre: tp for tp in TipoPrenda.objects.all()}
            tipos_prenda_nuevos = set()
            
            # Listas para bulk operations
            productos_a_crear = []
            productos_a_actualizar = []
            
            for idx, fila in enumerate(valores[1:], start=2):  # Empezar desde fila 2
                try:
                    # Obtener valores usando los índices encontrados
                    tipo_str = str(fila[idx_tipo]).strip() if len(fila) > idx_tipo and fila[idx_tipo] else ''
                    categoria_str = str(fila[idx_categoria]).strip() if len(fila) > idx_categoria and fila[idx_categoria] else ''
                    marca = str(fila[idx_marca]).strip() if idx_marca is not None and len(fila) > idx_marca and fila[idx_marca] else ''
                    color = str(fila[idx_color]).strip() if idx_color is not None and len(fila) > idx_color and fila[idx_color] else ''
                    talla = str(fila[idx_talla]).strip() if len(fila) > idx_talla and fila[idx_talla] else ''
                    precio_venta = limpiar_precio(fila[idx_precio]) if len(fila) > idx_precio else None
                    observacion = str(fila[idx_observacion]).strip() if idx_observacion is not None and len(fila) > idx_observacion and fila[idx_observacion] else ''
                    vendido_a = str(fila[idx_vendido_a]).strip() if idx_vendido_a is not None and len(fila) > idx_vendido_a and fila[idx_vendido_a] else ''
                    precio_real = limpiar_precio(fila[idx_precio_real]) if idx_precio_real is not None and len(fila) > idx_precio_real else None
                    estado_sheets = str(fila[idx_estado]).strip().lower() if idx_estado is not None and len(fila) > idx_estado and fila[idx_estado] else ''
                    
                    # Validar SOLO campos obligatorios: Tipo, Categoría, Talla, Precio
                    if not tipo_str or not categoria_str or not talla or not precio_venta:
                        errores.append(f"Fila {idx}: Faltan datos obligatorios (Tipo: '{tipo_str}', Categoría: '{categoria_str}', Talla: '{talla}', Precio: '{precio_venta}')")
                        continue
                    
                    # OPTIMIZACIÓN: Obtener o crear tipo de prenda usando cache
                    if tipo_str not in tipos_prenda_cache:
                        if tipo_str not in tipos_prenda_nuevos:
                            tipo_prenda = TipoPrenda.objects.create(nombre=tipo_str)
                            tipos_prenda_cache[tipo_str] = tipo_prenda
                            tipos_prenda_nuevos.add(tipo_str)
                    tipo_prenda = tipos_prenda_cache[tipo_str]
                    
                    # Mapear categoría del Sheet al modelo
                    mapeo_categoria = {
                        'bebé': 'bebe',
                        'bebe': 'bebe',
                        'niña': 'nina',
                        'nina': 'nina',
                        'niño': 'nino',
                        'nino': 'nino',
                        'joven': 'joven',
                        'adolescente': 'joven',
                        'mujer': 'adulto_mujer',
                        'hombre': 'adulto_hombre'
                    }
                    categoria_grupo = mapeo_categoria.get(categoria_str.lower(), 'adulto_mujer')
                    
                    # Rango de edad es el mismo valor de talla
                    rango_edad = talla
                    
                    # Determinar estado desde la columna "Estado" del Sheet
                    mapeo_estado = {
                        'disponible': 'disponible',
                        'separado': 'separado',
                        'vendido': 'vendido'
                    }
                    
                    if estado_sheets and estado_sheets in mapeo_estado:
                        estado = mapeo_estado[estado_sheets]
                    else:
                        # Fallback: si tiene cliente → vendido, si está vacío → disponible
                        estado = 'vendido' if vendido_a else 'disponible'
                    
                    # Generar descripción automática
                    descripcion_partes = []
                    if marca:
                        descripcion_partes.append(f"Marca: {marca}")
                    if color:
                        descripcion_partes.append(f"Color: {color}")
                    if observacion:
                        descripcion_partes.append(observacion)
                    descripcion = " | ".join(descripcion_partes)
                    
                    # Buscar si ya existe producto con este número de fila
                    producto_existente = productos_existentes.get(idx)
                    
                    if producto_existente:
                        # OPTIMIZACIÓN: Solo actualizar si hay cambios reales
                        cambios_detectados = (
                            producto_existente.tipo_prenda != tipo_prenda or
                            producto_existente.marca != marca or
                            producto_existente.color != color or
                            producto_existente.categoria_grupo != categoria_grupo or
                            producto_existente.rango_edad != rango_edad or
                            producto_existente.precio != precio_venta or
                            producto_existente.precio_real != precio_real or
                            producto_existente.descripcion != descripcion or
                            producto_existente.vendido_a != vendido_a or
                            producto_existente.estado != estado
                        )
                        
                        if cambios_detectados:
                            # IMPORTANTE: Si el producto cambió de 'vendido' a otro estado,
                            # eliminar las ventas/facturas asociadas
                            if producto_existente.estado == 'vendido' and estado != 'vendido':
                                # Importar modelos de ventas
                                from ventas.models import DetalleVenta, Venta
                                
                                # Buscar detalles de venta asociados a este producto
                                detalles = DetalleVenta.objects.filter(producto=producto_existente)
                                
                                # Obtener las ventas asociadas antes de eliminar los detalles
                                ventas_ids = list(detalles.values_list('venta_id', flat=True).distinct())
                                
                                # Eliminar los detalles
                                detalles.delete()
                                
                                # Eliminar ventas que quedaron sin productos
                                for venta_id in ventas_ids:
                                    try:
                                        venta = Venta.objects.get(id=venta_id)
                                        # Si la venta ya no tiene productos, eliminarla
                                        if not venta.detalles.exists():
                                            venta.delete()
                                        else:
                                            # Si aún tiene productos, recalcular totales
                                            venta.calcular_total()
                                    except Venta.DoesNotExist:
                                        pass
                            
                            # Actualizar solo si hubo cambios
                            producto_existente.tipo_prenda = tipo_prenda
                            producto_existente.marca = marca
                            producto_existente.color = color
                            producto_existente.categoria_grupo = categoria_grupo
                            producto_existente.rango_edad = rango_edad
                            producto_existente.precio = precio_venta
                            producto_existente.precio_real = precio_real
                            producto_existente.descripcion = descripcion
                            producto_existente.vendido_a = vendido_a
                            producto_existente.estado = estado
                            producto_existente.sincronizado_sheets = True
                            productos_a_actualizar.append(producto_existente)
                    else:
                        # Preparar producto nuevo para bulk_create
                        productos_a_crear.append(
                            Producto(
                                tipo_prenda=tipo_prenda,
                                marca=marca,
                                color=color,
                                categoria_grupo=categoria_grupo,
                                rango_edad=rango_edad,
                                precio=precio_venta,
                                precio_real=precio_real,
                                descripcion=descripcion,
                                vendido_a=vendido_a,
                                estado=estado,
                                google_sheets_row=idx,
                                sincronizado_sheets=True,
                            )
                        )
                    
                except Exception as e:
                    errores.append(f"Fila {idx}: {str(e)}")
            
            # OPTIMIZACIÓN: Ejecutar bulk operations (solo 2 queries en total)
            if productos_a_crear:
                Producto.objects.bulk_create(productos_a_crear, batch_size=500)
                productos_creados = len(productos_a_crear)
            
            if productos_a_actualizar:
                Producto.objects.bulk_update(
                    productos_a_actualizar,
                    ['tipo_prenda', 'marca', 'color', 'categoria_grupo', 'rango_edad', 
                     'precio', 'precio_real', 'descripcion', 'vendido_a', 'estado', 'sincronizado_sheets'],
                    batch_size=500
                )
                productos_actualizados = len(productos_a_actualizar)
            
            # Guardar configuración de Sheets para sincronización bidireccional
            config_data = {
                'sheet_url': sheet_url,
                'rango_celdas': rango_celdas,
                'ultima_sincronizacion': str(timezone.now())
            }
            config_file = os.path.join(settings.MEDIA_ROOT, 'sheets_config.json')
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, 'w') as f:
                json.dump(config_data, f)
            
            # ========================================
            # MENSAJES DE RESULTADO DE PRODUCTOS
            # ========================================
            # Mostrar PRIMERO los resultados de sincronización de productos
            if productos_creados > 0 and productos_actualizados > 0:
                messages.success(request, f'Sincronización completada: {productos_creados} productos nuevos creados y {productos_actualizados} actualizados')
            elif productos_creados > 0:
                messages.success(request, f'{productos_creados} producto(s) nuevo(s) creado(s) correctamente')
            elif productos_actualizados > 0:
                messages.success(request, f'{productos_actualizados} producto(s) actualizado(s) correctamente')
            else:
                # No hubo cambios
                messages.info(request, 'Sincronización completada. Todos los productos ya están actualizados')
            
            if errores:
                for error in errores[:10]:  # Mostrar primeros 10 errores directamente
                    messages.warning(request, f'{error}')
            
            # ========================================
            # LIMPIEZA DE CONSISTENCIA
            # ========================================
            # Eliminar facturas de productos que ya NO están en estado 'vendido'
            from ventas.models import DetalleVenta, Venta
            
            # Buscar productos en estado 'separado' o 'disponible' que tengan facturas
            productos_no_vendidos = Producto.objects.filter(
                estado__in=['separado', 'disponible']
            ).values_list('id', flat=True)
            
            # Buscar detalles de venta de estos productos
            detalles_inconsistentes = DetalleVenta.objects.filter(
                producto_id__in=productos_no_vendidos
            )
            
            if detalles_inconsistentes.exists():
                # Obtener ventas asociadas antes de eliminar
                ventas_ids = list(detalles_inconsistentes.values_list('venta_id', flat=True).distinct())
                cantidad_detalles = detalles_inconsistentes.count()
                
                # Eliminar detalles inconsistentes
                detalles_inconsistentes.delete()
                
                # Limpiar ventas huérfanas o recalcular totales
                ventas_eliminadas = 0
                ventas_actualizadas = 0
                for venta_id in ventas_ids:
                    try:
                        venta = Venta.objects.get(id=venta_id)
                        if not venta.detalles.exists():
                            venta.delete()
                            ventas_eliminadas += 1
                        else:
                            venta.calcular_total()
                            ventas_actualizadas += 1
                    except Venta.DoesNotExist:
                        pass
                
                # Mostrar mensaje de limpieza
                if ventas_eliminadas > 0:
                    messages.info(request, f'Limpieza: {ventas_eliminadas} factura(s) eliminada(s) porque los productos cambiaron a estado "separado" o "disponible"')
                if ventas_actualizadas > 0:
                    messages.info(request, f'Limpieza: {ventas_actualizadas} factura(s) actualizada(s) después de eliminar productos no vendidos')
            
            # ========================================
            # SINCRONIZACIÓN AUTOMÁTICA DE FACTURAS
            # ========================================
            # Después de sincronizar productos, crear facturas automáticamente
            # para productos vendidos (con vendido_a)
            estadisticas_ventas = sincronizar_ventas_desde_sheets()
            
            # Mostrar resultados de sincronización de facturas SOLO si hay actividad
            if estadisticas_ventas['ventas_creadas'] > 0:
                messages.success(request, f"Facturas: {estadisticas_ventas['ventas_creadas']} factura(s) creada(s) automáticamente con {estadisticas_ventas['productos_nuevos']} producto(s)")
            
            if estadisticas_ventas['clientes_creados'] > 0:
                messages.success(request, f"Clientes: {estadisticas_ventas['clientes_creados']} cliente(s) nuevo(s) registrado(s)")
            
            # Solo mostrar errores REALES como warning
            if estadisticas_ventas['errores']:
                for error in estadisticas_ventas['errores'][:3]:  # Mostrar primeros 3 errores
                    messages.warning(request, f"Facturas: {error}")
            
            # Nota: NO mostrar mensaje "No hay productos nuevos para facturar" 
            # cuando solo se están actualizando productos existentes
            
        except Exception as e:
            messages.error(request, f'Error al procesar Google Sheets: {str(e)}')
        
        return redirect('sincronizar_sheets')
    
    # GET: Mostrar formulario
    # Contar productos con y sin imagen
    total_productos = Producto.objects.filter(sincronizado_sheets=True).count()
    # Productos sin foto: campo imagen vacío o NULL
    productos_sin_foto = Producto.objects.filter(
        sincronizado_sheets=True
    ).filter(
        models.Q(imagen='') | models.Q(imagen__isnull=True)
    ).count()
    productos_con_foto = total_productos - productos_sin_foto
    
    context = {
        'total_productos': total_productos,
        'productos_sin_foto': productos_sin_foto,
        'productos_con_foto': productos_con_foto,
        'tiene_credentials': os.path.exists(os.path.join(settings.BASE_DIR, 'credentials.json')),
    }
    
    return render(request, 'productos/sincronizar_sheets.html', context)


def determinar_categoria(tipo_str, talla, observacion=''):
    """Determina la categoría según tipo, talla y observación"""
    tipo_lower = tipo_str.lower()
    talla_lower = str(talla).lower()
    obs_lower = observacion.lower()
    
    # Buscar palabras clave
    if 'bebé' in obs_lower or 'bebe' in obs_lower or 'meses' in talla_lower:
        return 'bebe'
    elif 'niño' in obs_lower or 'niña' in obs_lower or any(f'{i} año' in obs_lower for i in range(1, 12)):
        if 'niña' in obs_lower:
            return 'nina'
        return 'nino'
    elif 'joven' in obs_lower or 'adolescente' in obs_lower or any(str(i) in talla_lower for i in range(12, 18)):
        return 'joven'
    elif 'mujer' in obs_lower or 'dama' in obs_lower:
        return 'adulto_mujer'
    elif 'hombre' in obs_lower or 'caballero' in obs_lower:
        return 'adulto_hombre'
    else:
        # Por defecto según talla
        if talla_lower in ['xs', 's', 'm', 'l', 'xl', 'xxl', 'xxxl']:
            return 'adulto_mujer'  # Por defecto
        return 'adulto_hombre'


def mapear_talla(talla, categoria):
    """Mapea la talla según la categoría"""
    talla_str = str(talla).strip()
    
    if categoria == 'bebe':
        # Buscar patrones de meses
        if '0-3' in talla_str or '0_3' in talla_str:
            return '0-3'
        elif '3-6' in talla_str or '3_6' in talla_str:
            return '3-6'
        elif '6-9' in talla_str or '6_9' in talla_str:
            return '6-9'
        elif '9-12' in talla_str or '9_12' in talla_str:
            return '9-12'
    
    elif categoria in ['nino', 'nina']:
        # Buscar número de años (1-11)
        for i in range(1, 12):
            if str(i) in talla_str:
                return str(i)
    
    elif categoria == 'joven':
        # Buscar número de años (12-17)
        for i in range(12, 18):
            if str(i) in talla_str:
                return str(i)
    
    elif categoria in ['adulto_hombre', 'adulto_mujer']:
        # Tallas estándar
        talla_upper = talla_str.upper()
        tallas_validas = ['XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL']
        for talla_valida in tallas_validas:
            if talla_valida in talla_upper:
                return talla_valida
    
    return talla_str  # Devolver como está si no se puede mapear


@login_required
def subir_fotos_productos(request):
    """Vista para subir fotos a productos sincronizados desde Sheets"""
    
    if request.method == 'POST':
        producto_id = request.POST.get('producto_id')
        imagen = request.FILES.get('imagen')
        
        if producto_id and imagen:
            try:
                producto = Producto.objects.get(id=producto_id, sincronizado_sheets=True)
                producto.imagen = imagen
                producto.save()
                messages.success(request, f'Foto subida para {producto.tipo_prenda}')
            except Producto.DoesNotExist:
                messages.error(request, 'Producto no encontrado')
        
        return redirect('subir_fotos_productos')
    
    # GET: Listar productos sin foto (campo vacío o NULL) - Limitar a 100 más recientes
    productos_sin_foto = Producto.objects.select_related('tipo_prenda').filter(
        sincronizado_sheets=True
    ).filter(
        models.Q(imagen='') | models.Q(imagen__isnull=True)
    ).exclude(estado='vendido').order_by('-creado_en')[:100]
    
    context = {
        'productos': productos_sin_foto,
    }
    
    return render(request, 'productos/subir_fotos.html', context)


def agregar_cliente_a_sheets(nombre_cliente, sheet_url=None):
    """
    Agrega un nuevo cliente al Google Sheets en la columna de validación de datos.
    Esto permite que aparezca en el dropdown del campo 'vendido_a' en futuros productos.
    
    Args:
        nombre_cliente: Nombre del cliente a agregar
        sheet_url: URL del Google Sheet (opcional, se puede guardar en settings)
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Conectar con Google Sheets (ahora con permisos de escritura)
        client, error = conectar_google_sheets()
        if error:
            return False, f"Error de conexión: {error}"
        
        # Obtener la URL del sheet (puedes guardarla en settings o pasarla como parámetro)
        if not sheet_url:
            # Intentar obtener de la última sincronización o usar una configuración
            from django.core.cache import cache
            sheet_url = cache.get('last_sheet_url')
            if not sheet_url:
                return False, "No se ha configurado la URL del Google Sheet"
        
        # Abrir el Google Sheet
        sheet = client.open_by_url(sheet_url)
        worksheet = sheet.get_worksheet(0)  # Primera hoja
        
        # Buscar la columna "vendido_a" o "Cliente" en los encabezados
        headers = worksheet.row_values(1)
        
        # Encontrar la columna de clientes
        columna_cliente = None
        for idx, header in enumerate(headers):
            if header.lower() in ['vendido_a', 'cliente', 'vendido a']:
                columna_cliente = idx + 1  # gspread usa índice basado en 1
                break
        
        if not columna_cliente:
            return False, "No se encontró la columna de clientes en el Google Sheet"
        
        # Obtener todos los valores de la columna de clientes (sin header)
        letra_columna = chr(64 + columna_cliente)  # Convertir número a letra (1=A, 2=B, etc.)
        clientes_existentes = worksheet.col_values(columna_cliente)[1:]  # Excluir header
        
        # Verificar si el cliente ya existe
        if nombre_cliente in clientes_existentes:
            return True, f"Cliente '{nombre_cliente}' ya existe en Google Sheets"
        
        # Agregar el nuevo cliente al final de la columna
        # Buscar la primera celda vacía en la columna
        fila_nueva = len([c for c in clientes_existentes if c.strip()]) + 2  # +2 por header y índice base-1
        
        # Agregar el cliente
        worksheet.update_cell(fila_nueva, columna_cliente, nombre_cliente)
        
        return True, f"✅ Cliente '{nombre_cliente}' agregado exitosamente al Google Sheet"
        
    except Exception as e:
        return False, f"Error al agregar cliente: {str(e)}"


def guardar_sheet_url(sheet_url):
    """Guarda la URL del sheet en cache para uso posterior"""
    from django.core.cache import cache
    cache.set('last_sheet_url', sheet_url, timeout=None)  # Sin expiración


def sincronizar_ventas_desde_sheets():
    """
    Sincroniza ventas desde Google Sheets.
    SOLO crea facturas para productos que NO estén ya facturados.
    Esto permite que cada sincronización cree facturas nuevas solo con compras nuevas.
    
    Returns:
        dict: Estadísticas de sincronización (ventas_creadas, productos_nuevos, errores)
    """
    from ventas.models import Cliente, Venta, DetalleVenta
    from decimal import Decimal
    from collections import defaultdict
    
    estadisticas = {
        'ventas_creadas': 0,
        'productos_nuevos': 0,
        'productos_ya_facturados': 0,
        'clientes_creados': 0,
        'mensaje_info': None,
        'errores': []
    }
    
    try:
        # OPTIMIZACIÓN: Obtener productos con estado 'vendido' que NO estén ya en una factura
        # Usar set() para búsqueda O(1) en lugar de lista
        productos_ya_facturados_ids = set(DetalleVenta.objects.values_list('producto_id', flat=True))
        
        # OPTIMIZACIÓN: select_related evita N+1 queries, only() reduce campos cargados
        productos_nuevos = Producto.objects.filter(
            estado='vendido',  # SOLO productos con estado vendido
            vendido_a__isnull=False
        ).exclude(
            vendido_a=''
        ).exclude(
            id__in=productos_ya_facturados_ids
        ).select_related('tipo_prenda').only(
            'id', 'vendido_a', 'precio', 'precio_real', 'tipo_prenda__nombre'
        )
        
        if not productos_nuevos.exists():
            estadisticas['mensaje_info'] = 'No hay productos nuevos para facturar. Todos los productos vendidos ya tienen factura.'
            return estadisticas
        
        # Contar productos ya facturados para estadísticas
        productos_vendidos_total = Producto.objects.filter(
            vendido_a__isnull=False
        ).exclude(vendido_a='').count()
        estadisticas['productos_ya_facturados'] = productos_vendidos_total - productos_nuevos.count()
        estadisticas['productos_nuevos'] = productos_nuevos.count()
        
        # Agrupar productos NUEVOS por cliente
        ventas_por_cliente = defaultdict(list)
        
        for producto in productos_nuevos:
            cliente_nombre = producto.vendido_a.strip()
            ventas_por_cliente[cliente_nombre].append(producto)
        
        # OPTIMIZACIÓN: Obtener o crear todos los clientes de una vez
        clientes_cache = {}
        nombres_clientes = list(ventas_por_cliente.keys())
        clientes_existentes = Cliente.objects.filter(nombre__in=nombres_clientes)
        for cliente in clientes_existentes:
            clientes_cache[cliente.nombre] = cliente
        
        # Crear clientes nuevos en batch
        clientes_nuevos = []
        for nombre in nombres_clientes:
            if nombre not in clientes_cache:
                clientes_nuevos.append(
                    Cliente(
                        nombre=nombre,
                        notas='Cliente creado desde sincronización con Google Sheets'
                    )
                )
        
        if clientes_nuevos:
            Cliente.objects.bulk_create(clientes_nuevos, batch_size=100)
            estadisticas['clientes_creados'] = len(clientes_nuevos)
            # Actualizar cache con clientes nuevos
            for cliente in Cliente.objects.filter(nombre__in=[c.nombre for c in clientes_nuevos]):
                clientes_cache[cliente.nombre] = cliente
        
        # Crear facturas por cada cliente (solo con productos nuevos)
        for cliente_nombre, productos in ventas_por_cliente.items():
            try:
                cliente = clientes_cache[cliente_nombre]
                
                # Crear nueva venta para estos productos (solo se crea cuando hay pago)
                venta = Venta.objects.create(
                    cliente=cliente,
                    notas=''
                )
                
                # Calcular totales y preparar detalles
                subtotal = Decimal('0')
                descuento_total = Decimal('0')
                detalles_a_crear = []
                
                for producto in productos:
                    # Precio oficial/de lista (columna "Precio Venta" del Sheet)
                    precio_venta = producto.precio
                    # Precio realmente pagado (columna "Precio Real" del Sheet)
                    precio_real = producto.precio_real if producto.precio_real else precio_venta
                    
                    # Calcular descuento individual (diferencia entre precio oficial y precio real)
                    if precio_real and precio_real < precio_venta:
                        descuento_individual = precio_venta - precio_real
                        descuento_total += descuento_individual
                    
                    # Preparar detalle para bulk_create
                    detalles_a_crear.append(
                        DetalleVenta(
                            venta=venta,
                            producto=producto,
                            precio_unitario=precio_real
                        )
                    )
                    
                    # Sumar al subtotal (usando precio de venta oficial)
                    subtotal += precio_venta
                
                # OPTIMIZACIÓN: Crear todos los detalles de una vez
                DetalleVenta.objects.bulk_create(detalles_a_crear, batch_size=100)
                
                # Actualizar venta con cálculos
                venta.subtotal = subtotal
                venta.descuento = descuento_total
                venta.total = subtotal - descuento_total + venta.envio + venta.otros_gastos
                venta.save()
                
                estadisticas['ventas_creadas'] += 1
                
            except Exception as e:
                estadisticas['errores'].append(f"Error procesando cliente {cliente_nombre}: {str(e)}")
                continue
        
    except Exception as e:
        estadisticas['errores'].append(f"Error general: {str(e)}")
    
    return estadisticas
