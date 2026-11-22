from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from empresas.testing import crear_empresa_con_dueno
from productos.models import Producto, TipoProducto
from ventas.models import Venta


class VistasGraficasBase(TestCase):
    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('tienda-a')
        self.otra, _ = crear_empresa_con_dueno('tienda-b')
        self.cliente = Cliente.objects.create(nombre='Ana', ruc_cedula='1111111111')
        # Con el onboarding pendiente, base.html arma el tour con la URL
        # 'completar_onboarding', que ya no existe (bug previo, fuera de este cambio).
        self.dueno.profile.onboarding_completado = True
        self.dueno.profile.save(update_fields=['onboarding_completado'])
        self.client.force_login(self.dueno)

    def venta(self, total, estado='completada', empresa=None):
        return Venta.objects.create(
            empresa=empresa or self.empresa, cliente=self.cliente,
            fecha=timezone.now(), total=Decimal(total), estado=estado,
        )


class DashboardTenantTests(VistasGraficasBase):
    def test_kpis_de_hoy_solo_cobrado_y_de_la_empresa(self):
        self.venta('100')
        self.venta('40', estado='pendiente_pago')
        self.venta('25', estado='anulada')
        self.venta('999', empresa=self.otra)

        resp = self.client.get(reverse('dashboard_tenant'))

        self.assertEqual(resp.status_code, 200)
        resumen = resp.context['resumen']
        self.assertEqual(resumen['hoy']['ingresos'], Decimal('100'))
        self.assertEqual(resumen['mes']['ingresos'], Decimal('100'))
        self.assertEqual(resumen['por_cobrar'], {'monto': Decimal('40'), 'cantidad': 1})
        self.assertContains(resp, 'id="acumuladoChart"')
        self.assertContains(resp, 'id="estadosChart"')
        self.assertContains(resp, 'acumulado-data')

    def test_no_repite_graficas_de_reportes(self):
        resp = self.client.get(reverse('dashboard_tenant'))
        self.assertNotContains(resp, 'productosVendidosChart')
        self.assertNotContains(resp, 'ventasChart')

    def test_alerta_de_stock_bajo_solo_de_la_empresa_dashboard(self):
        tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Ropa')
        tipo_b = TipoProducto.objects.create(empresa=self.otra, nombre='Ropa')
        Producto.objects.create(empresa=self.empresa, nombre='Camisa escasa', tipo_producto=tipo,
                                precio=Decimal('10'), stock=1, estado='disponible')
        Producto.objects.create(empresa=self.otra, nombre='Gorra ajena', tipo_producto=tipo_b,
                                precio=Decimal('10'), stock=1, estado='disponible')

        resp = self.client.get(reverse('dashboard_tenant'))

        self.assertContains(resp, 'Camisa escasa')
        self.assertNotContains(resp, 'Gorra ajena')


class ReportesTests(VistasGraficasBase):
    def test_kpis_solo_cobrado_y_de_la_empresa(self):
        self.venta('100')
        self.venta('40', estado='pendiente_pago')
        self.venta('25', estado='anulada')
        self.venta('999', empresa=self.otra)

        resp = self.client.get(reverse('tenant_reportes'), {'dias': 7})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['kpis']['ingresos'], Decimal('100'))
        self.assertEqual(resp.context['kpis']['ventas'], 1)
        self.assertEqual(sum(resp.context['serie_json']['ingresos']), 100.0)
        for grafica in ('ingresosChart', 'heatmapChart', 'paretoChart', 'categoriasChart'):
            self.assertContains(resp, f'id="{grafica}"')

    def test_periodo_invalido_vuelve_a_30_dias(self):
        for valor in ('100000', '-5', 'abc'):
            resp = self.client.get(reverse('tenant_reportes'), {'dias': valor})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context['dias'], 30)
            self.assertEqual(len(resp.context['serie_json']['labels']), 30)

    def test_anio_se_agrupa_por_mes(self):
        resp = self.client.get(reverse('tenant_reportes'), {'dias': 365})
        self.assertTrue(resp.context['serie_json']['mensual'])
        self.assertEqual(len(resp.context['serie_json']['labels']), 12)

    def test_exportaciones_siguen_funcionando(self):
        self.venta('100')
        self.venta('999', empresa=self.otra)

        csv_resp = self.client.get(reverse('tenant_reportes'), {'dias': 30, 'export': 'csv'})
        self.assertEqual(csv_resp.status_code, 200)
        contenido = csv_resp.content.decode('utf-8-sig')
        # Las dos ventas son de Ana: debe aparecer solo la de esta empresa.
        self.assertEqual(contenido.count('Ana'), 1)

        xls_resp = self.client.get(reverse('tenant_reportes'), {'dias': 30, 'export': 'excel'})
        self.assertEqual(xls_resp.status_code, 200)
        self.assertIn('spreadsheetml', xls_resp['Content-Type'])
