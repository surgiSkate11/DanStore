from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from .models import Sorteo, Participante, Premio, ResultadoSorteo, Cupon
import random
import string


@login_required
def lista_sorteos(request):
    """Vista principal de sorteos"""
    # OPTIMIZACIÓN: prefetch_related para cargar participantes y premios de una vez
    sorteos_activos = Sorteo.objects.filter(
        activo=True, completado=False
    ).prefetch_related('premios').order_by('-fecha_creacion')
    
    sorteos_completados = Sorteo.objects.filter(
        completado=True
    ).prefetch_related('premios', 'resultados__cliente').order_by('-fecha_sorteo')
    
    context = {
        'sorteos_activos': sorteos_activos,
        'sorteos_completados': sorteos_completados,
    }
    return render(request, 'sorteos/lista_sorteos.html', context)


@login_required
def crear_sorteo(request):
    """Vista para crear un nuevo sorteo"""
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        tipo = request.POST.get('tipo')
        descripcion = request.POST.get('descripcion', '')
        criterio = request.POST.get('criterio')
        
        sorteo = Sorteo.objects.create(
            nombre=nombre,
            tipo=tipo,
            descripcion=descripcion,
            criterio=criterio,
            monto_minimo=request.POST.get('monto_minimo') if request.POST.get('monto_minimo') else None,
            cantidad_minima=request.POST.get('cantidad_minima') if request.POST.get('cantidad_minima') else None,
            top_cantidad=request.POST.get('top_cantidad', 10),
            cantidad_cofres=request.POST.get('cantidad_cofres', 5)
        )
        
        messages.success(request, f'Sorteo "{sorteo.nombre}" creado exitosamente')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    return render(request, 'sorteos/crear_sorteo.html')


@login_required
def detalle_sorteo(request, sorteo_id):
    """Vista de detalle de un sorteo"""
    # OPTIMIZACIÓN: Cargar sorteo con todas sus relaciones
    sorteo = get_object_or_404(
        Sorteo.objects.prefetch_related(
            'premios',
            'resultados__cliente',
            'resultados__premio'
        ),
        id=sorteo_id
    )
    participantes = sorteo.obtener_participantes()
    premios = sorteo.premios.all()
    resultados = sorteo.resultados.all()
    
    context = {
        'sorteo': sorteo,
        'participantes': participantes,
        'premios': premios,
        'resultados': resultados,
        'cantidad_participantes': participantes.count(),
    }
    
    return render(request, 'sorteos/detalle_sorteo.html', context)


@login_required
def ejecutar_sorteo(request, sorteo_id):
    """Vista para ejecutar el sorteo en vivo"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    
    if sorteo.completado:
        messages.warning(request, 'Este sorteo ya fue completado')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    participantes = sorteo.obtener_participantes()
    premios = sorteo.premios.all()
    
    # Validar participantes primero (prioridad)
    if not participantes.exists():
        messages.error(request, 'No hay participantes elegibles para este sorteo')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    # Validar premios segundo
    if not premios.exists():
        messages.error(request, 'Debes configurar al menos un premio antes de iniciar el sorteo')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    context = {
        'sorteo': sorteo,
        'participantes': list(participantes.values('id', 'nombre', 'telefono')),
        'premios': list(premios.values('id', 'nombre', 'tipo', 'numero_cofre', 'color')),
        'tipo': sorteo.tipo,
    }
    
    # Renderizar template específico según el tipo
    templates = {
        'ruleta': 'sorteos/ruleta.html',
        'cofre': 'sorteos/cofre.html',
        'caja': 'sorteos/caja_misteriosa.html',
        'semaforo': 'sorteos/semaforo.html',
        'ranking': 'sorteos/ranking.html',
    }
    
    template = templates.get(sorteo.tipo, 'sorteos/ruleta.html')
    return render(request, template, context)


@login_required
def sortear_ganador(request, sorteo_id):
    """API para sortear un ganador aleatorio"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    participantes = sorteo.obtener_participantes()
    
    if not participantes.exists():
        return JsonResponse({'error': 'No hay participantes'}, status=400)
    
    # Seleccionar ganador aleatorio
    ganador = random.choice(list(participantes))
    
    return JsonResponse({
        'ganador': {
            'id': ganador.id,
            'nombre': ganador.nombre,
            'telefono': ganador.telefono or 'N/A'
        }
    })


@login_required
def registrar_resultado(request, sorteo_id):
    """Registra el resultado del sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        sorteo = get_object_or_404(Sorteo, id=sorteo_id)
        cliente_id = request.POST.get('cliente_id')
        premio_id = request.POST.get('premio_id')
        posicion = request.POST.get('posicion')
        
        if not cliente_id:
            return JsonResponse({'success': False, 'error': 'ID de cliente no proporcionado'}, status=400)
        
        from ventas.models import Cliente
        cliente = get_object_or_404(Cliente, id=cliente_id)
        premio = get_object_or_404(Premio, id=premio_id) if premio_id else None
        
        # Crear resultado
        resultado = ResultadoSorteo.objects.create(
            sorteo=sorteo,
            cliente=cliente,
            premio=premio,
            posicion=posicion if posicion else None,
            fecha_resultado=timezone.now()
        )
        
        # Generar cupón si el premio es descuento
        if premio and premio.tipo in ['descuento_porcentaje', 'descuento_fijo', 'cupon']:
            codigo = generar_codigo_cupon()
            tipo = 'porcentaje' if premio.tipo == 'descuento_porcentaje' else 'fijo'
            
            Cupon.objects.create(
                codigo=codigo,
                resultado=resultado,
                tipo_descuento=tipo,
                valor=premio.valor_descuento or 0
            )
        
        # Marcar premio como asignado
        if premio:
            premio.asignado = True
            premio.save()
        
        return JsonResponse({
            'success': True,
            'resultado_id': resultado.id,
            'mensaje': f'{cliente.nombre} ganó: {premio.nombre if premio else "Premio sorpresa"}'
        })
        
    except Exception as e:
        import traceback
        print(f"Error al registrar resultado: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': f'Error al registrar: {str(e)}'}, status=500)


@login_required
def finalizar_sorteo(request, sorteo_id):
    """Marca el sorteo como completado"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    sorteo.completado = True
    sorteo.fecha_sorteo = timezone.now()
    sorteo.save()
    
    messages.success(request, f'Sorteo "{sorteo.nombre}" finalizado')
    return redirect('detalle_sorteo', sorteo_id=sorteo.id)


def generar_codigo_cupon():
    """Genera un código único de cupón"""
    while True:
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not Cupon.objects.filter(codigo=codigo).exists():
            return codigo


@login_required
def gestionar_participantes(request, sorteo_id):
    """Vista para gestionar participantes manualmente"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    
    if sorteo.criterio != 'manual':
        messages.warning(request, 'Este sorteo no usa selección manual de participantes')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    from ventas.models import Cliente
    # OPTIMIZACIÓN: prefetch_related para participantes actuales
    participantes_actuales = sorteo.participantes.select_related('cliente').all()
    todos_clientes = Cliente.objects.only('id', 'nombre', 'telefono').order_by('nombre')
    
    context = {
        'sorteo': sorteo,
        'participantes_actuales': participantes_actuales,
        'todos_clientes': todos_clientes,
    }
    
    return render(request, 'sorteos/gestionar_participantes.html', context)


@login_required
def agregar_participante(request, sorteo_id):
    """Agregar un participante al sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    cliente_id = request.POST.get('cliente_id')
    
    from ventas.models import Cliente
    cliente = get_object_or_404(Cliente, id=cliente_id)
    
    # Crear o verificar participante
    participante, created = Participante.objects.get_or_create(
        sorteo=sorteo,
        cliente=cliente
    )
    
    if created:
        return JsonResponse({
            'success': True,
            'mensaje': f'{cliente.nombre} agregado al sorteo',
            'participante_id': participante.id
        })
    else:
        return JsonResponse({
            'success': False,
            'mensaje': f'{cliente.nombre} ya está en el sorteo'
        }, status=400)


@login_required
def eliminar_participante(request, sorteo_id, participante_id):
    """Eliminar un participante del sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    participante = get_object_or_404(Participante, id=participante_id, sorteo=sorteo)
    
    nombre = participante.cliente.nombre
    participante.delete()
    
    return JsonResponse({
        'success': True,
        'mensaje': f'{nombre} eliminado del sorteo'
    })


@login_required
def gestionar_premios(request, sorteo_id):
    """Vista para gestionar premios del sorteo"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    premios = sorteo.premios.all()
    
    context = {
        'sorteo': sorteo,
        'premios': premios,
    }
    return render(request, 'sorteos/gestionar_premios.html', context)


@login_required
def agregar_premio(request, sorteo_id):
    """Agregar un premio al sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id)
    
    # Validar cantidad de premios según el tipo de sorteo
    premios_actuales = sorteo.premios.count()
    max_premios = None
    
    if sorteo.tipo == 'cofre':
        max_premios = sorteo.cantidad_cofres
    elif sorteo.tipo == 'semaforo':
        max_premios = 3  # Uno por cada color
    elif sorteo.tipo == 'ranking':
        max_premios = 3  # Top 3
    
    if max_premios and premios_actuales >= max_premios:
        return JsonResponse({
            'success': False,
            'error': f'Ya has agregado el máximo de {max_premios} premios para este sorteo',
            'limite_alcanzado': True
        }, status=400)
    
    nombre = request.POST.get('nombre')
    tipo = request.POST.get('tipo')
    descripcion = request.POST.get('descripcion', '')
    valor_descuento = request.POST.get('valor_descuento')
    minimo_compra = request.POST.get('minimo_compra')
    dias_validez = request.POST.get('dias_validez', 2)
    numero_cofre = request.POST.get('numero_cofre')
    color = request.POST.get('color')
    
    if not nombre or not tipo:
        return JsonResponse({
            'success': False,
            'error': 'Nombre y tipo son requeridos'
        }, status=400)
    
    premio = Premio.objects.create(
        sorteo=sorteo,
        nombre=nombre,
        tipo=tipo,
        descripcion=descripcion,
        valor_descuento=valor_descuento if valor_descuento else None,
        minimo_compra=minimo_compra if minimo_compra else None,
        dias_validez=dias_validez,
        numero_cofre=numero_cofre if numero_cofre else None,
        color=color if color else None
    )
    
    return JsonResponse({
        'success': True,
        'mensaje': f'Premio "{premio.nombre}" agregado exitosamente',
        'premio_id': premio.id
    })


@login_required
def eliminar_premio(request, premio_id):
    """Eliminar un premio"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    premio = get_object_or_404(Premio, id=premio_id)
    nombre = premio.nombre
    premio.delete()
    
    return JsonResponse({
        'success': True,
        'mensaje': f'Premio "{nombre}" eliminado exitosamente'
    })
