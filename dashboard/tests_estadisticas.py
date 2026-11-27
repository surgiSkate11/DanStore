from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.test import TestCase

from clientes.models import Cliente
from dashboard import estadisticas as est
from empresas.models import Empresa, Plan, SuscripcionEmpresa
from productos.models import Producto, TipoProducto
from ventas.models import DetalleVenta, Venta

TZ = ZoneInfo('America/Guayaquil')
AHORA = datetime(2026, 3, 15, 14, 0, tzinfo=TZ)


def local(*args):
    return datetime(*args, tzinfo=TZ)


class EstadisticasBase(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='Tienda A', slug='tienda-a')
        self.otra = Empresa.objects.create(nombre='Tienda B', slug='tienda-b')
        self.tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Ropa')
        self.cliente = Cliente.objects.create(nombre='Ana', ruc_cedula='1111111111')
        self.cliente2 = Cliente.objects.create(nombre='Luis', ruc_cedula='2222222222')

    def producto(self, nombre, precio, costo=None, stock=5, empresa=None):
        return Producto.objects.create(
            empresa=empresa or self.empresa, nombre=nombre, tipo_producto=self.tipo,
            precio=Decimal(precio), precio_costo=Decimal(costo) if costo else None,
            stock=stock, estado='disponible',
        )

    def venta(self, fecha, total, estado='completada', empresa=None, cliente=None, productos=()):
        v = Venta.objects.create(
            empresa=empresa or self.empresa, cliente=cliente or self.cliente,
            fecha=fecha, total=Decimal(total), estado=estado,
        )
        for p in productos:
            DetalleVenta.objects.create(venta=v, producto=p, precio_unitario=p.precio)
        return v


class IngresosCobradosTests(EstadisticasBase):
    def test_excluye_anuladas_y_pendientes_y_otras_empresas(self):
        self.venta(local(2026, 3, 10, 10), '100')
        self.venta(local(2026, 3, 10, 11), '50', estado='anulada')
        self.venta(local(2026, 3, 10, 12), '30', estado='pendiente_pago')
        self.venta(local(2026, 3, 10, 12), '999', empresa=self.otra)

        kpis = est.kpis_periodo(self.empresa, local(2026, 3, 1))

        self.assertEqual(kpis['ingresos'], Decimal('100'))
        self.assertEqual(kpis['ventas'], 1)
        self.assertEqual(kpis['ticket'], Decimal('100'))

    def test_por_cobrar_suma_solo_pendientes_de_la_empresa(self):
        self.venta(local(2026, 3, 10, 12), '30', estado='pendiente_pago')
        self.venta(local(2026, 1, 2, 12), '20', estado='pendiente_pago')
        self.venta(local(2026, 3, 10, 12), '70', estado='pendiente_pago', empresa=self.otra)

        self.assertEqual(est.por_cobrar(self.empresa), {'monto': Decimal('50'), 'cantidad': 2})


class VariacionTests(TestCase):
    def test_variacion(self):
        self.assertEqual(est.variacion_pct(150, 100), 50.0)
        self.assertEqual(est.variacion_pct(50, 100), -50.0)
        self.assertIsNone(est.variacion_pct(10, 0))


class ResumenHoyTests(EstadisticasBase):
    def test_compara_hoy_con_ayer_y_mes_con_mismo_tramo_anterior(self):
        self.venta(local(2026, 3, 15, 9), '200')       # hoy
        self.venta(local(2026, 3, 14, 9), '100')       # ayer antes de las 14h
        self.venta(local(2026, 3, 14, 18), '500')      # ayer después de la hora actual: no cuenta
        self.venta(local(2026, 2, 10, 9), '100')       # febrero dentro del tramo
        self.venta(local(2026, 2, 20, 9), '900')       # febrero fuera del tramo

        r = est.resumen_hoy(self.empresa, ahora=AHORA)

        self.assertEqual(r['hoy']['ingresos'], Decimal('200'))
        self.assertEqual(r['var_hoy'], 100.0)
        self.assertEqual(r['mes']['ingresos'], Decimal('800'))
        self.assertEqual(r['var_mes'], 700.0)


class AcumuladoTests(EstadisticasBase):
    def test_acumulado_corta_en_hoy_y_mes_anterior_completo(self):
        self.venta(local(2026, 3, 1, 9), '10')
        self.venta(local(2026, 3, 3, 9), '5')
        self.venta(local(2026, 2, 28, 9), '7')

        a = est.acumulado_mes_vs_anterior(self.empresa, ahora=AHORA)

        self.assertEqual(len(a['labels']), 31)
        self.assertEqual(a['actual'][:3], [10.0, 10.0, 15.0])
        self.assertEqual(a['actual'][14], 15.0)
        self.assertIsNone(a['actual'][15])
        self.assertEqual(a['anterior'][27], 7.0)
        self.assertIsNone(a['anterior'][28])
        self.assertEqual(a['nombre_actual'], 'Mar 2026')


class SerieIngresosUtilidadTests(EstadisticasBase):
    def test_diaria_con_utilidad_y_margen(self):
        camisa = self.producto('Camisa', '20', costo='10')
        sin_costo = self.producto('Gorra', '5')
        self.venta(local(2026, 3, 15, 9), '25', productos=[camisa, sin_costo])
        self.venta(local(2026, 3, 15, 10), '20', estado='pendiente_pago', productos=[camisa])

        s = est.serie_ingresos_utilidad(self.empresa, 7, ahora=AHORA)

        self.assertFalse(s['mensual'])
        self.assertEqual(len(s['labels']), 7)
        self.assertEqual(s['labels'][-1], '15 Mar')
        self.assertEqual(s['ingresos'][-1], 25.0)
        self.assertEqual(s['utilidad'][-1], 10.0)
        self.assertEqual(s['margen'][-1], 100.0)  # utilidad 10 sobre costo 10
        self.assertIsNone(s['margen'][0])

    def test_mensual_para_un_anio(self):
        self.venta(local(2025, 4, 5, 9), '40')
        s = est.serie_ingresos_utilidad(self.empresa, 365, ahora=AHORA)
        self.assertTrue(s['mensual'])
        self.assertEqual(s['labels'][0], 'Abr 2025')
        self.assertEqual(s['labels'][-1], 'Mar 2026')
        self.assertEqual(s['ingresos'][0], 40.0)


class MapaCalorTests(EstadisticasBase):
    def test_agrupa_por_dia_y_hora_local(self):
        # 2026-03-13 es viernes
        self.venta(local(2026, 3, 13, 18), '10')
        self.venta(local(2026, 3, 13, 18, 30), '15')
        self.venta(local(2026, 3, 13, 18), '99', empresa=self.otra)

        m = est.mapa_calor(self.empresa, local(2026, 3, 1))

        viernes = next(s for s in m['series'] if s['name'] == 'Vie')
        celda = next(c for c in viernes['data'] if c['x'] == '18h')
        self.assertEqual(celda['y'], 2)
        self.assertEqual(celda['ingresos'], 25.0)
        self.assertEqual(m['mejor'], {'dia': 'Vie', 'hora': 18, 'cantidad': 2})
        self.assertEqual([s['name'] for s in m['series']][-1], 'Lun')

    def test_sin_ventas(self):
        m = est.mapa_calor(self.empresa, local(2026, 3, 1))
        self.assertIsNone(m['mejor'])
        self.assertEqual(len(m['series']), 7)


class ParetoTests(EstadisticasBase):
    def test_acumulado_y_productos_que_hacen_el_80(self):
        a = self.producto('A', '80')
        b = self.producto('B', '15')
        c = self.producto('C', '5')
        self.venta(local(2026, 3, 10, 9), '100', productos=[a, b, c])

        p = est.pareto_productos(self.empresa, local(2026, 3, 1))

        self.assertEqual([x['nombre'] for x in p['productos']], ['A', 'B', 'C'])
        self.assertEqual([x['pct_acumulado'] for x in p['productos']], [80.0, 95.0, 100.0])
        self.assertEqual(p['productos_80'], 1)
        self.assertEqual(p['pct_catalogo_80'], 33.3)


class ClientesTests(EstadisticasBase):
    def test_nuevos_recurrentes_y_recompra(self):
        self.venta(local(2026, 1, 5, 9), '10', cliente=self.cliente)   # Ana ya compraba
        self.venta(local(2026, 3, 5, 9), '20', cliente=self.cliente)
        self.venta(local(2026, 3, 6, 9), '30', cliente=self.cliente)
        self.venta(local(2026, 3, 7, 9), '40', cliente=self.cliente2)  # Luis es nuevo

        c = est.clientes_nuevos_vs_recurrentes(self.empresa, local(2026, 3, 1))

        self.assertEqual(c['nuevos'], {'clientes': 1, 'monto': 40.0})
        self.assertEqual(c['recurrentes'], {'clientes': 1, 'monto': 50.0})
        self.assertEqual(c['tasa_recompra'], 50.0)


class VentasPorEstadoTests(EstadisticasBase):
    def test_etiquetas_legibles_y_solo_de_la_empresa(self):
        self.venta(local(2026, 3, 10, 9), '10')
        self.venta(local(2026, 3, 10, 9), '5', estado='pendiente_pago')
        self.venta(local(2026, 3, 10, 9), '7', empresa=self.otra)

        estados = {e['estado']: e for e in est.ventas_por_estado(self.empresa, local(2026, 3, 1))}

        self.assertEqual(set(estados), {'completada', 'pendiente_pago'})
        self.assertEqual(estados['completada']['label'], 'Completada')
        self.assertNotIn('_', estados['pendiente_pago']['label'])
        self.assertEqual(estados['pendiente_pago']['monto'], 5.0)


class StockBajoTests(EstadisticasBase):
    def test_solo_pocas_unidades_de_la_empresa(self):
        self.producto('Poco', '1', stock=1)
        self.producto('Mucho', '1', stock=10)
        self.producto('Ajeno', '1', stock=1, empresa=self.otra)
        self.assertEqual([p['nombre'] for p in est.productos_stock_bajo(self.empresa)], ['Poco'])


class MrrHistoricoTests(TestCase):
    def test_suma_suscripciones_vigentes_por_mes_y_prorratea_anual(self):
        mensual = Plan.objects.create(nombre='Básico', precio_mensual=Decimal('10'), precio_anual=Decimal('100'))
        e1 = Empresa.objects.create(nombre='E1', slug='e1')
        e2 = Empresa.objects.create(nombre='E2', slug='e2')
        Empresa.objects.filter(pk=e1.pk).update(fecha_creacion=local(2025, 12, 1))
        Empresa.objects.filter(pk=e2.pk).update(fecha_creacion=local(2026, 2, 10))
        SuscripcionEmpresa.objects.create(empresa=e1, plan=mensual, tipo_plan='mensual',
                                          fecha_vencimiento=local(2026, 4, 1))
        SuscripcionEmpresa.objects.create(empresa=e2, plan=mensual, tipo_plan='anual',
                                          fecha_vencimiento=local(2027, 2, 10))

        suspendida = Empresa.objects.create(nombre='E3', slug='e3', activa=False)
        SuscripcionEmpresa.objects.create(empresa=suspendida, plan=mensual, tipo_plan='mensual',
                                          fecha_vencimiento=local(2026, 4, 1))

        h = est.mrr_historico(meses=4, ahora=AHORA)

        self.assertEqual(h['labels'], ['Dic 2025', 'Ene 2026', 'Feb 2026', 'Mar 2026'])
        self.assertEqual(h['valores'], [10.0, 10.0, 18.33, 18.33])
