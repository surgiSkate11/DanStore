from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from empresas.models import Plan, SuscripcionEmpresa
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

    def test_no_expone_utilidad_ni_margen_a_empleado(self):
        from django.contrib.auth.models import User
        from usuarios.models import ModuloSaaS, RolEmpresa, UserProfile

        modulo, _ = ModuloSaaS.objects.get_or_create(codigo='reportes', defaults={'nombre': 'Reportes'})
        cargo = RolEmpresa.objects.create(empresa=self.empresa, nombre='Cajero')
        cargo.modulos_permitidos.add(modulo)
        empleado = User.objects.create_user(username='cajero', password='Clave-prueba-123')
        UserProfile.objects.update_or_create(user=empleado, defaults={
            'empresa': self.empresa, 'rol': 'employee', 'cargo': cargo, 'onboarding_completado': True})
        self.venta('100')
        self.client.force_login(empleado)

        resp = self.client.get(reverse('tenant_reportes'))

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(sum(resp.context['serie_json']['ingresos']), 100.0)
        self.assertNotIn('utilidad', resp.context['serie_json'])
        self.assertNotIn('margen', resp.context['serie_json'])
        self.assertNotContains(resp, '"utilidad"')
        self.assertNotContains(resp, '"margen"')

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


class DashboardSaasTests(VistasGraficasBase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser('root', 'root@example.com', 'Clave-prueba-123')

    def entrar_como_superadmin(self):
        self.client.force_login(self.admin)
        return self.client.get(reverse('dashboard_saas'))

    def test_dueno_de_empresa_recibe_403(self):
        # setUp deja logueado al dueño de una empresa (no superusuario)
        resp = self.client.get(reverse('dashboard_saas'))
        self.assertEqual(resp.status_code, 403)

    def test_historial_mrr_de_12_meses_sin_serie_inventada(self):
        resp = self.entrar_como_superadmin()

        self.assertEqual(resp.status_code, 200)
        historico = resp.context['mrr_historico']
        self.assertEqual(len(historico['labels']), 12)
        self.assertEqual(len(historico['valores']), 12)
        self.assertNotContains(resp, '120,250,450')
        self.assertContains(resp, 'id="mrr-data"')
        self.assertContains(resp, 'MRR estimado según suscripciones vigentes')

    def test_mrr_refleja_suscripcion_mensual_vigente(self):
        plan = Plan.objects.create(nombre='Pro', precio_mensual=Decimal('10'), precio_anual=Decimal('100'))
        sub = self.empresa.suscripcion
        sub.plan = plan
        sub.tipo_plan = 'mensual'
        sub.save()

        resp = self.entrar_como_superadmin()

        self.assertEqual(resp.context['mrr_estimado'], Decimal('10'))
        self.assertEqual(resp.context['mrr_historico']['valores'][-1], 10.0)
        self.assertEqual(resp.context['planes_labels'], ['Pro'])
        self.assertEqual(resp.context['planes_series'], [1])

    def test_mrr_ignora_suscripciones_vencidas_o_de_empresas_suspendidas(self):
        plan = Plan.objects.create(nombre='Pro', precio_mensual=Decimal('10'), precio_anual=Decimal('120'))
        sub = self.empresa.suscripcion
        sub.plan = plan
        sub.fecha_vencimiento = timezone.now() - timedelta(days=1)
        sub.save()
        sub_b = self.otra.suscripcion
        sub_b.plan = plan
        sub_b.save()
        self.otra.activa = False
        self.otra.save(update_fields=['activa'])

        resp = self.entrar_como_superadmin()

        self.assertEqual(resp.context['mrr_estimado'], 0)

    def test_mrr_anual_se_prorratea_en_12_meses(self):
        plan = Plan.objects.create(nombre='Anual', precio_mensual=Decimal('15'), precio_anual=Decimal('120'))
        sub = self.empresa.suscripcion
        sub.plan = plan
        sub.tipo_plan = 'anual'
        sub.save()

        resp = self.entrar_como_superadmin()

        self.assertEqual(resp.context['mrr_estimado'], Decimal('10'))

    def test_sin_planes_las_listas_van_vacias_y_no_se_inventa_un_dato(self):
        resp = self.entrar_como_superadmin()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['planes_labels'], [])
        self.assertEqual(resp.context['planes_series'], [])
        self.assertEqual(resp.context['mrr_estimado'], 0)
        self.assertNotContains(resp, 'Sin Planes')

