"""Cálculos de estadísticas de negocio para el Dashboard, Reportes y el panel SaaS.

Todas las funciones de tenant reciben la empresa y filtran por ella: los
datos de una empresa nunca se mezclan con los de otra.

Ingreso = solo ventas cobradas. Las anuladas no cuentan y las que están
pendientes de pago se informan aparte como "por cobrar".
"""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Min, Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay, TruncDate, TruncMonth
from django.utils import timezone

from empresas.models import SuscripcionEmpresa
from productos.models import Producto
from ventas.models import DetalleVenta, Venta

ESTADOS_NO_COBRADOS = ('anulada', 'pendiente_pago')
ESTADO_POR_COBRAR = 'pendiente_pago'

MESES_CORTOS = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
DIAS_SEMANA = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']

# Hasta este número de días la serie se agrupa por día; más allá, por mes.
MAX_DIAS_SERIE_DIARIA = 90

_DECIMAL = DecimalField(max_digits=14, decimal_places=2)
_CERO = Decimal('0')


def _f(valor):
    """Convierte Decimal/None a float redondeado para JSON."""
    return round(float(valor or 0), 2)


def etiqueta_dia(fecha):
    return f"{fecha.day:02d} {MESES_CORTOS[fecha.month - 1]}"


def etiqueta_mes(anio, mes):
    return f"{MESES_CORTOS[mes - 1]} {anio}"


def variacion_pct(actual, anterior):
    """% de cambio entre dos valores. None cuando no hay base para comparar."""
    actual = Decimal(str(actual or 0))
    anterior = Decimal(str(anterior or 0))
    if anterior == 0:
        return None
    return round(float((actual - anterior) * 100 / anterior), 1)


def ventas_cobradas(empresa, desde=None, hasta=None):
    qs = Venta.objects.filter(empresa=empresa).exclude(estado__in=ESTADOS_NO_COBRADOS)
    if desde is not None:
        qs = qs.filter(fecha__gte=desde)
    if hasta is not None:
        qs = qs.filter(fecha__lt=hasta)
    return qs


def detalles_cobrados(empresa, desde=None, hasta=None):
    qs = DetalleVenta.objects.filter(venta__empresa=empresa).exclude(venta__estado__in=ESTADOS_NO_COBRADOS)
    if desde is not None:
        qs = qs.filter(venta__fecha__gte=desde)
    if hasta is not None:
        qs = qs.filter(venta__fecha__lt=hasta)
    return qs


def kpis_periodo(empresa, desde, hasta=None):
    """Ingresos, número de ventas, ticket promedio y clientes únicos de un período."""
    datos = ventas_cobradas(empresa, desde, hasta).aggregate(
        ingresos=Sum('total'), ventas=Count('id'), clientes=Count('cliente', distinct=True)
    )
    ingresos = datos['ingresos'] or _CERO
    ventas = datos['ventas'] or 0
    return {
        'ingresos': ingresos,
        'ventas': ventas,
        'ticket': (ingresos / ventas) if ventas else _CERO,
        'clientes': datos['clientes'] or 0,
    }


def por_cobrar(empresa):
    """Monto y cantidad de ventas pendientes de pago (de cualquier fecha)."""
    datos = Venta.objects.filter(empresa=empresa, estado=ESTADO_POR_COBRAR).aggregate(
        monto=Sum('total'), cantidad=Count('id')
    )
    return {'monto': datos['monto'] or _CERO, 'cantidad': datos['cantidad'] or 0}


def _inicio_dia(fecha_hora):
    return timezone.localtime(fecha_hora).replace(hour=0, minute=0, second=0, microsecond=0)


def _sumar_meses(fecha_hora, meses):
    mes = fecha_hora.month - 1 + meses
    anio = fecha_hora.year + mes // 12
    return fecha_hora.replace(year=anio, month=mes % 12 + 1, day=1)


def resumen_hoy(empresa, ahora=None):
    """KPIs del Dashboard con su comparación contra el período anterior equivalente.

    - Hoy contra ayer a la misma hora.
    - Mes en curso contra los mismos días del mes anterior.
    """
    ahora = timezone.localtime(ahora or timezone.now())
    hoy = _inicio_dia(ahora)
    ayer = hoy - timedelta(days=1)
    inicio_mes = hoy.replace(day=1)
    inicio_mes_anterior = _sumar_meses(inicio_mes, -1)
    # Mismo tramo del mes anterior; si ese mes es más corto se corta en su fin.
    corte_mes_anterior = min(inicio_mes_anterior + (ahora - inicio_mes), inicio_mes)

    kpi_hoy = kpis_periodo(empresa, hoy, ahora)
    kpi_ayer = kpis_periodo(empresa, ayer, ayer + (ahora - hoy))
    kpi_mes = kpis_periodo(empresa, inicio_mes, ahora)
    kpi_mes_ant = kpis_periodo(empresa, inicio_mes_anterior, corte_mes_anterior)

    return {
        'hoy': kpi_hoy,
        'mes': kpi_mes,
        'var_hoy': variacion_pct(kpi_hoy['ingresos'], kpi_ayer['ingresos']),
        'var_mes': variacion_pct(kpi_mes['ingresos'], kpi_mes_ant['ingresos']),
        'var_ticket': variacion_pct(kpi_mes['ticket'], kpi_mes_ant['ticket']),
        'var_ventas': variacion_pct(kpi_mes['ventas'], kpi_mes_ant['ventas']),
        'por_cobrar': por_cobrar(empresa),
    }


def acumulado_mes_vs_anterior(empresa, ahora=None):
    """Ingreso acumulado día a día del mes actual frente al mes anterior completo."""
    ahora = timezone.localtime(ahora or timezone.now())
    inicio_mes = _inicio_dia(ahora).replace(day=1)
    inicio_ant = _sumar_meses(inicio_mes, -1)
    dias_ant = (inicio_mes - inicio_ant).days
    dias_mes = (_sumar_meses(inicio_mes, 1) - inicio_mes).days

    def por_dia(desde, hasta):
        filas = (
            ventas_cobradas(empresa, desde, hasta)
            .annotate(dia=TruncDate('fecha'))
            .values('dia').annotate(total=Sum('total'))
        )
        return {f['dia'].day: f['total'] for f in filas if f['dia']}

    actual = por_dia(inicio_mes, ahora)
    anterior = por_dia(inicio_ant, inicio_mes)

    serie_actual, serie_anterior = [], []
    acum_a = acum_b = _CERO
    for dia in range(1, max(dias_mes, dias_ant) + 1):
        if dia <= ahora.day:
            acum_a += actual.get(dia, _CERO)
            serie_actual.append(_f(acum_a))
        else:
            serie_actual.append(None)
        if dia <= dias_ant:
            acum_b += anterior.get(dia, _CERO)
            serie_anterior.append(_f(acum_b))
        else:
            serie_anterior.append(None)

    return {
        'labels': [str(d) for d in range(1, max(dias_mes, dias_ant) + 1)],
        'actual': serie_actual,
        'anterior': serie_anterior,
        'nombre_actual': etiqueta_mes(inicio_mes.year, inicio_mes.month),
        'nombre_anterior': etiqueta_mes(inicio_ant.year, inicio_ant.month),
    }


def ventas_por_estado(empresa, desde):
    """Cantidad y monto de ventas por estado desde una fecha (incluye todas)."""
    etiquetas = {'pendiente_pago': 'Pendiente de pago', **dict(Venta.ESTADO_CHOICES)}
    filas = (
        Venta.objects.filter(empresa=empresa, fecha__gte=desde)
        .values('estado').annotate(cantidad=Count('id'), monto=Sum('total'))
        .order_by('-cantidad')
    )
    return [
        {'estado': f['estado'], 'label': etiquetas.get(f['estado'], f['estado'].replace('_', ' ').capitalize()),
         'cantidad': f['cantidad'], 'monto': _f(f['monto'])}
        for f in filas
    ]


def productos_stock_bajo(empresa, umbral=2, limite=6):
    """Productos disponibles o reservados con pocas unidades, de menos a más."""
    return list(
        Producto.objects.filter(empresa=empresa, estado__in=['disponible', 'reservado'], stock__lte=umbral)
        .order_by('stock', 'nombre')
        .values('id', 'nombre', 'stock')[:limite]
    )


def serie_ingresos_utilidad(empresa, dias, ahora=None):
    """Ingresos, utilidad y margen % agrupados por día (≤90 días) o por mes.

    La utilidad usa el costo actual del producto y solo cuenta productos con
    costo cargado; el margen es utilidad / costo, ponderado por monto.
    """
    ahora = timezone.localtime(ahora or timezone.now())
    hoy = _inicio_dia(ahora)
    mensual = dias > MAX_DIAS_SERIE_DIARIA

    if mensual:
        meses = max(1, round(dias / 30.4))
        inicio = _sumar_meses(hoy.replace(day=1), -(meses - 1))
        trunc = TruncMonth
        claves = [_sumar_meses(inicio, i).date() for i in range(meses)]
        labels = [etiqueta_mes(c.year, c.month) for c in claves]
    else:
        inicio = hoy - timedelta(days=dias - 1)
        trunc = TruncDate
        claves = [(inicio + timedelta(days=i)).date() for i in range(dias)]
        labels = [etiqueta_dia(c) for c in claves]

    def _clave(valor):
        return valor.date() if hasattr(valor, 'date') else valor

    ingresos = {
        _clave(f['k']): f['total']
        for f in ventas_cobradas(empresa, inicio).annotate(k=trunc('fecha')).values('k').annotate(total=Sum('total'))
        if f['k']
    }
    utilidad_qs = (
        detalles_cobrados(empresa, inicio)
        .filter(producto__precio_costo__gt=0)
        .annotate(k=trunc('venta__fecha'))
        .values('k')
        .annotate(
            utilidad=Sum(ExpressionWrapper(F('precio_unitario') - F('producto__precio_costo'), output_field=_DECIMAL)),
            vendido=Sum('precio_unitario'),
        )
    )
    utilidad = {_clave(f['k']): (f['utilidad'], f['vendido']) for f in utilidad_qs if f['k']}

    serie_ing, serie_util, serie_margen = [], [], []
    for c in claves:
        u, vendido = utilidad.get(c, (_CERO, _CERO))
        serie_ing.append(_f(ingresos.get(c)))
        serie_util.append(_f(u))
        costo = vendido - u
        serie_margen.append(round(float(u * 100 / costo), 1) if costo > 0 else None)

    return {'labels': labels, 'ingresos': serie_ing, 'utilidad': serie_util,
            'margen': serie_margen, 'mensual': mensual}


def mapa_calor(empresa, desde):
    """Ventas por día de la semana (filas) y hora (columnas), en hora local."""
    filas = (
        ventas_cobradas(empresa, desde)
        .annotate(dia=ExtractIsoWeekDay('fecha'), hora=ExtractHour('fecha'))
        .values('dia', 'hora').annotate(cantidad=Count('id'), ingresos=Sum('total'))
    )
    matriz = {(f['dia'], f['hora']): f for f in filas}
    horas_con_datos = [h for (_, h) in matriz]
    hora_min = min(horas_con_datos, default=8)
    hora_max = max(horas_con_datos, default=20)
    horas = list(range(min(hora_min, 8), max(hora_max, 20) + 1))

    series = []
    for dia in range(7, 0, -1):  # ApexCharts dibuja la primera serie abajo: Domingo abajo, Lunes arriba.
        series.append({
            'name': DIAS_SEMANA[dia - 1],
            'data': [{'x': f"{h:02d}h", 'y': matriz.get((dia, h), {}).get('cantidad', 0),
                      'ingresos': _f(matriz.get((dia, h), {}).get('ingresos'))} for h in horas],
        })

    mejor = max(matriz.values(), key=lambda f: (f['cantidad'], f['ingresos'] or 0), default=None)
    return {
        'series': series,
        'mejor': {'dia': DIAS_SEMANA[mejor['dia'] - 1], 'hora': mejor['hora'], 'cantidad': mejor['cantidad']} if mejor else None,
    }


def pareto_productos(empresa, desde, limite=15):
    """Productos ordenados por ingreso con su % acumulado (análisis 80/20)."""
    filas = list(
        detalles_cobrados(empresa, desde)
        .values('producto__nombre')
        .annotate(ingresos=Sum('precio_unitario'), unidades=Count('id'))
        .order_by('-ingresos', 'producto__nombre')
    )
    total = sum((f['ingresos'] or _CERO) for f in filas)
    acumulado = _CERO
    productos_80 = 0
    resultado = []
    for f in filas:
        acumulado += f['ingresos'] or _CERO
        pct = float(acumulado * 100 / total) if total else 0.0
        if productos_80 == 0 and pct >= 80:
            productos_80 = len(resultado) + 1
        resultado.append({'nombre': f['producto__nombre'], 'ingresos': _f(f['ingresos']),
                          'unidades': f['unidades'], 'pct_acumulado': round(pct, 1)})

    return {
        'productos': resultado[:limite],
        'total_productos': len(resultado),
        'productos_80': productos_80,
        'pct_catalogo_80': round(productos_80 * 100 / len(resultado), 1) if resultado else 0,
    }


def clientes_nuevos_vs_recurrentes(empresa, desde):
    """Clasifica a los clientes que compraron en el período.

    Nuevo: su primera compra en esta empresa cae dentro del período.
    Recurrente: ya había comprado antes del período.
    """
    compras = ventas_cobradas(empresa).filter(cliente__isnull=False)
    del_periodo = (
        compras.filter(fecha__gte=desde)
        .values('cliente').annotate(compras=Count('id'), monto=Sum('total'))
    )
    primeras = dict(compras.values('cliente').annotate(primera=Min('fecha')).values_list('cliente', 'primera'))

    nuevos = {'clientes': 0, 'monto': _CERO}
    recurrentes = {'clientes': 0, 'monto': _CERO}
    repiten = 0
    for f in del_periodo:
        grupo = nuevos if primeras.get(f['cliente']) and primeras[f['cliente']] >= desde else recurrentes
        grupo['clientes'] += 1
        grupo['monto'] += f['monto'] or _CERO
        if f['compras'] >= 2:
            repiten += 1

    total = nuevos['clientes'] + recurrentes['clientes']
    return {
        'nuevos': {'clientes': nuevos['clientes'], 'monto': _f(nuevos['monto'])},
        'recurrentes': {'clientes': recurrentes['clientes'], 'monto': _f(recurrentes['monto'])},
        'tasa_recompra': round(repiten * 100 / total, 1) if total else 0,
        'total': total,
    }


def mrr_suscripcion(precio_mensual, precio_anual, tipo_plan):
    """Aporte mensual de una suscripción: la anual se prorratea en 12 meses."""
    if tipo_plan == 'anual' and precio_anual:
        return Decimal(precio_anual) / 12
    return Decimal(precio_mensual or 0)


def mrr_historico(meses=12, ahora=None):
    """MRR estimado mes a mes según las suscripciones vigentes en cada mes.

    Una suscripción cuenta en un mes si la empresa está activa, ya existía al
    cierre del mes y su vencimiento es posterior al inicio del mes. Es una estimación: el
    sistema guarda solo el período vigente de cada empresa, no su historial.
    """
    ahora = timezone.localtime(ahora or timezone.now())
    inicio_mes_actual = _inicio_dia(ahora).replace(day=1)
    subs = list(
        SuscripcionEmpresa.objects.filter(plan__isnull=False, empresa__activa=True)
        .values('tipo_plan', 'fecha_vencimiento', 'empresa__fecha_creacion',
                'plan__precio_mensual', 'plan__precio_anual')
    )
    labels, valores = [], []
    for i in range(meses - 1, -1, -1):
        inicio = _sumar_meses(inicio_mes_actual, -i)
        fin = min(_sumar_meses(inicio, 1), ahora)
        total = sum(
            (mrr_suscripcion(s['plan__precio_mensual'], s['plan__precio_anual'], s['tipo_plan'])
             for s in subs
             if s['empresa__fecha_creacion'] < fin and s['fecha_vencimiento'] >= inicio),
            _CERO,
        )
        labels.append(etiqueta_mes(inicio.year, inicio.month))
        valores.append(_f(total))
    return {'labels': labels, 'valores': valores}
