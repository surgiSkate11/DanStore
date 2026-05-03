from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db import transaction
from .models import Sorteo, Participante, Premio, ResultadoSorteo, Cupon
import random
import string 
from .models import SorteoPremio
from clientes.models import Cliente
from empresas.mixins import requiere_modulo

@login_required
@requiere_modulo('sorteos')
def lista_sorteos(request):
    """Vista principal de sorteos"""
    # OPTIMIZACIÓN: prefetch_related para cargar participantes y premios de una vez
    sorteos_activos = Sorteo.objects.filter(
        empresa=request.empresa,
        activo=True, completado=False
    ).prefetch_related('sorteo_premios__premio').order_by('-fecha_creacion')
    
    sorteos_completados = Sorteo.objects.filter(
        empresa=request.empresa,
        completado=True
    ).prefetch_related('sorteo_premios__premio', 'resultados__cliente').order_by('-fecha_sorteo')
    
    context = {
        'sorteos_activos': sorteos_activos,
        'sorteos_completados': sorteos_completados,
    }
    return render(request, 'sorteos/lista_sorteos.html', context)


@login_required
@requiere_modulo('sorteos', accion='crear')
def crear_sorteo(request):
    """Vista para crear un nuevo sorteo"""
    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        tipo = request.POST.get('tipo')
        descripcion = request.POST.get('descripcion', '')
        criterio = request.POST.get('criterio')
        
        sorteo = Sorteo.objects.create(
            empresa=request.empresa,
            nombre=nombre,
            tipo=tipo,
            descripcion=descripcion,
            criterio=criterio,
            monto_minimo=request.POST.get('monto_minimo') if request.POST.get('monto_minimo') else None,
            cantidad_minima=request.POST.get('cantidad_minima') if request.POST.get('cantidad_minima') else None,
            top_cantidad=request.POST.get('top_cantidad', 10),
            cantidad_cofres=request.POST.get('cantidad_cofres', 3)
        )
        
        messages.success(request, f'Sorteo "{sorteo.nombre}" creado exitosamente')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    return render(request, 'sorteos/crear_sorteo.html')


@login_required
@requiere_modulo('sorteos')
def detalle_sorteo(request, sorteo_id):
    """Vista de detalle de un sorteo"""
    # OPTIMIZACIÓN: Cargar sorteo con todas sus relaciones
    sorteo = get_object_or_404(
        Sorteo.objects.prefetch_related(
            'sorteo_premios__premio',
            'resultados__cliente',
            'resultados__premio'
        ),
        id=sorteo_id, empresa=request.empresa
    )
    participantes = sorteo.obtener_participantes()
    premios = sorteo.sorteo_premios.select_related('premio').all()
    resultados = sorteo.resultados.all()
    
    # Agrupar ganadores únicos con sus premios (evitar duplicados)
    ganadores_dict = {}
    for resultado in resultados:
        cliente_id = resultado.cliente.id
        if cliente_id not in ganadores_dict:
            ganadores_dict[cliente_id] = {
                'cliente': resultado.cliente,
                'premios': [],
                'fecha': resultado.fecha_resultado
            }
        if resultado.premio and resultado.premio.nombre not in ganadores_dict[cliente_id]['premios']:
            ganadores_dict[cliente_id]['premios'].append(resultado.premio.nombre)
    ganadores_unicos = list(ganadores_dict.values())
    
    # Contar premios asignados
    premios_asignados = premios.filter(asignado=True).count()
    
    context = {
        'sorteo': sorteo,
        'participantes': participantes,
        'premios': premios,
        'resultados': resultados,
        'ganadores_unicos': ganadores_unicos,
        'cantidad_participantes': participantes.count(),
        'premios_asignados': premios_asignados,
    }
    
    return render(request, 'sorteos/detalle_sorteo.html', context)


@login_required
@requiere_modulo('sorteos', accion='editar')
def ejecutar_sorteo(request, sorteo_id):
    """Vista para ejecutar el sorteo en vivo"""
    import json
    from django.db.models import Sum, Count
    from datetime import date
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    
    if sorteo.completado:
        messages.warning(request, 'Este sorteo ya fue completado')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    participantes = sorteo.obtener_participantes()
    premios = sorteo.sorteo_premios.select_related('premio').all()
    
    # Validar participantes primero (prioridad)
    if not participantes.exists():
        messages.error(request, 'No hay participantes elegibles para este sorteo')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    # Validar premios segundo
    if not premios.exists():
        messages.error(request, 'Debes configurar al menos un premio antes de iniciar el sorteo')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    # Validar que cofres/cajas coincidan exactamente con la configuración
    if sorteo.tipo in ['cofre', 'caja'] and premios.count() != sorteo.cantidad_cofres:
        messages.error(request, f'Debes configurar exactamente {sorteo.cantidad_cofres} premios para iniciar este sorteo.')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    # Contar resultados ya registrados
    resultados_count = sorteo.resultados.count()
    premios_restantes = premios.filter(asignado=False).count()
    
    # Verificar si todos los premios ya fueron asignados
    if premios_restantes == 0:
        # Marcar como completado si no lo estaba
        if not sorteo.completado:
            sorteo.completado = True
            sorteo.activo = False
            sorteo.fecha_sorteo = timezone.now()
            sorteo.save()
        messages.info(request, 'Este sorteo ya ha entregado todos sus premios')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    # Serializar premios con datos del SorteoPremio y Premio
    premios_data = []
    for sp in premios:
        premios_data.append({
            'id': sp.id,
            'nombre': sp.premio.nombre,
            'tipo': sp.premio.tipo,
            'numero_cofre': sp.numero_cofre,
            'color': sp.color,
            'asignado': sp.asignado,
            'orden': sp.orden,
            'premio_id': sp.premio.id
        })
    
    # Para el ranking, calcular puntos (cada $5 = 3 puntos)
    if sorteo.tipo == 'ranking':
        from ventas.models import Venta
        participantes_ranking = []
        
        for cliente in participantes:
            # Calcular monto según el criterio del sorteo
            if sorteo.criterio == 'compras_hoy':
                ventas_hoy = Venta.objects.filter(cliente=cliente, empresa=request.empresa, fecha__date=date.today())
                monto = float(ventas_hoy.aggregate(total=Sum('total'))['total'] or 0)
                
            elif sorteo.criterio == 'cantidad_productos':
                # Para cantidad de productos, cada producto = 5 puntos base
                from ventas.models import DetalleVenta
                cantidad = DetalleVenta.objects.filter(venta__cliente=cliente, venta__empresa=request.empresa).count()
                monto = cantidad * 5 / 3 * 5  # Convertir a equivalente de monto
                
            else:
                # Monto total de compras (monto_minimo, top_compradores, manual, todos)
                monto = float(cliente.total_compras())
            
            # Convertir monto a puntos: cada $5 = 3 puntos
            puntos = int((monto / 5) * 3)
            
            participantes_ranking.append({
                'id': cliente.id,
                'nombre': cliente.nombre,
                'puntos': puntos
            })
        
        # Ordenar por puntos descendente
        participantes_ranking.sort(key=lambda x: x['puntos'], reverse=True)
        participantes_json = json.dumps(participantes_ranking)
    else:
        participantes_json = json.dumps(list(participantes.values('id', 'nombre', 'telefono')))
    
    context = {
        'sorteo': sorteo,
        'participantes_json': participantes_json,
        'premios_json': json.dumps(premios_data),
        'premios_restantes': premios_restantes,
        'ganadores_count': resultados_count,
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
@requiere_modulo('sorteos', accion='editar')
def sortear_ganador(request, sorteo_id):
    """API para sortear un ganador aleatorio"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
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


@transaction.atomic
@login_required
@requiere_modulo('sorteos', accion='editar')
def registrar_resultado(request, sorteo_id):
    """Registra el resultado del sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
        cliente_id = request.POST.get('cliente_id')
        premio_id = request.POST.get('premio_id')
        posicion = request.POST.get('posicion')
        
        if not cliente_id:
            return JsonResponse({'success': False, 'error': 'ID de cliente no proporcionado'}, status=400)
        
        cliente = get_object_or_404(Cliente, id=cliente_id, empresas=request.empresa)
        sorteo_premio = None
        premio_obj = None
        
        # Buscar el SorteoPremio (no el Premio directamente)
        if premio_id:
            # Evitar condiciones de carrera si dos peticiones entran a la vez
            sorteo_premio = get_object_or_404(SorteoPremio.objects.select_for_update(), id=premio_id, sorteo=sorteo)
            if sorteo_premio.asignado:
                return JsonResponse({'success': False, 'error': 'Este premio ya fue asignado. Refresca la página.'}, status=400)
                
            premio_obj = sorteo_premio.premio
        
        # Crear resultado
        resultado = ResultadoSorteo.objects.create(
            sorteo=sorteo,
            cliente=cliente,
            premio=premio_obj,
            posicion=posicion if posicion else None,
            fecha_resultado=timezone.now()
        )
        
        # Generar cupón si el premio es descuento
        if premio_obj and premio_obj.tipo in ['descuento_porcentaje', 'descuento_fijo', 'cupon']:
            codigo = generar_codigo_cupon()
            tipo = 'porcentaje' if premio_obj.tipo == 'descuento_porcentaje' else 'fijo'
            
            Cupon.objects.create(
                codigo=codigo,
                resultado=resultado,
                tipo_descuento=tipo,
                valor=premio_obj.valor_descuento or 0
            )
        
        # Marcar SorteoPremio como asignado
        if sorteo_premio:
            sorteo_premio.asignado = True
            sorteo_premio.save()
        
        # CORRECCIÓN: Verificar si el sorteo debe marcarse como completado
        sorteo_completado = False
        
        if sorteo.tipo == 'ranking':
            # Para ranking: completar cuando se asignen 3 premios (Top 3)
            premios_asignados = sorteo.sorteo_premios.filter(asignado=True).count()
            if premios_asignados >= 3:
                sorteo.completado = True
                sorteo.activo = False
                sorteo.fecha_sorteo = timezone.now()
                sorteo.save()
                sorteo_completado = True
        else:
            # Para otros sorteos: completar cuando todos los premios estén asignados
            premios_sin_asignar = sorteo.sorteo_premios.filter(asignado=False).count()
            if premios_sin_asignar == 0 and sorteo.sorteo_premios.exists():
                sorteo.completado = True
                sorteo.activo = False
                sorteo.fecha_sorteo = timezone.now()
                sorteo.save()
                sorteo_completado = True
        
        return JsonResponse({
            'success': True,
            'resultado_id': resultado.id,
            'mensaje': f'{cliente.nombre} ganó: {premio_obj.nombre if premio_obj else "Premio sorpresa"}',
            'sorteo_completado': sorteo_completado
        })
        
    except Exception as e:
        import traceback
        print(f"Error al registrar resultado: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'success': False, 'error': f'Error al registrar: {str(e)}'}, status=500)


@login_required
@requiere_modulo('sorteos', accion='editar')
def finalizar_sorteo(request, sorteo_id):
    """Marca el sorteo como completado"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    sorteo.completado = True
    sorteo.activo = False
    sorteo.fecha_sorteo = timezone.now()
    sorteo.save()
    
    # Si es una petición AJAX, devolver JSON
    if request.headers.get('Content-Type') == 'application/json':
        return JsonResponse({'success': True, 'mensaje': f'Sorteo "{sorteo.nombre}" finalizado'})
    
    messages.success(request, f'Sorteo "{sorteo.nombre}" finalizado')
    return redirect('detalle_sorteo', sorteo_id=sorteo.id)


def generar_codigo_cupon():
    """Genera un código único de cupón"""
    while True:
        codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if not Cupon.objects.filter(codigo=codigo).exists():
            return codigo


@login_required
@requiere_modulo('sorteos', accion='editar')
def gestionar_participantes(request, sorteo_id):
    """Vista para gestionar participantes manualmente"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    
    if sorteo.criterio != 'manual':
        messages.warning(request, 'Este sorteo no usa selección manual de participantes')
        return redirect('detalle_sorteo', sorteo_id=sorteo.id)
    
    from clientes.models import Cliente
    # OPTIMIZACIÓN: prefetch_related para participantes actuales
    participantes_actuales = sorteo.participantes.select_related('cliente').all()
    todos_clientes = Cliente.objects.filter(empresas=request.empresa).only('id', 'nombre', 'telefono').order_by('nombre')
    
    context = {
        'sorteo': sorteo,
        'participantes_actuales': participantes_actuales,
        'todos_clientes': todos_clientes,
    }
    
    return render(request, 'sorteos/gestionar_participantes.html', context)


@login_required
@requiere_modulo('sorteos', accion='crear')
def agregar_participante(request, sorteo_id):
    """Agregar un participante al sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    cliente_id = request.POST.get('cliente_id')
    
    from clientes.models import Cliente
    cliente = get_object_or_404(Cliente, id=cliente_id, empresas=request.empresa)
    
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
@requiere_modulo('sorteos', accion='eliminar')
def eliminar_participante(request, sorteo_id, participante_id):
    """Eliminar un participante del sorteo"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    participante = get_object_or_404(Participante, id=participante_id, sorteo=sorteo)
    
    nombre = participante.cliente.nombre
    participante.delete()
    
    return JsonResponse({
        'success': True,
        'mensaje': f'{nombre} eliminado del sorteo'
    })


@login_required
@requiere_modulo('sorteos', accion='editar')
def gestionar_premios(request, sorteo_id):
    """Vista para gestionar premios del sorteo"""
    sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
    from .models import Premio
    
    # Premios ya asociados a este sorteo
    premios_sorteo = sorteo.sorteo_premios.select_related('premio').all()
    
    # Todos los premios disponibles en la biblioteca
    premios_disponibles = Premio.objects.filter(empresa=request.empresa).order_by('-creado_en')
    
    context = {
        'sorteo': sorteo,
        'premios_sorteo': premios_sorteo,
        'premios_disponibles': premios_disponibles,
        'url_name': 'gestionar_premios',
    }
    return render(request, 'sorteos/gestionar_premios.html', context)


@login_required
@requiere_modulo('sorteos', accion='crear')
def agregar_premio(request, sorteo_id):
    """Agregar un premio al sorteo (crear nuevo o vincular existente)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    try:
        sorteo = get_object_or_404(Sorteo, id=sorteo_id, empresa=request.empresa)
        
        # Validar cantidad de premios según el tipo de sorteo
        premios_actuales = sorteo.sorteo_premios.count()
        max_premios = None
        
        if sorteo.tipo == 'cofre':
            max_premios = sorteo.cantidad_cofres
        elif sorteo.tipo == 'caja':
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
        
        # Verificar si se está usando un premio existente o creando uno nuevo
        premio_id = request.POST.get('premio_id')
        
        if premio_id:
            # Usar premio existente
            premio = get_object_or_404(Premio, id=premio_id, empresa=request.empresa)
        else:
            # Crear nuevo premio
            nombre = request.POST.get('nombre')
            tipo = request.POST.get('tipo')
            descripcion = request.POST.get('descripcion', '')
            valor_descuento = request.POST.get('valor_descuento')
            dias_validez = request.POST.get('dias_validez', 2)
            
            if not nombre or not tipo:
                return JsonResponse({
                    'success': False,
                    'error': 'Nombre y tipo son requeridos'
                }, status=400)
            
            # Validación de seguridad para premios de tipo descuento
            if tipo in ['descuento_porcentaje', 'descuento_fijo'] and not valor_descuento:
                return JsonResponse({
                    'success': False,
                    'error': 'El valor del descuento es obligatorio para este tipo de premio'
                }, status=400)
                
            if tipo not in ['descuento_porcentaje', 'descuento_fijo']:
                valor_descuento = None
            
            premio = Premio.objects.create(
                empresa=request.empresa,
                nombre=nombre,
                tipo=tipo,
                descripcion=descripcion,
                valor_descuento=valor_descuento if valor_descuento else None,
                dias_validez=dias_validez if dias_validez else 2,
            )
        
        # Crear la asociación SorteoPremio
        numero_cofre = request.POST.get('numero_cofre')
        color = request.POST.get('color')
        orden = request.POST.get('orden', premios_actuales + 1)
        
        # Validar que no se repita el numero_cofre en cofre
        if sorteo.tipo == 'cofre' and numero_cofre:
            if sorteo.sorteo_premios.filter(numero_cofre=numero_cofre).exists():
                return JsonResponse({
                    'success': False,
                    'error': f'El cofre número {numero_cofre} ya tiene un premio asignado.'
                }, status=400)

        # Validar que no se repita el color en semáforo
        if sorteo.tipo == 'semaforo' and color:
            color_existente = sorteo.sorteo_premios.filter(color=color).exists()
            if color_existente:
                return JsonResponse({
                    'success': False,
                    'error': f'Ya existe un premio para el color {color}. Cada color solo puede tener un premio.'
                }, status=400)
        
        sorteo_premio = SorteoPremio.objects.create(
            sorteo=sorteo,
            premio=premio,
            numero_cofre=numero_cofre if numero_cofre else None,
            color=color if color else None,
            orden=orden
        )
        
        return JsonResponse({
            'success': True,
            'mensaje': f'Premio "{premio.nombre}" agregado exitosamente',
            'premio_id': premio.id
        })
    
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al agregar premio: {str(e)}'
        }, status=500)


@login_required
@requiere_modulo('sorteos', accion='eliminar')
def eliminar_premio(request, sorteo_id, premio_id):
    """Eliminar un premio de un sorteo específico"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)
    
    # premio_id es el ID de SorteoPremio
    sorteo_premio = get_object_or_404(SorteoPremio, id=premio_id, sorteo_id=sorteo_id)
    
    nombre = sorteo_premio.premio.nombre
    sorteo_premio.delete()
    
    return JsonResponse({
        'success': True,
        'mensaje': f'Premio "{nombre}" eliminado del sorteo exitosamente'
    })