from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from .models import Producto, TipoPrenda
from .forms import ProductoForm, ProductoFiltroForm


@login_required
def home(request):
    """Vista principal - Dashboard"""
    # OPTIMIZACIÓN: Usar count() directo es rápido con índices
    context = {
        'total_productos': Producto.objects.count(),
        'disponibles': Producto.objects.filter(estado='disponible').count(),
        'separados': Producto.objects.filter(estado='separado').count(),
        'vendidos': Producto.objects.filter(estado='vendido').count(),
    }
    return render(request, 'productos/home.html', context)


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
    
    if request.method == 'POST':
        form = ProductoForm(request.POST, request.FILES, instance=producto)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Producto actualizado exitosamente!')
            return redirect('lista_productos')
    else:
        form = ProductoForm(instance=producto)
    
    return render(request, 'productos/form_producto.html', {
        'form': form,
        'titulo': 'Editar Producto',
        'producto': producto
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
