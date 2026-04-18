from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from .models import Producto, TipoPrenda
from .forms import ProductoForm, ProductoFiltroForm
import openpyxl
import csv
import io


@login_required
def lista_productos(request):
    """Vista para listar productos con filtros"""
    from django.core.paginator import Paginator
    
    # OPTIMIZACIÓN: select_related evita N+1, only() carga solo campos necesarios
    productos = Producto.objects.select_related('tipo_prenda').only(
        'id', 'imagen', 'marca', 'color', 'categoria_grupo', 'rango_edad',
        'precio', 'estado', 'descripcion', 'tipo_prenda__nombre'
    )
    
    # Aplicar filtros
    filtro_form = ProductoFiltroForm(request.GET)
    
    if filtro_form.is_valid():
        if filtro_form.cleaned_data.get('categoria_grupo'):
            productos = productos.filter(
                categoria_grupo=filtro_form.cleaned_data['categoria_grupo']
            )
        
        if filtro_form.cleaned_data.get('tipo_prenda'):
            productos = productos.filter(
                tipo_prenda=filtro_form.cleaned_data['tipo_prenda']
            )
        
        if filtro_form.cleaned_data.get('estado'):
            productos = productos.filter(
                estado=filtro_form.cleaned_data['estado']
            )
        
        if filtro_form.cleaned_data.get('busqueda'):
            busqueda = filtro_form.cleaned_data['busqueda']
            productos = productos.filter(
                Q(descripcion__icontains=busqueda)
            )
    
    # Paginación: 52 productos por página (divisible entre 4 columnas)
    paginator = Paginator(productos, 52)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'filtro_form': filtro_form,
    }
    return render(request, 'productos/lista_productos.html', context)


@login_required
def editar_producto(request, pk):
    """Vista para editar un producto existente"""
    producto = get_object_or_404(Producto, pk=pk)
    negocio_tipo = request.user.profile.negocio_tipo if hasattr(request.user, 'profile') else 'ropa'
    
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, instance=producto, negocio_tipo=negocio_tipo)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Producto actualizado exitosamente!')
            return redirect('lista_productos')
    else:
        form = ProductoForm(instance=producto, negocio_tipo=negocio_tipo)
    
    return render(request, 'productos/form_producto.html', {
        'form': form,
        'titulo': 'Editar Producto',
        'producto': producto,
        'negocio_tipo': negocio_tipo
    })


@login_required
def eliminar_producto(request, pk):
    """Vista para eliminar un producto"""
    producto = get_object_or_404(Producto, pk=pk)
    
    if request.method == 'POST':
        producto.delete()
        messages.success(request, '¡Producto eliminado exitosamente!')
        return redirect('lista_productos')
    
    return render(request, 'productos/confirmar_eliminar.html', {
        'producto': producto
    })


@login_required
def cambiar_estado_producto(request, pk):
    """Vista AJAX para cambiar el estado de un producto"""
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=pk)
        nuevo_estado = request.POST.get('estado')
        
        if nuevo_estado in dict(Producto.ESTADO_CHOICES):
            producto.estado = nuevo_estado
            producto.save()
            
            return JsonResponse({
                'success': True,
                'estado': producto.get_estado_display()
            })
    
    return JsonResponse({'success': False}, status=400)


@login_required
def get_rangos_edad(request):
    """Vista AJAX para obtener rangos de edad según categoría"""
    categoria = request.GET.get('categoria')
    
    choices = []
    if categoria == 'bebe':
        choices = Producto.EDAD_BEBE
    elif categoria in ['nino', 'nina']:
        choices = Producto.EDAD_NINO
    elif categoria == 'joven':
        choices = Producto.EDAD_JOVEN
    elif categoria in ['adulto_hombre', 'adulto_mujer']:
        choices = Producto.TALLA_ADULTO
    
    return JsonResponse({
        'choices': [{'value': c[0], 'label': c[1]} for c in choices]
    })


@login_required
def cambiar_categoria_producto(request, pk):
    """Vista AJAX para cambiar la categoría de un producto"""
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=pk)
        nueva_categoria = request.POST.get('categoria_grupo')
        
        if nueva_categoria in dict(Producto.CATEGORIA_CHOICES):
            producto.categoria_grupo = nueva_categoria
            producto.save()
            
            return JsonResponse({
                'success': True,
                'categoria': producto.get_categoria_grupo_display()
            })
    
    return JsonResponse({'success': False}, status=400)


@login_required
def cambiar_talla_producto(request, pk):
    """Vista AJAX para cambiar la talla/edad de un producto"""
    if request.method == 'POST':
        producto = get_object_or_404(Producto, pk=pk)
        nueva_talla = request.POST.get('rango_edad', '')
        
        # Permitir cualquier valor de texto (viene de Google Sheets)
        producto.rango_edad = nueva_talla
        producto.save()
        
        return JsonResponse({
            'success': True,
            'talla': producto.rango_edad
        })
    
    return JsonResponse({'success': False}, status=400)


@login_required
def subir_foto_producto(request, pk):
    """Vista AJAX para subir/actualizar foto de un producto"""
    if request.method == 'POST' and request.FILES.get('imagen'):
        try:
            producto = get_object_or_404(Producto, pk=pk)
            producto.imagen = request.FILES['imagen']
            producto.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Foto actualizada exitosamente',
                'imagen_url': producto.imagen.url if producto.imagen else None
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}'
            }, status=400)
    
    return JsonResponse({'success': False, 'message': 'No se recibió imagen'}, status=400)


@login_required
def crear_producto(request):
    """Vista para crear un nuevo producto"""
    negocio_tipo = request.user.profile.negocio_tipo if hasattr(request.user, 'profile') else 'ropa'
    
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, negocio_tipo=negocio_tipo)
        if form.is_valid():
            producto = form.save()
            messages.success(request, '¡Producto creado exitosamente!')
            return redirect('lista_productos')
    else:
        form = ProductoForm(negocio_tipo=negocio_tipo)
    
    return render(request, 'productos/form_producto.html', {
        'form': form,
        'titulo': 'Crear Nuevo Producto',
        'negocio_tipo': negocio_tipo
    })


# CAMBIO 2: Vistas de importación Excel/CSV
@login_required
def importar_excel(request):
    """
    Acepta .xlsx o .csv
    Columnas esperadas: nombre, categoria_grupo, precio, estado, descripcion
    La fila 1 siempre es cabecera — se ignora automáticamente
    """
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        
        if not archivo:
            messages.error(request, 'Debes seleccionar un archivo.')
            return redirect('importar_excel')
        
        nombre = archivo.name.lower()
        errores = []
        creados = 0
        actualizados = 0

        try:
            # ── EXCEL ──────────────────────────────────────────
            if nombre.endswith('.xlsx') or nombre.endswith('.xls'):
                wb = openpyxl.load_workbook(archivo)
                ws = wb.active
                filas = list(ws.iter_rows(min_row=2, values_only=True))
            
            # ── CSV ────────────────────────────────────────────
            elif nombre.endswith('.csv'):
                contenido = archivo.read().decode('utf-8-sig')
                reader = csv.reader(io.StringIO(contenido))
                next(reader)  # saltar cabecera
                filas = list(reader)
            
            else:
                messages.error(request, 'Formato no soportado. Usa .xlsx o .csv')
                return redirect('importar_excel')

            # ── PROCESAR FILAS ─────────────────────────────────
            for i, fila in enumerate(filas, start=2):
                try:
                    nombre_prod  = str(fila[0]).strip() if fila[0] else None
                    categoria    = str(fila[1]).strip() if len(fila) > 1 and fila[1] else 'adulto_mujer'
                    precio       = float(fila[2]) if len(fila) > 2 and fila[2] else 0
                    estado       = str(fila[3]).strip().lower() if len(fila) > 3 and fila[3] else 'disponible'
                    descripcion  = str(fila[4]).strip() if len(fila) > 4 and fila[4] else ''

                    if not nombre_prod:
                        continue

                    # Validar estado
                    estados_validos = ['disponible', 'separado', 'vendido']
                    if estado not in estados_validos:
                        estado = 'disponible'
                    
                    # Validar categoría
                    categorias_validas = dict(Producto.CATEGORIA_CHOICES)
                    if categoria not in categorias_validas:
                        categoria = 'adulto_mujer'

                    # update_or_create
                    producto, creado = Producto.objects.update_or_create(
                        nombre=nombre_prod,
                        defaults={
                            'categoria_grupo': categoria,
                            'precio': precio,
                            'estado': estado,
                            'descripcion': descripcion,
                            'origen': 'excel',
                            'fecha_importacion': timezone.now(),
                        }
                    )
                    
                    if creado:
                        creados += 1
                    else:
                        actualizados += 1

                except (IndexError, ValueError) as e:
                    errores.append(f'Fila {i}: {str(e)}')

        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {str(e)}')
            return redirect('importar_excel')

        # ── RESUMEN FINAL ──────────────────────────────────────
        if creados or actualizados:
            messages.success(
                request,
                f'✅ {creados} productos creados, {actualizados} actualizados.'
            )
        if errores:
            for error in errores[:5]:
                messages.warning(request, error)

        return redirect('lista_productos')

    return render(request, 'productos/importar_excel.html')


@login_required
def descargar_plantilla(request):
    """Genera y descarga una plantilla Excel vacía con las columnas correctas"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Productos"
    
    # Cabeceras
    cabeceras = ['Nombre', 'Categoría', 'Precio', 'Estado', 'Descripción']
    ws.append(cabeceras)
    
    # Fila de ejemplo
    ws.append(['Vestido floral', 'adulto_mujer', '25.00', 'disponible', 'Talla M'])
    
    # Estilo de cabecera
    from openpyxl.styles import Font, PatternFill
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1a73e8")
    
    # Ancho de columnas
    ws.column_dimensions['A'].width = 25
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 15
    ws.column_dimensions['E'].width = 30

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_productos.xlsx"'
    wb.save(response)
    return response


