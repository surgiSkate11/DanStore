import csv
import io
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from empresas.models import Empresa
from empresas.testing import crear_empresa_con_dueno
from clientes.models import Cliente
from clientes.views import lista_clientes
from productos.models import Producto, TipoProducto
from ventas.models import DetalleVenta, Venta


class ClientesListViewRenderTest(TestCase):
    def test_lista_clientes_renders_existing_template(self):
        empresa = Empresa.objects.create(nombre='Tienda Test', slug='tienda-test')
        cliente = Cliente.objects.create(nombre='Ana', ruc_cedula='1712345678')
        cliente.empresas.add(empresa)

        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            username='tester',
            first_name='Tester',
            last_name='User',
            profile=SimpleNamespace(
                rol='owner',
                negocio_tipo='tienda',
                nombre_negocio='Tienda Test',
                onboarding_completado=True,
                empresa=empresa,
                get_vocabulario=lambda: {},
            ),
        )

        request = RequestFactory().get('/clientes/')
        request.user = user
        request.empresa = empresa

        response = lista_clientes(request)

        self.assertEqual(response.status_code, 200)
        self.assertIn('Clientes', response.content.decode('utf-8'))


class BaseTemplateClientesExportTest(SimpleTestCase):
    def test_base_template_includes_create_client_link_when_create_permission_exists(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            username='tester',
            first_name='Tester',
            last_name='User',
        )
        request = RequestFactory().get('/clientes/')
        request.user = user

        html = render_to_string(
            'base.html',
            {
                'user': user,
                'es_superadmin': False,
                'modulos_permitidos': ['clientes'],
                'permisos': {'clientes': ['crear']},
                'app_name': 'Tiendita',
                'tiene_credentials_google': False,
                'request': request,
            },
            request=request,
        )

        self.assertIn('Crear Cliente', html)
        self.assertIn('/clientes/crear/', html)

    def test_base_template_includes_clientes_csv_export_link(self):
        user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            username='tester',
            first_name='Tester',
            last_name='User',
        )
        request = RequestFactory().get('/clientes/')
        request.user = user

        html = render_to_string(
            'base.html',
            {
                'user': user,
                'es_superadmin': False,
                'modulos_permitidos': ['clientes'],
                'permisos': {'clientes': ['ver', 'crear']},
                'app_name': 'Tiendita',
                'tiene_credentials_google': False,
                'request': request,
            },
            request=request,
        )

        self.assertIn('Exportar CSV', html)
        self.assertIn('/clientes/exportar/csv/', html)


class AislamientoClientesTests(TestCase):
    """La empresa A nunca ve ni modifica clientes de la empresa B."""

    def setUp(self):
        # El middleware guarda el timeout de sesión en caché; no lo dejamos a otras pruebas.
        self.addCleanup(cache.clear)
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')

        # Control: un cliente propio de A debe verse siempre.
        self.cliente_a = Cliente.objects.create(
            nombre='Lucia Panadera', ruc_cedula='1111111111',
            telefono='0971111111', email='lucia@panaderia.test',
        )
        self.cliente_a.empresas.add(self.empresa_a)

        # Cliente que solo existe en B.
        self.cliente_b = Cliente.objects.create(
            nombre='Carlos Cafetero', ruc_cedula='2222222222',
            telefono='0988888888', email='carlos@cafeteria.test',
        )
        self.cliente_b.empresas.add(self.empresa_b)

        self.client.force_login(self.dueno_a)

    def _datos_b(self):
        return ['Carlos Cafetero', '2222222222', '0988888888', 'carlos@cafeteria.test']

    def _crear_venta(self, empresa, cliente, nombre_producto, precio):
        tipo = TipoProducto.objects.create(empresa=empresa, nombre=f'Tipo {nombre_producto}')
        producto = Producto.objects.create(
            empresa=empresa, nombre=nombre_producto, tipo_producto=tipo,
            precio=precio, stock=5, estado='disponible',
        )
        venta = Venta.objects.create(empresa=empresa, cliente=cliente)
        DetalleVenta.objects.create(venta=venta, producto=producto, precio_unitario=precio)
        venta.calcular_total()
        return venta

    def assertClienteBIntacto(self):
        self.cliente_b.refresh_from_db()
        self.assertEqual(self.cliente_b.nombre, 'Carlos Cafetero')
        self.assertEqual(self.cliente_b.telefono, '0988888888')
        self.assertEqual(self.cliente_b.email, 'carlos@cafeteria.test')
        self.assertEqual(list(self.cliente_b.empresas.all()), [self.empresa_b])

    def test_lista_clientes_no_muestra_clientes_de_otra_empresa(self):
        html = self.client.get(reverse('lista_clientes')).content.decode()
        self.assertIn('Lucia Panadera', html)
        for dato in self._datos_b():
            self.assertNotIn(dato, html)

    def test_exportar_csv_no_incluye_clientes_de_otra_empresa(self):
        respuesta = self.client.get(reverse('exportar_clientes_csv'))
        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode('utf-8')
        self.assertIn('Lucia Panadera', contenido)
        for dato in self._datos_b():
            self.assertNotIn(dato, contenido)

    def test_detalle_de_cliente_de_otra_empresa_da_404(self):
        respuesta = self.client.get(reverse('detalle_cliente', args=[self.cliente_b.id]))
        self.assertEqual(respuesta.status_code, 404)
        for dato in self._datos_b():
            self.assertNotIn(dato, respuesta.content.decode())

    def test_editar_cliente_de_otra_empresa_da_404_en_get(self):
        respuesta = self.client.get(reverse('editar_cliente', args=[self.cliente_b.id]))
        self.assertEqual(respuesta.status_code, 404)
        for dato in self._datos_b():
            self.assertNotIn(dato, respuesta.content.decode())

    def test_editar_cliente_de_otra_empresa_da_404_en_post_y_no_lo_modifica(self):
        respuesta = self.client.post(reverse('editar_cliente', args=[self.cliente_b.id]), {
            'nombre': 'Intruso Editor', 'ruc_cedula': '2222222222',
            'telefono': '0977777777', 'email': 'intruso@a.test',
        })
        self.assertEqual(respuesta.status_code, 404)
        self.assertClienteBIntacto()

    def test_detalle_de_cliente_compartido_no_muestra_ventas_de_otra_empresa(self):
        compartido = Cliente.objects.create(nombre='Cliente Compartido', ruc_cedula='3333333333')
        compartido.empresas.add(self.empresa_a, self.empresa_b)
        venta_a = self._crear_venta(self.empresa_a, compartido, 'Baguette de A', Decimal('10.00'))
        venta_b = self._crear_venta(self.empresa_b, compartido, 'Molinillo secreto de B', Decimal('500.00'))

        respuesta = self.client.get(reverse('detalle_cliente', args=[compartido.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['total_gastado'], venta_a.total)
        self.assertEqual(respuesta.context['cantidad_productos'], 1)
        html = respuesta.content.decode()
        self.assertIn('Baguette de A', html)
        self.assertNotIn('Molinillo secreto de B', html)
        self.assertNotIn(f'{venta_b.total:.2f}', html)

    def test_lista_y_csv_de_cliente_compartido_solo_suman_ventas_propias(self):
        compartido = Cliente.objects.create(nombre='Cliente Compartido', ruc_cedula='3333333333')
        compartido.empresas.add(self.empresa_a, self.empresa_b)
        venta_a = self._crear_venta(self.empresa_a, compartido, 'Baguette de A', Decimal('10.00'))
        venta_b = self._crear_venta(self.empresa_b, compartido, 'Molinillo secreto de B', Decimal('500.00'))

        respuesta = self.client.get(reverse('lista_clientes'))
        self.assertEqual(respuesta.context['total_ventas'], venta_a.total)
        csv_texto = self.client.get(reverse('exportar_clientes_csv')).content.decode('utf-8')
        filas = {fila[1]: fila for fila in csv.reader(io.StringIO(csv_texto.lstrip('﻿'))) if len(fila) > 5}
        self.assertEqual(Decimal(filas['3333333333'][4]), venta_a.total)
        self.assertNotIn(str(int(venta_b.total)), csv_texto)

    def test_crear_cliente_con_cedula_de_otra_empresa_se_rechaza_sin_asociarlo(self):
        respuesta = self.client.post(reverse('crear_cliente'), {
            'nombre': 'Intruso Creador', 'ruc_cedula': '2222222222',
            'tipo_identificacion': 'cedula',
        })
        # Se vuelve a mostrar el formulario con error; no hay redirección de éxito.
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Cliente.objects.filter(ruc_cedula='2222222222').count(), 1)
        self.assertClienteBIntacto()
        self.assertFalse(Cliente.objects.filter(empresas=self.empresa_a, ruc_cedula='2222222222').exists())
        html = respuesta.content.decode()
        for dato in ['Carlos Cafetero', '0988888888', 'carlos@cafeteria.test']:
            self.assertNotIn(dato, html)

    def _crear_consumidor_final(self):
        # Peor caso: la fila única y global ya está asociada a ambas empresas.
        final = Cliente.objects.create(nombre='CONSUMIDOR FINAL', ruc_cedula='9999999999')
        final.empresas.add(self.empresa_a, self.empresa_b)
        return final

    def test_consumidor_final_no_aparece_en_lista_ni_csv(self):
        self._crear_consumidor_final()
        lista = self.client.get(reverse('lista_clientes'))
        self.assertNotIn('CONSUMIDOR FINAL', lista.content.decode())
        self.assertNotIn('9999999999', lista.content.decode())
        self.assertEqual(lista.context['total_clientes'], 1)
        csv_texto = self.client.get(reverse('exportar_clientes_csv')).content.decode('utf-8')
        self.assertNotIn('CONSUMIDOR FINAL', csv_texto)
        self.assertNotIn('9999999999', csv_texto)

    def test_consumidor_final_no_se_puede_abrir_ni_editar(self):
        final = self._crear_consumidor_final()
        self.assertEqual(self.client.get(reverse('detalle_cliente', args=[final.id])).status_code, 404)
        self.assertEqual(self.client.get(reverse('editar_cliente', args=[final.id])).status_code, 404)
        respuesta = self.client.post(reverse('editar_cliente', args=[final.id]), {
            'nombre': 'Nombre Cambiado', 'ruc_cedula': '9999999999',
        })
        self.assertEqual(respuesta.status_code, 404)
        final.refresh_from_db()
        self.assertEqual(final.nombre, 'CONSUMIDOR FINAL')


class ClientesSinEmpresaTests(TestCase):
    def test_superadmin_sin_empresa_no_abre_clientes_sin_empresa(self):
        huerfano = Cliente.objects.create(nombre='Cliente Huerfano', ruc_cedula='5555555555')
        superadmin = User.objects.create_superuser('root', 'root@example.com', 'Clave-prueba-123')
        self.client.force_login(superadmin)
        respuesta = self.client.get(reverse('detalle_cliente', args=[huerfano.pk]))
        self.assertEqual(respuesta.status_code, 404)
