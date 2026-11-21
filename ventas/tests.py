import importlib
import json
import re
import uuid
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from unittest import mock

from django.apps import apps as django_apps
from django.contrib import admin as admin_site
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse

from clientes.models import Cliente
from empresas.models import Empresa
from empresas.testing import crear_empresa_con_dueno
from productos.models import Producto, TipoProducto
from ventas.models import ConfiguracionFactura, DetalleVenta, Venta
from ventas.views import crear_venta


class VentaFlowTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre='Mi Tienda', slug='mi-tienda')
        self.user = get_user_model().objects.create_user(
            username='admin',
            password='secret123',
            is_staff=True,
            is_superuser=True,
        )
        self.tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Ropa')
        self.producto = Producto.objects.create(
            empresa=self.empresa,
            nombre='Camisa básica',
            tipo_producto=self.tipo,
            precio=Decimal('100.00'),
            stock=3,
            estado='disponible',
        )
        self.cliente = Cliente.objects.create(
            nombre='Ana García',
            ruc_cedula='1234567890',
            email='ana@example.com',
            telefono='0999999999',
            direccion='Quito',
        )
        self.cliente.empresas.add(self.empresa)
        self.config = ConfiguracionFactura.objects.create(
            empresa=self.empresa,
            porcentaje_iva=Decimal('15.00'),
            texto_consumidor_final='CONSUMIDOR FINAL',
            id_consumidor_final='9999999999',
        )

    def test_crear_venta_aplica_iva_y_repite_productos(self):
        factory = RequestFactory()
        request = factory.post(
            reverse('crear_venta'),
            {
                'cliente_id': str(self.cliente.id),
                'productos': [
                    str(self.producto.id),
                    str(self.producto.id),
                    str(self.producto.id),
                ],
                'descuento': '0',
                'envio': '0',
                'otros_gastos': '0',
                'descripcion_otros': '',
                'notas': '',
                'metodo_pago': 'efectivo',
                'ruc_cliente': '',
            },
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user
        request.empresa = self.empresa

        response = crear_venta(request)

        self.assertEqual(response.status_code, 302)
        venta = Venta.objects.get(cliente=self.cliente)
        self.assertEqual(venta.detalles.count(), 3)
        self.assertEqual(venta.subtotal, Decimal('300.00'))
        self.assertEqual(venta.iva, Decimal('45.00'))
        self.assertEqual(venta.total, Decimal('345.00'))
        
        # Verificar que el stock se haya actualizado correctamente
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 0)  # Empezó con 3, se vendieron 3
        self.assertEqual(self.producto.estado, 'vendido')

    def test_crear_venta_con_factura_sin_datos_usa_cliente_default(self):
        factory = RequestFactory()
        request = factory.post(
            reverse('crear_venta'),
            {
                'factura_sin_datos': '1',
                'productos': [str(self.producto.id)],
                'descuento': '0',
                'envio': '0',
                'otros_gastos': '0',
                'descripcion_otros': '',
                'notas': '',
                'metodo_pago': 'efectivo',
                'ruc_cliente': '',
            },
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user
        request.empresa = self.empresa

        response = crear_venta(request)

        self.assertEqual(response.status_code, 302)
        venta = Venta.objects.order_by('-id').first()
        self.assertEqual(venta.cliente.nombre, 'CONSUMIDOR FINAL')
        self.assertEqual(venta.ruc_cliente, '9999999999')

    def test_crear_venta_redirige_al_detalle_sin_abrir_previa_automatica(self):
        """Después de crear la venta, debe quedarse en el detalle con opciones y no forzar la vista previa."""
        factory = RequestFactory()
        request = factory.post(
            reverse('crear_venta'),
            {
                'cliente_id': str(self.cliente.id),
                'productos': [str(self.producto.id)],
                'descuento': '0',
                'envio': '0',
                'otros_gastos': '0',
                'descripcion_otros': '',
                'notas': '',
                'metodo_pago': 'efectivo',
                'ruc_cliente': '',
            },
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user
        request.empresa = self.empresa

        response = crear_venta(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url_detalle_nueva(Venta.objects.latest('id').id))

    def test_productos_con_stock_restante_no_quedan_en_estado_vendido(self):
        """Si aún queda stock, el producto debe seguir disponible."""
        self.producto.stock = 5
        self.producto.estado = 'disponible'
        self.producto.save(update_fields=['stock', 'estado'])

        factory = RequestFactory()
        request = factory.post(
            reverse('crear_venta'),
            {
                'cliente_id': str(self.cliente.id),
                'productos': [str(self.producto.id)],
                'descuento': '0',
                'envio': '0',
                'otros_gastos': '0',
                'descripcion_otros': '',
                'notas': '',
                'metodo_pago': 'efectivo',
                'ruc_cliente': '',
            },
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user
        request.empresa = self.empresa

        response = crear_venta(request)

        self.assertEqual(response.status_code, 302)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 4)
        self.assertEqual(self.producto.estado, 'disponible')

    def test_no_puede_vender_mas_stock_del_disponible(self):
        """Validar que no se puede vender más productos del stock disponible"""
        factory = RequestFactory()
        request = factory.post(
            reverse('crear_venta'),
            {
                'cliente_id': str(self.cliente.id),
                'productos': [
                    str(self.producto.id),
                    str(self.producto.id),
                    str(self.producto.id),
                    str(self.producto.id),  # 4 copias, pero solo hay 3 en stock
                ],
                'descuento': '0',
                'envio': '0',
                'otros_gastos': '0',
                'descripcion_otros': '',
                'notas': '',
                'metodo_pago': 'efectivo',
                'ruc_cliente': '',
            },
        )
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        request.user = self.user
        request.empresa = self.empresa

        response = crear_venta(request)

        # La vista debe redirigir de vuelta debido al error de stock
        self.assertEqual(response.status_code, 302)
        
        # No debe haber creado una venta
        ventas_creadas = Venta.objects.filter(cliente=self.cliente)
        self.assertEqual(ventas_creadas.count(), 0)


class AislamientoVentasTests(TestCase):
    """La empresa A nunca ve ni modifica datos de ventas de la empresa B."""

    def setUp(self):
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')

        # Datos de A (control: lo propio sí debe verse)
        tipo_a = TipoProducto.objects.create(empresa=self.empresa_a, nombre='Pan')
        self.producto_a = Producto.objects.create(
            empresa=self.empresa_a, nombre='Baguette', tipo_producto=tipo_a,
            precio=Decimal('1.00'), stock=5, estado='disponible',
        )
        self.cliente_a = Cliente.objects.create(nombre='Lucia Panadera', ruc_cedula='1111111111')
        self.cliente_a.empresas.add(self.empresa_a)
        self.venta_a = Venta.objects.create(empresa=self.empresa_a, cliente=self.cliente_a)
        DetalleVenta.objects.create(venta=self.venta_a, producto=self.producto_a, precio_unitario=Decimal('1.00'))
        self.venta_a.calcular_total()

        # Datos de B
        tipo_b = TipoProducto.objects.create(empresa=self.empresa_b, nombre='Bebida caliente')
        self.producto_b = Producto.objects.create(
            empresa=self.empresa_b, nombre='Capuchino', tipo_producto=tipo_b,
            precio=Decimal('2.00'), stock=10, estado='disponible',
        )
        self.producto_reservado_b = Producto.objects.create(
            empresa=self.empresa_b, nombre='Molinillo reservado', tipo_producto=tipo_b,
            precio=Decimal('7.00'), stock=1, estado='reservado', vendido_a='Beto Cafetero',
        )
        self.cliente_b = Cliente.objects.create(
            nombre='Carlos Cafetero', ruc_cedula='2222222222', telefono='0988888888',
        )
        self.cliente_b.empresas.add(self.empresa_b)
        self.venta_b = Venta.objects.create(
            empresa=self.empresa_b, cliente=self.cliente_b,
            descuento=Decimal('0'), notas='Nota de B', metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(venta=self.venta_b, producto=self.producto_b, precio_unitario=Decimal('2.00'))
        self.venta_b.calcular_total()

        self.client.force_login(self.dueno_a)

    def datos_venta(self, **extra):
        datos = {
            'descuento': '0', 'envio': '0', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': '', 'metodo_pago': 'efectivo',
            'ruc_cliente': '',
        }
        datos.update(extra)
        return datos

    def assertVentaBIntacta(self):
        self.venta_b.refresh_from_db()
        self.assertEqual(self.venta_b.notas, 'Nota de B')
        self.assertEqual(self.venta_b.descuento, Decimal('0'))
        self.assertEqual(self.venta_b.metodo_pago, 'efectivo')
        self.assertEqual(self.venta_b.total, Decimal('2.30'))

    def assertClienteBIntacto(self):
        self.cliente_b.refresh_from_db()
        self.assertEqual(self.cliente_b.nombre, 'Carlos Cafetero')
        self.assertEqual(list(self.cliente_b.empresas.all()), [self.empresa_b])

    def assertProductoBIntacto(self):
        self.producto_b.refresh_from_db()
        self.assertEqual(self.producto_b.stock, 10)
        self.assertEqual(self.producto_b.estado, 'disponible')
        self.assertFalse(DetalleVenta.objects.filter(producto=self.producto_b).exclude(venta=self.venta_b).exists())

    def test_lista_ventas_no_muestra_datos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('lista_ventas'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Lucia Panadera')
        for ajeno in ('Carlos Cafetero', 'Capuchino', 'Molinillo reservado', 'Beto Cafetero'):
            self.assertNotContains(respuesta, ajeno)

    def test_lista_deudas_no_muestra_datos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('lista_deudas'))
        self.assertEqual(respuesta.status_code, 200)
        for ajeno in ('Carlos Cafetero', 'Capuchino', 'Molinillo reservado', 'Beto Cafetero'):
            self.assertNotContains(respuesta, ajeno)

    def test_formulario_de_venta_no_ofrece_clientes_ni_productos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'data-titulo="Baguette"')  # la tarjeta lleva el nombre del producto
        for ajeno in ('Carlos Cafetero', 'capuchino', 'Bebida caliente', 'Beto Cafetero'):
            self.assertNotContains(respuesta, ajeno)

    def test_detalle_y_factura_de_venta_ajena_dan_404(self):
        for nombre_url in ('detalle_venta', 'factura_pdf'):
            with self.subTest(nombre_url):
                respuesta = self.client.get(reverse(nombre_url, args=[self.venta_b.pk]))
                self.assertEqual(respuesta.status_code, 404)

    def test_editar_venta_ajena_da_404_y_no_la_modifica(self):
        url = reverse('editar_venta', args=[self.venta_b.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        respuesta = self.client.post(url, {
            'descuento': '1', 'envio': '5', 'otros_gastos': '3',
            'descripcion_otros': 'Robo', 'notas': 'Hackeada', 'metodo_pago': 'tarjeta',
        })
        self.assertEqual(respuesta.status_code, 404)
        self.assertVentaBIntacta()

    def test_comprobante_de_deuda_con_cliente_de_otra_empresa_no_muestra_sus_datos(self):
        respuesta = self.client.get(reverse('generar_comprobante_deuda_pdf', args=['Beto Cafetero']))
        # Sin productos separados propios con ese nombre, la vista redirige a la lista de deudas
        self.assertRedirects(respuesta, reverse('lista_deudas'), fetch_redirect_response=False)
        self.assertNotEqual(respuesta.get('Content-Type'), 'application/pdf')

    def test_crear_venta_con_producto_de_otra_empresa_no_crea_venta_ni_toca_su_stock(self):
        ventas_antes = Venta.objects.count()
        self.client.post(reverse('crear_venta'), self.datos_venta(
            cliente_id=str(self.cliente_a.pk), productos=[str(self.producto_b.pk)],
        ))
        self.assertEqual(Venta.objects.count(), ventas_antes)
        self.assertProductoBIntacto()

    def test_crear_venta_mezclando_producto_ajeno_solo_vende_el_propio(self):
        self.client.post(reverse('crear_venta'), self.datos_venta(
            cliente_id=str(self.cliente_a.pk),
            productos=[str(self.producto_a.pk), str(self.producto_b.pk)],
        ))
        self.assertProductoBIntacto()
        self.producto_a.refresh_from_db()
        self.assertEqual(self.producto_a.stock, 4)

    def test_crear_venta_con_cliente_id_de_otra_empresa_se_rechaza(self):
        ventas_antes = Venta.objects.count()
        respuesta = self.client.post(reverse('crear_venta'), self.datos_venta(
            cliente_id=str(self.cliente_b.pk), productos=[str(self.producto_a.pk)],
        ))
        self.assertRedirects(respuesta, reverse('crear_venta'), fetch_redirect_response=False)
        self.assertEqual(Venta.objects.count(), ventas_antes)
        self.assertClienteBIntacto()
        self.producto_a.refresh_from_db()
        self.assertEqual(self.producto_a.stock, 5)

    def test_factura_sin_datos_con_ruc_de_cliente_ajeno_no_lo_renombra_ni_lo_asocia(self):
        """L7: el RUC enviado por el usuario no debe alcanzar a un cliente de otra empresa."""
        self.client.post(reverse('crear_venta'), self.datos_venta(
            factura_sin_datos='1', ruc_cliente=self.cliente_b.ruc_cedula,
            productos=[str(self.producto_a.pk)],
        ))
        self.assertClienteBIntacto()
        self.assertFalse(Venta.objects.filter(empresa=self.empresa_a, cliente=self.cliente_b).exists())

    def test_modal_crear_cliente_con_ruc_de_otra_empresa_da_409(self):
        respuesta = self.client.post(reverse('crear_venta'), {
            'action': 'crear_cliente', 'nombre': 'Intruso', 'ruc_cedula': self.cliente_b.ruc_cedula,
        })
        self.assertEqual(respuesta.status_code, 409)
        self.assertFalse(respuesta.json()['success'])
        self.assertNotIn('Carlos', respuesta.content.decode())
        self.assertClienteBIntacto()


class CrearVentaRevisionGGATests(TestCase):
    """Huecos encontrados por GGA en crear_venta."""

    def setUp(self):
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')
        # Cliente compartido: compró en B, y A ya lo tiene asociado.
        self.cliente = Cliente.objects.create(nombre='Cliente Compartido', ruc_cedula='3333333333')
        self.cliente.empresas.add(self.empresa_a, self.empresa_b)
        Venta.objects.create(empresa=self.empresa_b, cliente=self.cliente)
        Venta.objects.create(empresa=self.empresa_b, cliente=self.cliente)

    def test_modal_no_cuenta_compras_hechas_en_otra_empresa(self):
        self.client.force_login(self.dueno_a)
        respuesta = self.client.post(reverse('crear_venta'), {
            'action': 'crear_cliente', 'nombre': 'Cliente Compartido', 'ruc_cedula': '3333333333',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()['cliente']['compras'], 0)

    def test_modal_no_muestra_el_error_interno(self):
        self.client.force_login(self.dueno_a)
        with mock.patch.object(Cliente.objects, 'create', side_effect=IntegrityError('duplicate key value')):
            respuesta = self.client.post(reverse('crear_venta'), {
                'action': 'crear_cliente', 'nombre': 'Nuevo', 'ruc_cedula': '4444444444',
            })
        cuerpo = respuesta.json()
        self.assertFalse(cuerpo['success'])
        self.assertEqual(cuerpo['error'], 'No se pudo crear el cliente. Intenta de nuevo.')

    def test_sin_empresa_no_crea_ventas_en_otra_empresa(self):
        superadmin = get_user_model().objects.create_superuser('root', 'root@example.com', 'Clave-prueba-123')
        self.client.force_login(superadmin)
        ventas_antes = Venta.objects.count()
        respuesta = self.client.post(reverse('crear_venta'), {
            'factura_sin_datos': '1', 'productos': ['1'],
            'descuento': '0', 'envio': '0', 'otros_gastos': '0', 'metodo_pago': 'efectivo',
        })
        self.assertRedirects(respuesta, reverse('lista_ventas'), fetch_redirect_response=False)
        self.assertEqual(Venta.objects.count(), ventas_antes)
        self.assertFalse(ConfiguracionFactura.objects.exists())


class ConsumidorFinalCompartidoTests(TestCase):
    """L9: el cliente consumidor final es una sola fila para todas las empresas;
    el nombre que le da una empresa no debe verse en las ventas de otra."""

    def setUp(self):
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, self.dueno_b = crear_empresa_con_dueno('cafeteria')
        ConfiguracionFactura.objects.create(
            empresa=self.empresa_a, texto_consumidor_final='CONSUMIDOR FINAL',
        )
        ConfiguracionFactura.objects.create(
            empresa=self.empresa_b, texto_consumidor_final='Consumidor Final Cafeteria Beto',
        )
        tipo_a = TipoProducto.objects.create(empresa=self.empresa_a, nombre='Pan')
        self.producto_a = Producto.objects.create(
            empresa=self.empresa_a, nombre='Baguette', tipo_producto=tipo_a,
            precio=Decimal('1.00'), stock=5, estado='disponible',
        )
        tipo_b = TipoProducto.objects.create(empresa=self.empresa_b, nombre='Bebida caliente')
        self.producto_b = Producto.objects.create(
            empresa=self.empresa_b, nombre='Capuchino', tipo_producto=tipo_b,
            precio=Decimal('2.00'), stock=5, estado='disponible',
        )

    def vender_sin_datos(self, usuario, producto):
        self.client.force_login(usuario)
        respuesta = self.client.post(reverse('crear_venta'), {
            'factura_sin_datos': '1', 'productos': [str(producto.pk)],
            'descuento': '0', 'envio': '0', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': '', 'metodo_pago': 'efectivo',
            'ruc_cliente': '',
        })
        self.assertEqual(respuesta.status_code, 302)

    def vender_sin_datos_en_ambas_empresas(self):
        self.vender_sin_datos(self.dueno_b, self.producto_b)
        self.vender_sin_datos(self.dueno_a, self.producto_a)
        self.venta_b = Venta.objects.get(empresa=self.empresa_b)
        self.venta_a = Venta.objects.get(empresa=self.empresa_a)

    def test_venta_guarda_el_nombre_de_consumidor_final_de_su_empresa(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.assertEqual(self.venta_a.nombre_cliente, 'CONSUMIDOR FINAL')
        self.assertEqual(self.venta_b.nombre_cliente, 'Consumidor Final Cafeteria Beto')

    def test_la_empresa_a_no_renombra_el_cliente_compartido(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.assertEqual(self.venta_a.cliente_id, self.venta_b.cliente_id)
        compartido = Cliente.objects.get(pk=self.venta_a.cliente_id)
        self.assertEqual(compartido.nombre, 'Consumidor Final Cafeteria Beto')

    def test_la_empresa_b_tampoco_renombra_el_cliente_compartido(self):
        self.vender_sin_datos(self.dueno_b, self.producto_b)
        ConfiguracionFactura.objects.filter(empresa=self.empresa_b).update(
            texto_consumidor_final='Otro nombre de Beto',
        )
        self.vender_sin_datos(self.dueno_b, self.producto_b)
        compartido = Cliente.objects.get(ruc_cedula='9999999999')
        self.assertEqual(compartido.nombre, 'Consumidor Final Cafeteria Beto')

    def test_lista_y_detalle_de_a_no_muestran_el_nombre_que_puso_b(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.client.force_login(self.dueno_a)
        lista = self.client.get(reverse('lista_ventas'))
        self.assertContains(lista, 'CONSUMIDOR FINAL')
        self.assertNotContains(lista, 'Cafeteria Beto')
        detalle = self.client.get(reverse('detalle_venta', args=[self.venta_a.pk]))
        self.assertContains(detalle, 'CONSUMIDOR FINAL')
        self.assertNotContains(detalle, 'Cafeteria Beto')
        factura = self.client.get(reverse('factura_pdf', args=[self.venta_a.pk]) + '?html=1')
        self.assertContains(factura, 'CONSUMIDOR FINAL')
        self.assertNotContains(factura, 'Cafeteria Beto')

    def test_venta_de_b_conserva_su_propio_nombre(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.client.force_login(self.dueno_b)
        lista = self.client.get(reverse('lista_ventas'))
        self.assertContains(lista, 'Consumidor Final Cafeteria Beto')
        detalle = self.client.get(reverse('detalle_venta', args=[self.venta_b.pk]))
        self.assertContains(detalle, 'Consumidor Final Cafeteria Beto')

    def test_el_producto_vendido_de_a_no_lleva_el_nombre_de_b(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.producto_a.refresh_from_db()
        self.assertNotIn('Cafeteria Beto', self.producto_a.vendido_a)

    def test_formulario_de_venta_no_lista_al_consumidor_final(self):
        self.vender_sin_datos_en_ambas_empresas()
        self.client.force_login(self.dueno_a)
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('9999999999', [c['ruc_cedula'] for c in respuesta.context['clientes']])
        self.assertNotContains(respuesta, 'Cafeteria Beto')

    def test_venta_con_cliente_normal_guarda_el_nombre_del_cliente(self):
        cliente = Cliente.objects.create(nombre='Lucia Panadera', ruc_cedula='1111111111')
        cliente.empresas.add(self.empresa_a)
        self.client.force_login(self.dueno_a)
        self.client.post(reverse('crear_venta'), {
            'cliente_id': str(cliente.pk), 'productos': [str(self.producto_a.pk)],
            'descuento': '0', 'envio': '0', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': '', 'metodo_pago': 'efectivo',
        })
        self.assertEqual(Venta.objects.get(empresa=self.empresa_a).nombre_cliente, 'Lucia Panadera')

    def test_migracion_copia_el_nombre_del_cliente_a_las_ventas_existentes(self):
        migracion = importlib.import_module('ventas.migrations.0007_venta_nombre_cliente')
        cliente = Cliente.objects.create(nombre='Lucia Panadera', ruc_cedula='1111111111')
        con_nombre = Venta.objects.create(empresa=self.empresa_a, cliente=cliente)
        ya_guardada = Venta.objects.create(
            empresa=self.empresa_a, cliente=cliente, nombre_cliente='Nombre propio',
        )
        migracion.copiar_nombre_del_cliente(django_apps, None)
        con_nombre.refresh_from_db()
        ya_guardada.refresh_from_db()
        self.assertEqual(con_nombre.nombre_cliente, 'Lucia Panadera')
        self.assertEqual(ya_guardada.nombre_cliente, 'Nombre propio')

    def test_migracion_usa_el_texto_de_consumidor_final_de_cada_empresa(self):
        migracion = importlib.import_module('ventas.migrations.0007_venta_nombre_cliente')
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa_a, defaults={'texto_consumidor_final': 'CONSUMIDOR FINAL'},
        )
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa_b, defaults={'texto_consumidor_final': 'Consumidor Final Cafeteria Beto'},
        )
        # La fila compartida quedó con el nombre de la última empresa que vendió (B).
        compartido, _ = Cliente.objects.update_or_create(
            ruc_cedula='9999999999', defaults={'nombre': 'Consumidor Final Cafeteria Beto'},
        )
        venta_a = Venta.objects.create(empresa=self.empresa_a, cliente=compartido)
        venta_b = Venta.objects.create(empresa=self.empresa_b, cliente=compartido)
        Venta.objects.filter(pk__in=[venta_a.pk, venta_b.pk]).update(nombre_cliente='')
        migracion.copiar_nombre_del_cliente(django_apps, None)
        venta_a.refresh_from_db()
        venta_b.refresh_from_db()
        self.assertEqual(venta_a.nombre_cliente, 'CONSUMIDOR FINAL')
        self.assertEqual(venta_b.nombre_cliente, 'Consumidor Final Cafeteria Beto')


def mensajes(response):
    """Textos de los mensajes que dejó la petición (sin renderizar la plantilla)."""
    return [str(m) for m in get_messages(response.wsgi_request)]


def url_detalle_nueva(venta_id):
    """Adónde lleva guardar una venta nueva: al detalle, con el panel de acciones rápidas."""
    return reverse('detalle_venta', args=[venta_id]) + '?nueva=1'


class PorcentajeIvaConfiguracionTests(TestCase):
    """S2: el % de IVA solo admite 0–30 con hasta 2 decimales, validado en el servidor."""

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('iva-tienda')
        self.config = ConfiguracionFactura.obtener_configuracion(self.empresa.id)
        self.config.porcentaje_iva = Decimal('12.00')
        self.config.direccion_empresa = 'Dirección original'
        self.config.save()
        self.client.force_login(self.dueno)
        self.url = reverse('configuracion_facturas')

    def datos(self, **extra):
        datos = {
            'nombre_empresa': '',
            'direccion_empresa': 'Dirección nueva',
            'telefono_empresa': '0991234567',
            'email_empresa': 'tienda@example.com',
            'mensaje_factura': 'Gracias',
            'mensaje_deuda': 'Debes',
            'porcentaje_iva': '15',
            'texto_consumidor_final': 'CONSUMIDOR FINAL',
            'id_consumidor_final': '9999999999',
        }
        datos.update(extra)
        return datos

    def assertConfigIntacta(self):
        self.config.refresh_from_db()
        self.assertEqual(self.config.porcentaje_iva, Decimal('12.00'))
        self.assertEqual(self.config.direccion_empresa, 'Dirección original')

    def test_valores_invalidos_se_rechazan_con_mensaje_y_no_guardan_nada(self):
        negativo = 'El porcentaje de IVA no puede ser negativo.'
        excedido = 'El porcentaje de IVA no puede ser mayor a 30.'
        no_numero = 'El porcentaje de IVA debe ser un número válido.'
        casos = {
            '-5': negativo,
            '-0.01': negativo,
            '30.01': excedido,
            '150': excedido,
            '1e9': excedido,
            '15.555': 'El porcentaje de IVA admite como máximo 2 decimales.',
            'abc': no_numero,
            'NaN': no_numero,
            'Infinity': no_numero,
            '-Infinity': no_numero,
            '': 'El porcentaje de IVA es obligatorio.',
        }
        for valor, mensaje in casos.items():
            with self.subTest(valor=valor):
                response = self.client.post(self.url, self.datos(porcentaje_iva=valor))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, mensaje)
                self.assertConfigIntacta()

    def test_valores_validos_se_guardan(self):
        for valor in ['0', '12', '15', '15.5', '30', '0.01', '29.99']:
            with self.subTest(valor=valor):
                response = self.client.post(self.url, self.datos(porcentaje_iva=valor))
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response.url, self.url)
                self.config.refresh_from_db()
                self.assertEqual(self.config.porcentaje_iva, Decimal(valor))

    def test_sin_el_campo_conserva_el_porcentaje_actual(self):
        datos = self.datos()
        del datos['porcentaje_iva']
        response = self.client.post(self.url, datos)
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.porcentaje_iva, Decimal('12.00'))
        self.assertEqual(self.config.direccion_empresa, 'Dirección nueva')

    def test_los_demas_campos_siguen_guardandose(self):
        response = self.client.post(self.url, self.datos(
            nombre_empresa='Mi Negocio SA', porcentaje_iva='8',
            texto_consumidor_final='CLIENTE GENERAL', id_consumidor_final='1111111111',
        ))
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.nombre_empresa, 'Mi Negocio SA')
        self.assertTrue(self.config.nombre_personalizado)
        self.assertEqual(self.config.direccion_empresa, 'Dirección nueva')
        self.assertEqual(self.config.telefono_empresa, '0991234567')
        self.assertEqual(self.config.email_empresa, 'tienda@example.com')
        self.assertEqual(self.config.mensaje_factura, 'Gracias')
        self.assertEqual(self.config.mensaje_deuda, 'Debes')
        self.assertEqual(self.config.porcentaje_iva, Decimal('8.00'))
        self.assertEqual(self.config.texto_consumidor_final, 'CLIENTE GENERAL')
        self.assertEqual(self.config.id_consumidor_final, '1111111111')

    def test_nombre_vacio_vuelve_al_de_la_empresa(self):
        self.config.nombre_empresa = 'Otro'
        self.config.nombre_personalizado = True
        self.config.save()
        response = self.client.post(self.url, self.datos(nombre_empresa=''))
        self.assertEqual(response.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.nombre_empresa, self.empresa.nombre)
        self.assertFalse(self.config.nombre_personalizado)

    def test_el_campo_del_formulario_declara_el_rango(self):
        html = self.client.get(self.url).content.decode()
        inicio = html.rindex('<input', 0, html.index('name="porcentaje_iva"'))
        campo = html[inicio:html.index('>', inicio)]
        self.assertIn('min="0"', campo)
        self.assertIn('max="30"', campo)
        self.assertIn('step="0.01"', campo)


class PorcentajeIvaAdminTests(TestCase):
    """El formulario del admin de Django también rechaza porcentajes fuera de rango (validadores del modelo)."""

    def setUp(self):
        self.empresa, _ = crear_empresa_con_dueno('iva-admin')
        self.config = ConfiguracionFactura.obtener_configuracion(self.empresa.id)
        self.config.porcentaje_iva = Decimal('12.00')
        self.config.save()
        request = RequestFactory().get('/')
        request.user = get_user_model().objects.create_superuser('root-iva', 'root@example.com', 'Clave-prueba-123')
        modelo_admin = admin_site.site._registry[ConfiguracionFactura]
        self.formulario = modelo_admin.get_form(request, self.config)

    def formulario_con(self, iva):
        return self.formulario({
            'empresa': self.empresa.pk,
            'nombre_empresa': 'Iva Admin',
            'ruc_empresa': '', 'direccion_empresa': '', 'telefono_empresa': '', 'email_empresa': '',
            'porcentaje_iva': iva,
            'texto_consumidor_final': 'CONSUMIDOR FINAL',
            'id_consumidor_final': '9999999999',
            'mensaje_factura': '', 'mensaje_deuda': '',
        }, instance=self.config)

    def test_admin_rechaza_valores_fuera_de_rango(self):
        casos = {
            '-5': 'El porcentaje de IVA no puede ser negativo.',
            '150': 'El porcentaje de IVA no puede ser mayor a 30.',
            '30.01': 'El porcentaje de IVA no puede ser mayor a 30.',
        }
        for valor, mensaje in casos.items():
            with self.subTest(valor=valor):
                form = self.formulario_con(valor)
                self.assertFalse(form.is_valid())
                self.assertEqual(form.errors['porcentaje_iva'], [mensaje])

    def test_admin_acepta_valores_dentro_del_rango(self):
        for valor in ['0', '15.5', '30']:
            with self.subTest(valor=valor):
                form = self.formulario_con(valor)
                self.assertTrue(form.is_valid(), form.errors)


class GastosVentaBase(TestCase):
    """Preparación común: empresa con dueño, un producto de $100 con stock 3 y un cliente."""

    CAMPOS = {'descuento': 'descuento', 'envio': 'envío', 'otros_gastos': 'otros gastos'}

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('gastos-tienda')
        tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Ropa')
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Camisa', tipo_producto=tipo,
            precio=Decimal('100.00'), stock=3, estado='disponible',
        )
        self.cliente = Cliente.objects.create(nombre='Ana García', ruc_cedula='1234567890')
        self.cliente.empresas.add(self.empresa)
        self.client.force_login(self.dueno)

    def datos(self, unidades=1, **extra):
        datos = {
            'cliente_id': str(self.cliente.id),
            'productos': [str(self.producto.id)] * unidades,
            'descuento': '0', 'envio': '0', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': '', 'metodo_pago': 'efectivo',
            'ruc_cliente': '',
        }
        datos.update(extra)
        return datos

    def casos_invalidos(self, campo):
        etiqueta = self.CAMPOS[campo]
        texto = f'Ingresa un valor numérico válido para {etiqueta}.'
        return {
            'abc': texto,
            'NaN': texto,
            'Infinity': texto,
            '1e3': texto,
            '-1': f'El valor de {etiqueta} no puede ser negativo.',
            '-0.01': f'El valor de {etiqueta} no puede ser negativo.',
            '1.234': f'El valor de {etiqueta} admite como máximo 2 decimales.',
            '100000000': f'El valor de {etiqueta} no puede superar 99999999.99.',
        }


class GastosCrearVentaTests(GastosVentaBase):
    """S3 en crear_venta: descuento, envío y otros gastos se validan en el servidor."""

    def assertNadaCambio(self):
        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(DetalleVenta.objects.count(), 0)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)
        self.assertEqual(self.producto.estado, 'disponible')

    def test_valores_invalidos_no_crean_venta_ni_tocan_el_stock(self):
        for campo in self.CAMPOS:
            for valor, mensaje in self.casos_invalidos(campo).items():
                with self.subTest(campo=campo, valor=valor):
                    response = self.client.post(reverse('crear_venta'), self.datos(**{campo: valor}))
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, reverse('crear_venta'))
                    self.assertIn(mensaje, mensajes(response))
                    self.assertNadaCambio()

    def test_descuento_mayor_al_subtotal_se_rechaza(self):
        response = self.client.post(reverse('crear_venta'), self.datos(descuento='100.01'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertIn('El descuento no puede ser mayor al subtotal ($100.00).', mensajes(response))
        self.assertNadaCambio()

    def test_descuento_se_compara_con_el_subtotal_de_todas_las_unidades(self):
        response = self.client.post(reverse('crear_venta'), self.datos(unidades=2, descuento='200.01'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('El descuento no puede ser mayor al subtotal ($200.00).', mensajes(response))
        self.assertNadaCambio()

        response = self.client.post(reverse('crear_venta'), self.datos(unidades=2, descuento='150'))
        self.assertEqual(response.status_code, 302)
        venta = Venta.objects.get()
        self.assertEqual(venta.descuento, Decimal('150.00'))

    def test_descuento_igual_al_subtotal_se_acepta(self):
        response = self.client.post(reverse('crear_venta'), self.datos(descuento='100'))
        venta = Venta.objects.get()
        self.assertRedirects(response, url_detalle_nueva(venta.id))
        self.assertEqual(venta.descuento, Decimal('100.00'))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 2)

    def test_valores_validos_se_guardan(self):
        response = self.client.post(
            reverse('crear_venta'),
            self.datos(descuento='10.5', envio='5', otros_gastos='2.25'),
        )
        venta = Venta.objects.get()
        self.assertRedirects(response, url_detalle_nueva(venta.id))
        self.assertEqual(venta.descuento, Decimal('10.50'))
        self.assertEqual(venta.envio, Decimal('5.00'))
        self.assertEqual(venta.otros_gastos, Decimal('2.25'))
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 2)

    def test_valores_vacios_cuentan_como_cero(self):
        response = self.client.post(
            reverse('crear_venta'),
            self.datos(descuento='', envio=' ', otros_gastos=''),
        )
        venta = Venta.objects.get()
        self.assertRedirects(response, url_detalle_nueva(venta.id))
        self.assertEqual((venta.descuento, venta.envio, venta.otros_gastos), (0, 0, 0))

    def test_el_formulario_declara_los_limites_de_los_campos(self):
        html = self.client.get(reverse('crear_venta')).content.decode()

        def etiqueta(identificador):
            inicio = html.rindex('<input', 0, html.index(f'id="{identificador}"'))
            return html[inicio:html.index('>', inicio)]

        self.assertIn('min="0"', etiqueta('inputEnvio'))
        self.assertIn('min="0"', etiqueta('inputOtrosGastos'))
        self.assertIn('min="0"', etiqueta('inputDescuento'))
        self.assertIn('max="100"', etiqueta('inputDescuento'))


class GastosEditarVentaTests(GastosVentaBase):
    """S3 en editar_venta: un dato inválido deja la venta exactamente como estaba."""

    def setUp(self):
        super().setUp()
        self.venta = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, descuento=Decimal('5.00'),
            envio=Decimal('2.00'), otros_gastos=Decimal('1.00'), notas='original',
        )
        DetalleVenta.objects.create(venta=self.venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        self.venta.calcular_total()
        self.url = reverse('editar_venta', args=[self.venta.id])

    def datos_edicion(self, **extra):
        datos = {
            'descuento': '5.00', 'envio': '2.00', 'otros_gastos': '1.00',
            'descripcion_otros': 'Embalaje', 'notas': 'cambiada', 'metodo_pago': 'tarjeta',
        }
        datos.update(extra)
        return datos

    def assertVentaIntacta(self):
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.descuento, Decimal('5.00'))
        self.assertEqual(self.venta.envio, Decimal('2.00'))
        self.assertEqual(self.venta.otros_gastos, Decimal('1.00'))
        # T3: base 100 - 5 = 95; IVA 15 % = 14.25; + envío 2 + otros 1 (sin IVA).
        self.assertEqual(self.venta.total, Decimal('112.25'))
        self.assertEqual(self.venta.notas, 'original')
        self.assertEqual(self.venta.metodo_pago, 'efectivo')
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 3)

    def test_valores_invalidos_dejan_la_venta_sin_cambios(self):
        for campo in self.CAMPOS:
            for valor, mensaje in self.casos_invalidos(campo).items():
                with self.subTest(campo=campo, valor=valor):
                    response = self.client.post(self.url, self.datos_edicion(**{campo: valor}))
                    self.assertEqual(response.status_code, 302)
                    self.assertEqual(response.url, self.url)
                    self.assertIn(mensaje, mensajes(response))
                    self.assertVentaIntacta()

    def test_descuento_mayor_al_subtotal_se_rechaza(self):
        response = self.client.post(self.url, self.datos_edicion(descuento='100.01'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.url)
        self.assertIn('El descuento no puede ser mayor al subtotal ($100.00).', mensajes(response))
        self.assertVentaIntacta()

    def test_descuento_igual_al_subtotal_se_acepta(self):
        response = self.client.post(self.url, self.datos_edicion(descuento='100'))
        self.assertRedirects(response, reverse('detalle_venta', args=[self.venta.id]))
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.descuento, Decimal('100.00'))

    def test_valores_validos_se_guardan_y_recalculan_el_total(self):
        response = self.client.post(
            self.url, self.datos_edicion(descuento='10', envio='3.5', otros_gastos='0.25'),
        )
        self.assertRedirects(response, reverse('detalle_venta', args=[self.venta.id]))
        self.venta.refresh_from_db()
        self.assertEqual(self.venta.descuento, Decimal('10.00'))
        self.assertEqual(self.venta.envio, Decimal('3.50'))
        self.assertEqual(self.venta.otros_gastos, Decimal('0.25'))
        self.assertEqual(self.venta.notas, 'cambiada')
        self.assertEqual(self.venta.metodo_pago, 'tarjeta')
        # T3: base 100 - 10 = 90; IVA 15 % = 13.50; + envío 3.50 + otros 0.25 (sin IVA).
        self.assertEqual(self.venta.total, Decimal('107.25'))

    def test_valores_vacios_cuentan_como_cero(self):
        response = self.client.post(self.url, self.datos_edicion(descuento='', envio='', otros_gastos=''))
        self.assertRedirects(response, reverse('detalle_venta', args=[self.venta.id]))
        self.venta.refresh_from_db()
        self.assertEqual((self.venta.descuento, self.venta.envio, self.venta.otros_gastos), (0, 0, 0))


class CalculoFacturaTests(GastosVentaBase):
    """S1/S4: el IVA se calcula sobre subtotal - descuento, con redondeo HALF_UP y % guardado en la venta."""

    def venta(self, precio, porcentaje=None, **campos):
        if porcentaje is not None:
            ConfiguracionFactura.objects.update_or_create(
                empresa=self.empresa, defaults={'porcentaje_iva': Decimal(porcentaje)},
            )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente, **campos)
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal(precio))
        venta.calcular_total()
        venta.refresh_from_db()
        return venta

    def test_iva_se_suma_al_subtotal_sin_descuento(self):
        venta = self.venta('100.00', '15.00')
        self.assertEqual(venta.subtotal, Decimal('100.00'))
        self.assertEqual(venta.iva, Decimal('15.00'))
        self.assertEqual(venta.total, Decimal('115.00'))
        self.assertEqual(venta.porcentaje_iva, Decimal('15.00'))

    def test_iva_se_calcula_despues_del_descuento(self):
        venta = self.venta('100.00', '15.00', descuento=Decimal('10.00'))
        self.assertEqual(venta.subtotal, Decimal('100.00'))
        self.assertEqual(venta.iva, Decimal('13.50'))
        self.assertEqual(venta.total, Decimal('103.50'))

    def test_envio_y_otros_gastos_se_suman_sin_iva(self):
        venta = self.venta(
            '100.00', '15.00', descuento=Decimal('10.00'),
            envio=Decimal('5.00'), otros_gastos=Decimal('2.00'),
        )
        self.assertEqual(venta.iva, Decimal('13.50'))
        self.assertEqual(venta.total, Decimal('110.50'))

    def test_redondeo_half_up_a_centavos(self):
        venta = self.venta('0.30', '15.00')
        self.assertEqual(venta.iva, Decimal('0.05'))  # 0.045 sube a 0.05
        self.assertEqual(venta.total, Decimal('0.35'))

    def test_porcentaje_cero_no_agrega_iva(self):
        venta = self.venta('100.00', '0.00')
        self.assertEqual(venta.iva, Decimal('0.00'))
        self.assertEqual(venta.total, Decimal('100.00'))
        self.assertEqual(venta.porcentaje_iva, Decimal('0.00'))

    def test_descuento_igual_al_subtotal_deja_solo_los_gastos_sin_iva(self):
        venta = self.venta('100.00', '15.00', descuento=Decimal('100.00'), envio=Decimal('3.00'))
        self.assertEqual(venta.iva, Decimal('0.00'))
        self.assertEqual(venta.total, Decimal('3.00'))

    def test_descuento_mayor_al_subtotal_nunca_da_base_negativa(self):
        venta = self.venta('100.00', '15.00', descuento=Decimal('150.00'))
        self.assertEqual(venta.iva, Decimal('0.00'))
        self.assertEqual(venta.total, Decimal('0.00'))

    def test_el_porcentaje_queda_guardado_al_crear_la_venta(self):
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('15.00')},
        )
        response = self.client.post(reverse('crear_venta'), self.datos(descuento='10'))
        self.assertEqual(response.status_code, 302)
        venta = Venta.objects.get(empresa=self.empresa)
        self.assertEqual(venta.porcentaje_iva, Decimal('15.00'))
        self.assertEqual((venta.subtotal, venta.iva, venta.total), (Decimal('100.00'), Decimal('13.50'), Decimal('103.50')))

    def test_cambiar_la_configuracion_no_recalcula_una_venta_al_editarla(self):
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('15.00')},
        )
        self.client.post(reverse('crear_venta'), self.datos())
        venta = Venta.objects.get(empresa=self.empresa)
        ConfiguracionFactura.objects.filter(empresa=self.empresa).update(porcentaje_iva=Decimal('12.00'))

        response = self.client.post(reverse('editar_venta', args=[venta.id]), {
            'descuento': '0', 'envio': '0', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': 'sin cambios', 'metodo_pago': 'efectivo',
        })

        self.assertRedirects(response, reverse('detalle_venta', args=[venta.id]))
        venta.refresh_from_db()
        self.assertEqual(venta.porcentaje_iva, Decimal('15.00'))
        self.assertEqual(venta.iva, Decimal('15.00'))
        self.assertEqual(venta.total, Decimal('115.00'))

    def test_venta_antigua_sin_porcentaje_toma_el_de_la_configuracion_y_lo_guarda(self):
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('12.00')},
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        self.assertIsNone(venta.porcentaje_iva)

        venta.calcular_total()

        venta.refresh_from_db()
        self.assertEqual(venta.porcentaje_iva, Decimal('12.00'))
        self.assertEqual((venta.iva, venta.total), (Decimal('12.00'), Decimal('112.00')))


class MigracionPorcentajeIvaTests(GastosVentaBase):
    """La migración 0010 asigna el % actual de cada empresa sin tocar los importes históricos."""

    def test_ventas_existentes_reciben_el_porcentaje_de_su_empresa_sin_cambiar_importes(self):
        migracion = importlib.import_module('ventas.migrations.0010_venta_porcentaje_iva')
        otra_empresa, _ = crear_empresa_con_dueno('sin-config')
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('12.00')},
        )
        ConfiguracionFactura.objects.filter(empresa=otra_empresa).delete()

        # Importes "históricos" calculados con la regla vieja (IVA sobre el subtotal, antes del descuento).
        historicos = dict(
            subtotal=Decimal('100.00'), iva=Decimal('15.00'), descuento=Decimal('10.00'),
            envio=Decimal('2.00'), otros_gastos=Decimal('1.00'), total=Decimal('108.00'),
        )
        con_config = Venta.objects.create(empresa=self.empresa, cliente=self.cliente, **historicos)
        sin_config = Venta.objects.create(empresa=otra_empresa, cliente=self.cliente, **historicos)
        Venta.objects.filter(pk__in=[con_config.pk, sin_config.pk]).update(porcentaje_iva=None)

        migracion.asignar_porcentaje_iva(django_apps, None)

        for venta, esperado in ((con_config, Decimal('12.00')), (sin_config, Decimal('15.00'))):
            venta.refresh_from_db()
            self.assertEqual(venta.porcentaje_iva, esperado)
            for campo, valor in historicos.items():
                self.assertEqual(getattr(venta, campo), valor, campo)

    def test_ventas_antiguas_de_sheets_quedan_sin_iva_y_editarlas_no_lo_agrega(self):
        migracion = importlib.import_module('ventas.migrations.0010_venta_porcentaje_iva')
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('15.00')},
        )
        venta = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, origen='sheets',
            subtotal=Decimal('100.00'), iva=Decimal('0.00'), total=Decimal('100.00'),
        )
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        Venta.objects.filter(pk=venta.pk).update(porcentaje_iva=None)

        migracion.asignar_porcentaje_iva(django_apps, None)

        venta.refresh_from_db()
        self.assertEqual(venta.porcentaje_iva, Decimal('0'))
        venta.calcular_total()
        venta.refresh_from_db()
        self.assertEqual(venta.iva, Decimal('0.00'))
        self.assertEqual(venta.total, Decimal('100.00'))

    def test_la_migracion_no_pisa_un_porcentaje_ya_guardado(self):
        migracion = importlib.import_module('ventas.migrations.0010_venta_porcentaje_iva')
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('12.00')},
        )
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente, porcentaje_iva=Decimal('8.00'))
        migracion.asignar_porcentaje_iva(django_apps, None)
        venta.refresh_from_db()
        self.assertEqual(venta.porcentaje_iva, Decimal('8.00'))


class IntegridadVentaTests(GastosVentaBase):
    """S5: la venta se guarda completa o no se guarda, y un envío repetido no la duplica."""

    def setUp(self):
        super().setUp()
        self.token = str(uuid.uuid4())

    def estado(self):
        self.producto.refresh_from_db()
        return {
            'ventas': Venta.objects.count(),
            'detalles': DetalleVenta.objects.count(),
            'clientes': Cliente.objects.count(),
            'stock': self.producto.stock,
            'estado': self.producto.estado,
        }

    def assertSinCambios(self, antes):
        self.assertEqual(self.estado(), antes)

    def test_mismo_token_dos_veces_crea_una_sola_venta_y_descuenta_stock_una_vez(self):
        primera = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        venta = Venta.objects.get()
        self.assertEqual(primera.status_code, 302)
        self.assertEqual(primera.url, url_detalle_nueva(venta.id))
        self.assertEqual(venta.token_envio, uuid.UUID(self.token))
        self.client.get(primera.url)  # el usuario ve el detalle y se consume el mensaje de creación

        segunda = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(segunda.url, reverse('detalle_venta', args=[venta.id]))
        self.assertEqual(mensajes(segunda), ['Esta venta ya se registró.'])
        self.assertEqual(Venta.objects.count(), 1)
        self.assertEqual(DetalleVenta.objects.count(), 1)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 2)

    def test_token_repetido_ni_siquiera_valida_el_resto_del_envio(self):
        primera = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        self.client.get(primera.url)
        antes = self.estado()
        repetido = self.client.post(
            reverse('crear_venta'), self.datos(token_envio=self.token, descuento='-5', unidades=9),
        )
        self.assertEqual(repetido.url, reverse('detalle_venta', args=[Venta.objects.get().id]))
        self.assertEqual(mensajes(repetido), ['Esta venta ya se registró.'])
        self.assertSinCambios(antes)

    def test_token_usado_por_otra_empresa_no_bloquea_esta_empresa(self):
        otra, _ = crear_empresa_con_dueno('otra-tienda')
        ajena = Venta.objects.create(
            empresa=otra, cliente=self.cliente, token_envio=uuid.UUID(self.token),
        )
        response = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        propia = Venta.objects.get(empresa=self.empresa)
        self.assertEqual(response.url, reverse('detalle_venta', args=[propia.id]) + '?nueva=1')
        self.assertNotEqual(propia.id, ajena.id)
        self.assertEqual(propia.token_envio, uuid.UUID(self.token))
        self.assertNotIn('Esta venta ya se registró.', mensajes(response))
        self.assertEqual(Venta.objects.count(), 2)

    def test_sin_token_o_con_token_invalido_crea_la_venta_y_deja_una_advertencia(self):
        casos = {'sin token': {}, 'vacío': {'token_envio': ''}, 'texto': {'token_envio': 'no-es-uuid'}}
        for nombre, extra in casos.items():
            with self.subTest(caso=nombre):
                Venta.objects.all().delete()
                Producto.objects.filter(pk=self.producto.pk).update(stock=3, estado='disponible')
                with self.assertLogs('ventas.views', level='WARNING') as registro:
                    response = self.client.post(reverse('crear_venta'), self.datos(**extra))
                venta = Venta.objects.get()
                self.assertEqual(response.url, reverse('detalle_venta', args=[venta.id]) + '?nueva=1')
                self.assertIsNone(venta.token_envio)
                self.assertTrue(any('token_envio' in linea for linea in registro.output))
                self.producto.refresh_from_db()
                self.assertEqual(self.producto.stock, 2)

    def test_la_base_impide_dos_ventas_con_el_mismo_token_en_una_empresa_pero_no_con_nulos(self):
        token = uuid.UUID(self.token)
        Venta.objects.create(empresa=self.empresa, cliente=self.cliente, token_envio=token)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Venta.objects.create(empresa=self.empresa, cliente=self.cliente, token_envio=token)
        Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        self.assertEqual(Venta.objects.count(), 3)

    def test_carrera_entre_dos_envios_con_el_mismo_token_redirige_a_la_venta_existente(self):
        existente = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, token_envio=uuid.UUID(self.token),
        )
        antes = self.estado()
        # La primera consulta no la ve (el otro envío aún no había confirmado); la base sí la rechaza.
        with mock.patch('ventas.views._venta_con_token', side_effect=[None, existente]):
            response = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('detalle_venta', args=[existente.id]))
        self.assertEqual(mensajes(response), ['Esta venta ya se registró.'])
        self.assertSinCambios(antes)

    def test_stock_insuficiente_no_deja_venta_detalle_cliente_nuevo_ni_cambio_de_stock(self):
        antes = self.estado()
        response = self.client.post(
            reverse('crear_venta'), self.datos(unidades=4, cliente_id='Cliente Nuevo SA', token_envio=self.token),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertEqual(
            mensajes(response),
            ['No puedes vender 4 unidades de "Camisa" porque solo quedan 3 en stock.'],
        )
        self.assertFalse(Cliente.objects.filter(nombre='Cliente Nuevo SA').exists())
        self.assertSinCambios(antes)

    def test_producto_ya_vendido_no_deja_cliente_nuevo_ni_venta(self):
        Producto.objects.filter(pk=self.producto.pk).update(estado='vendido', stock=0)
        antes = self.estado()
        response = self.client.post(
            reverse('crear_venta'), self.datos(cliente_id='Otro Cliente Nuevo'),
        )
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertEqual(mensajes(response), ['El producto "Camisa" ya no está disponible.'])
        self.assertFalse(Cliente.objects.filter(nombre='Otro Cliente Nuevo').exists())
        self.assertSinCambios(antes)

    def test_si_falla_algo_despues_de_crear_la_venta_no_queda_nada_escrito(self):
        antes = self.estado()
        with mock.patch.object(Venta, 'calcular_total', side_effect=RuntimeError('falla simulada')):
            with self.assertRaises(RuntimeError):
                self.client.post(
                    reverse('crear_venta'),
                    self.datos(unidades=2, cliente_id='Cliente Fallido', token_envio=self.token),
                )
        self.assertFalse(Cliente.objects.filter(nombre='Cliente Fallido').exists())
        self.assertSinCambios(antes)
        # Como no quedó nada, reintentar con el mismo token funciona.
        response = self.client.post(reverse('crear_venta'), self.datos(token_envio=self.token))
        self.assertEqual(response.url, url_detalle_nueva(Venta.objects.get().id))

    def test_la_pantalla_trae_un_token_nuevo_en_cada_carga(self):
        patron = re.compile(r'<input type="hidden" name="token_envio" value="([^"]+)"')
        tokens = []
        for _ in range(2):
            response = self.client.get(reverse('crear_venta'))
            self.assertEqual(response.status_code, 200)
            encontrados = patron.findall(response.content.decode())
            self.assertEqual(len(encontrados), 1)
            tokens.append(uuid.UUID(encontrados[0]))
        self.assertNotEqual(tokens[0], tokens[1])

    def test_el_boton_se_bloquea_al_enviar(self):
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn('Guardando…', html)

    def test_la_edicion_no_lleva_token(self):
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        self.assertNotIn('name="token_envio"', html)


class TotalMaximoVentaTests(GastosVentaBase):
    """R3: el total no puede superar lo que cabe en DecimalField(10, 2)."""

    MENSAJE = 'El total de la venta no puede superar $99,999,999.99.'

    def setUp(self):
        super().setUp()
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('15.00')},
        )

    def precio(self, valor):
        Producto.objects.filter(pk=self.producto.pk).update(precio=Decimal(valor), stock=5)

    def assertNadaCambio(self):
        self.assertEqual(Venta.objects.count(), 0)
        self.assertEqual(DetalleVenta.objects.count(), 0)
        self.producto.refresh_from_db()
        self.assertEqual(self.producto.stock, 5)
        self.assertEqual(self.producto.estado, 'disponible')

    def test_total_con_iva_que_no_cabe_se_rechaza_sin_error_500(self):
        self.precio('90000000.00')
        response = self.client.post(reverse('crear_venta'), self.datos())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertEqual(mensajes(response), [self.MENSAJE])
        self.assertNadaCambio()

    def test_subtotal_de_varias_unidades_que_no_cabe_se_rechaza(self):
        self.precio('60000000.00')
        response = self.client.post(reverse('crear_venta'), self.datos(unidades=2))
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertEqual(mensajes(response), [self.MENSAJE])
        self.assertNadaCambio()

    def test_envio_que_empuja_el_total_sobre_el_maximo_se_rechaza(self):
        self.precio('90000000.00')
        ConfiguracionFactura.objects.filter(empresa=self.empresa).update(porcentaje_iva=Decimal('0'))
        response = self.client.post(reverse('crear_venta'), self.datos(envio='10000000'))
        self.assertEqual(response.url, reverse('crear_venta'))
        self.assertEqual(mensajes(response), [self.MENSAJE])
        self.assertNadaCambio()

    def test_total_exactamente_en_el_maximo_se_acepta(self):
        self.precio('99999999.99')
        ConfiguracionFactura.objects.filter(empresa=self.empresa).update(porcentaje_iva=Decimal('0'))
        response = self.client.post(reverse('crear_venta'), self.datos())
        venta = Venta.objects.get()
        self.assertEqual(response.url, url_detalle_nueva(venta.id))
        self.assertEqual(venta.total, Decimal('99999999.99'))

    def venta_grande(self):
        venta = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, porcentaje_iva=Decimal('0'),
        )
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal('90000000.00'))
        venta.calcular_total()
        venta.refresh_from_db()
        return venta

    def test_editar_con_total_que_no_cabe_se_rechaza_y_la_venta_queda_igual(self):
        venta = self.venta_grande()
        response = self.client.post(reverse('editar_venta', args=[venta.id]), {
            'descuento': '0', 'envio': '20000000', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': 'cambio', 'metodo_pago': 'efectivo',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('editar_venta', args=[venta.id]))
        self.assertEqual(mensajes(response), [self.MENSAJE])
        despues = Venta.objects.get(pk=venta.pk)
        self.assertEqual((despues.envio, despues.total, despues.notas), (venta.envio, venta.total, venta.notas))

    def test_editar_revierte_todo_si_falla_despues_de_guardar_algo(self):
        venta = self.venta_grande()

        def guarda_y_falla(self_venta):
            self_venta.save()
            raise RuntimeError('falla simulada')

        with mock.patch.object(Venta, 'calcular_total', autospec=True, side_effect=guarda_y_falla):
            with self.assertRaises(RuntimeError):
                self.client.post(reverse('editar_venta', args=[venta.id]), {
                    'descuento': '0', 'envio': '5', 'otros_gastos': '0',
                    'descripcion_otros': '', 'notas': 'cambio', 'metodo_pago': 'efectivo',
                })
        despues = Venta.objects.get(pk=venta.pk)
        self.assertEqual((despues.envio, despues.total, despues.notas), (venta.envio, venta.total, venta.notas))


class _FormularioRenderizado(HTMLParser):
    """Lee los campos del formulario de la pantalla como los vería el navegador."""

    def __init__(self):
        super().__init__()
        self.campos = {}
        self.por_id = {}
        self.productos = []
        self._textarea = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'input':
            if attrs.get('id'):
                self.por_id[attrs['id']] = attrs
            nombre = attrs.get('name')
            if nombre == 'productos':
                self.productos.append(attrs.get('value', ''))
            elif nombre:
                self.campos[nombre] = attrs.get('value', '')
        elif tag == 'textarea' and attrs.get('name'):
            self._textarea = attrs['name']
            self.campos[self._textarea] = ''

    def handle_data(self, data):
        if self._textarea:
            self.campos[self._textarea] += data

    def handle_endtag(self, tag):
        if tag == 'textarea':
            self._textarea = None


def _centavos_half_up(valor):
    return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


class IvaPantallaYEdicionTests(GastosVentaBase):
    """S6/S4: el % de IVA correcto llega a la pantalla y editar sin tocar nada no cambia la venta."""

    def venta_con(self, precio, descuento, envio='0', otros='0'):
        venta = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, descuento=Decimal(descuento),
            envio=Decimal(envio), otros_gastos=Decimal(otros),
        )
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal(precio))
        venta.calcular_total()
        venta.save()
        return venta

    def configurar_iva(self, porcentaje):
        config = ConfiguracionFactura.obtener_configuracion(self.empresa.id)
        config.porcentaje_iva = Decimal(porcentaje)
        config.save()

    def lo_que_enviaria_el_navegador(self, html, subtotal):
        """Reproduce el envío del formulario, incluido el cálculo del descuento que hace el JS al cargar."""
        formulario = _FormularioRenderizado()
        formulario.feed(html)
        visible = formulario.por_id['inputDescuento']
        valor = Decimal(visible.get('value') or '0')
        if visible.get('data-modo') == 'dinero':
            descuento = _centavos_half_up(valor)
        else:  # modo antiguo: el input es un porcentaje y el JS lo convierte a dinero
            descuento = _centavos_half_up(Decimal(subtotal) * valor / 100)
        datos = {nombre: valor for nombre, valor in formulario.campos.items()}
        datos['descuento'] = str(descuento)
        datos['productos'] = formulario.productos
        return datos

    # -- % de IVA en la pantalla --------------------------------------------------

    def test_crear_venta_usa_el_iva_de_la_configuracion(self):
        self.configurar_iva('12.00')
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn("const ivaPorcentaje = Number('12.00')", html)
        self.assertRegex(html, r'id="ivaPorcentajeEtiqueta">12\.00<')

    def test_editar_venta_usa_el_iva_guardado_aunque_la_configuracion_cambie(self):
        venta = self.venta_con('100.00', '0')
        self.assertEqual(venta.porcentaje_iva, Decimal('15.00'))
        self.configurar_iva('12.00')
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        self.assertIn("const ivaPorcentaje = Number('15.00')", html)
        self.assertRegex(html, r'id="ivaPorcentajeEtiqueta">15\.00<')
        self.assertNotIn("Number('12.00')", html)

    def test_editar_venta_sin_iva_guardado_usa_la_configuracion(self):
        venta = self.venta_con('100.00', '0')
        Venta.objects.filter(pk=venta.pk).update(porcentaje_iva=None)
        self.configurar_iva('12.00')
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        self.assertIn("const ivaPorcentaje = Number('12.00')", html)

    # -- editar sin tocar nada ----------------------------------------------------

    def test_abrir_y_guardar_sin_tocar_nada_no_cambia_descuento_iva_ni_total(self):
        casos = [
            ('30.00', '7.00'),     # 23,33 % del subtotal: no es un porcentaje redondo
            ('100.00', '33.33'),
            ('30.00', '0.01'),
            ('45.50', '12.34'),
            ('100.00', '15.00'),   # 15 % exacto
            ('100.00', '0.00'),
        ]
        for precio, descuento in casos:
            with self.subTest(precio=precio, descuento=descuento):
                venta = self.venta_con(precio, descuento, envio='2.50', otros='1.25')
                antes = Venta.objects.get(pk=venta.pk)
                url = reverse('editar_venta', args=[venta.id])
                html = self.client.get(url).content.decode()
                datos = self.lo_que_enviaria_el_navegador(html, precio)
                self.assertEqual(datos['descuento'], str(antes.descuento))
                response = self.client.post(url, datos)
                self.assertRedirects(response, reverse('detalle_venta', args=[venta.id]))
                despues = Venta.objects.get(pk=venta.pk)
                self.assertEqual(
                    (despues.descuento, despues.iva, despues.total, despues.envio, despues.otros_gastos, despues.porcentaje_iva),
                    (antes.descuento, antes.iva, antes.total, antes.envio, antes.otros_gastos, antes.porcentaje_iva),
                )

    def test_editar_muestra_el_descuento_guardado_en_dinero(self):
        venta = self.venta_con('30.00', '7.00')
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        formulario = _FormularioRenderizado()
        formulario.feed(html)
        visible = formulario.por_id['inputDescuento']
        self.assertEqual(visible['data-modo'], 'dinero')
        self.assertEqual(visible['value'], '7.00')
        self.assertEqual(formulario.campos['descuento'], '7.00')

    def test_crear_venta_sigue_pidiendo_el_descuento_en_porcentaje(self):
        formulario = _FormularioRenderizado()
        formulario.feed(self.client.get(reverse('crear_venta')).content.decode())
        self.assertEqual(formulario.por_id['inputDescuento'].get('data-modo'), 'porcentaje')


class IvaEnDocumentosTests(GastosVentaBase):
    """S6: el detalle y la factura impresa muestran la línea de IVA guardada, en el orden del cálculo."""

    def setUp(self):
        super().setUp()
        self.venta = Venta.objects.create(
            empresa=self.empresa, cliente=self.cliente, descuento=Decimal('5.00'),
            envio=Decimal('2.00'), otros_gastos=Decimal('1.00'), descripcion_otros='',
        )
        DetalleVenta.objects.create(venta=self.venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        self.venta.calcular_total()
        self.venta.save()
        self.assertEqual((self.venta.iva, self.venta.total), (Decimal('14.25'), Decimal('112.25')))

    def assertOrden(self, html, marcas):
        posicion = 0
        for marca in marcas:
            indice = html.find(marca, posicion)
            self.assertNotEqual(indice, -1, f'{marca!r} no aparece después de la marca anterior')
            posicion = indice + len(marca)

    def test_detalle_muestra_iva_con_porcentaje_y_monto_guardados(self):
        html = self.client.get(reverse('detalle_venta', args=[self.venta.id])).content.decode()
        self.assertIn('IVA (15%)', html)
        self.assertOrden(html, ['Subtotal (', 'Descuento:', 'IVA (15%)', '14.25', 'Envío:', 'Otros gastos', 'Total Pagado', '112.25'])

    def test_factura_html_muestra_iva_con_porcentaje_y_monto_guardados(self):
        response = self.client.get(reverse('factura_pdf', args=[self.venta.id]) + '?html=1')
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('IVA (15%)', html)
        self.assertOrden(html, ['Subtotal:', 'Descuento:', 'IVA (15%)', '14.25', 'Envío:', 'Otros gastos', 'TOTAL FINAL:', '112.25'])

    def test_el_iva_mostrado_es_el_guardado_no_el_de_la_configuracion_actual(self):
        config = ConfiguracionFactura.obtener_configuracion(self.empresa.id)
        config.porcentaje_iva = Decimal('12.00')
        config.save()
        for html in (
            self.client.get(reverse('detalle_venta', args=[self.venta.id])).content.decode(),
            self.client.get(reverse('factura_pdf', args=[self.venta.id]) + '?html=1').content.decode(),
        ):
            self.assertIn('IVA (15%)', html)
            self.assertNotIn('IVA (12%)', html)

    def test_porcentaje_decimal_se_muestra_sin_ceros_de_mas(self):
        Venta.objects.filter(pk=self.venta.pk).update(porcentaje_iva=Decimal('12.50'))
        html = self.client.get(reverse('detalle_venta', args=[self.venta.id])).content.decode()
        self.assertIn('IVA (12.50%)', html)

    def test_sin_porcentaje_guardado_muestra_el_monto_sin_texto_de_porcentaje(self):
        Venta.objects.filter(pk=self.venta.pk).update(porcentaje_iva=None)
        for html in (
            self.client.get(reverse('detalle_venta', args=[self.venta.id])).content.decode(),
            self.client.get(reverse('factura_pdf', args=[self.venta.id]) + '?html=1').content.decode(),
        ):
            self.assertIn('IVA', html)
            self.assertIn('14.25', html)
            self.assertNotIn('IVA (', html)

    def test_iva_cero_se_muestra_como_linea(self):
        Venta.objects.filter(pk=self.venta.pk).update(porcentaje_iva=Decimal('0.00'), iva=Decimal('0.00'))
        html = self.client.get(reverse('factura_pdf', args=[self.venta.id]) + '?html=1').content.decode()
        self.assertIn('IVA (0%)', html)

    def test_la_factura_sigue_generando_pdf(self):
        response = self.client.get(reverse('factura_pdf', args=[self.venta.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn(f'factura-{self.venta.numero_factura}.pdf', response['Content-Disposition'])

    def test_el_detalle_conserva_sus_botones_de_impresion(self):
        html = self.client.get(reverse('detalle_venta', args=[self.venta.id])).content.decode()
        self.assertIn(reverse('factura_pdf', args=[self.venta.id]), html)
        self.assertIn(reverse('editar_venta', args=[self.venta.id]), html)



class DatosDeClienteSinXssTests(TestCase):
    """Un nombre de cliente con HTML no puede ejecutar código en la pantalla de venta."""

    NOMBRE_MALICIOSO = '</script><script>alert(1)</script>'

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('panaderia-xss')
        cliente = Cliente.objects.create(nombre=self.NOMBRE_MALICIOSO, ruc_cedula='0911111111')
        cliente.empresas.add(self.empresa)
        self.client.force_login(self.dueno)

    def test_el_nombre_no_cierra_el_bloque_de_datos_json(self):
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.NOMBRE_MALICIOSO)
        self.assertNotContains(respuesta, '<script>alert(1)')

    def test_los_datos_llegan_completos_al_navegador(self):
        respuesta = self.client.get(reverse('crear_venta'))
        html = respuesta.content.decode()
        inicio = html.index('id="clientes-data"')
        bloque = html[html.index('>', inicio) + 1:html.index('</script>', inicio)]
        clientes = json.loads(bloque)
        self.assertIn(self.NOMBRE_MALICIOSO, [c['nombre'] for c in clientes])


class ApiBuscarProductosTests(TestCase):
    """S7/S8: la búsqueda de productos de la venta rápida es del servidor, por empresa y sin costos."""

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('api-panaderia')
        self.otra, _ = crear_empresa_con_dueno('api-cafeteria')
        self.tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Camisetas')
        self.client.force_login(self.dueno)
        self.url = reverse('api_buscar_productos')

    def producto(self, nombre, empresa=None, **extra):
        datos = {'precio': Decimal('10.00'), 'stock': 5, 'estado': 'disponible'}
        datos.update(extra)
        return Producto.objects.create(empresa=empresa or self.empresa, nombre=nombre, **datos)

    def buscar(self, q=None):
        respuesta = self.client.get(self.url, {} if q is None else {'q': q})
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.json()

    def test_la_ruta_es_ventas_api_productos(self):
        self.assertEqual(self.url, '/ventas/api/productos/')

    def test_devuelve_id_nombre_precio_con_dos_decimales_stock_y_categoria(self):
        p = self.producto('Camisón de seda', precio=Decimal('12.5'), stock=4, categoria='Mujer')
        self.assertEqual(self.buscar('seda'), [{
            'id': p.id, 'nombre': 'Camisón de seda', 'precio': '12.50', 'stock': 4, 'categoria': 'Mujer',
        }])

    def test_nunca_devuelve_productos_de_otra_empresa(self):
        propio = self.producto('Pan de yuca')
        self.producto('Pan de yuca ajeno', empresa=self.otra)
        self.assertEqual([r['id'] for r in self.buscar('pan')], [propio.id])
        self.assertEqual([r['id'] for r in self.buscar('')], [propio.id])

    def test_excluye_agotados_y_no_disponibles(self):
        visible = self.producto('Gorra azul')
        self.producto('Gorra agotada', stock=0)
        self.producto('Gorra vendida', estado='vendido')
        self.producto('Gorra reservada', estado='reservado')
        self.assertEqual([r['id'] for r in self.buscar('gorra')], [visible.id])

    def test_devuelve_como_maximo_20(self):
        for i in range(25):
            self.producto(f'Taza {i}')
        self.assertEqual(len(self.buscar('taza')), 20)
        self.assertEqual(len(self.buscar()), 20)

    def test_sin_texto_devuelve_los_mas_recientes_primero(self):
        ids = [self.producto(f'Item {i}').id for i in range(3)]
        self.assertEqual([r['id'] for r in self.buscar('')], ids[::-1])
        self.assertEqual([r['id'] for r in self.buscar('   ')], ids[::-1])

    def test_busca_sin_importar_mayusculas_ni_acentos(self):
        p = self.producto('Camisón de Seda')
        self.assertEqual([r['id'] for r in self.buscar('CAMISON')], [p.id])
        self.assertEqual([r['id'] for r in self.buscar('camisón')], [p.id])

    def test_busca_por_tipo_de_producto_y_por_varias_palabras(self):
        p = self.producto('Polo rojo', tipo_producto=self.tipo)
        self.producto('Polo verde')
        self.assertEqual([r['id'] for r in self.buscar('camisetas')], [p.id])
        self.assertEqual([r['id'] for r in self.buscar('polo rojo')], [p.id])
        self.assertEqual(self.buscar('rojo verde'), [])

    def test_los_comodines_de_like_se_buscan_como_texto(self):
        self.producto('Oferta 50% hoy')
        self.assertEqual(len(self.buscar('%')), 1)
        self.assertEqual(self.buscar('zzz%'), [])

    def test_no_incluye_el_precio_de_costo_ni_otros_campos(self):
        self.producto('Bolso', precio_costo=Decimal('3.21'), precio_real=Decimal('4.56'))
        respuesta = self.client.get(self.url, {'q': 'bolso'})
        self.assertNotContains(respuesta, '3.21')
        self.assertNotContains(respuesta, '4.56')
        self.assertNotContains(respuesta, 'costo')
        self.assertEqual(set(respuesta.json()[0]), {'id', 'nombre', 'precio', 'stock', 'categoria'})

    def test_un_anonimo_es_enviado_al_login(self):
        self.client.logout()
        respuesta = self.client.get(self.url, {'q': 'a'})
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('login', respuesta.url)

    def test_solo_acepta_get(self):
        self.assertEqual(self.client.post(self.url, {'q': 'a'}).status_code, 405)


class PantallaVentaRapidaTests(GastosVentaBase):
    """S7/S8: la pantalla arranca con pocos productos, enfoca el buscador y consulta la API."""

    def crear_productos(self, cantidad):
        return [
            Producto.objects.create(
                empresa=self.empresa, nombre=f'Lote {i:02d}', precio=Decimal('1.00'),
                stock=2, estado='disponible',
            )
            for i in range(cantidad)
        ]

    def pagina(self):
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.content.decode()

    def test_la_lista_inicial_trae_solo_los_24_mas_recientes(self):
        lotes = self.crear_productos(30)
        html = self.pagina()
        ids = [int(i) for i in re.findall(r'class="card producto-seleccionable"\s+data-producto-id="(\d+)"', html)]
        self.assertEqual(len(ids), 24)
        self.assertEqual(set(ids), {p.id for p in lotes[6:]})
        self.assertNotIn(self.producto.id, ids)

    def test_la_lista_inicial_no_ofrece_productos_agotados(self):
        Producto.objects.filter(pk=self.producto.pk).update(stock=0)
        self.assertNotIn(f'data-producto-id="{self.producto.id}"', self.pagina())

    def test_el_buscador_tiene_foco_y_consulta_la_api(self):
        html = self.pagina()
        buscador = re.search(r'<input[^>]*id="searchProductos"[^>]*>', html, re.S).group(0)
        self.assertIn('autofocus', buscador)
        self.assertIn(f'data-url-api="{reverse("api_buscar_productos")}"', html)

    def test_la_tabla_de_la_venta_tiene_columna_de_cantidad(self):
        self.assertIn('<th style="text-align: center;">Cantidad</th>', self.pagina())

    def test_cada_tarjeta_lleva_el_nombre_del_producto_para_la_tabla(self):
        self.assertIn(f'data-titulo="{self.producto.nombre}"', self.pagina())

    def test_la_pantalla_de_edicion_no_cambia_no_hay_buscador_ni_cantidades(self):
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        venta.calcular_total()
        html = self.client.get(reverse('editar_venta', args=[venta.id])).content.decode()
        self.assertNotIn('id="searchProductos"', html)
        self.assertNotIn('>Cantidad</th>', html)
        self.assertIn('producto-card-edicion', html)


class PanelPosteriorVentaTests(GastosVentaBase):
    """S7/S8: tras guardar, el detalle ofrece imprimir, descargar, compartir y nueva venta."""

    def guardar(self):
        self.client.post(reverse('crear_venta'), self.datos())
        return Venta.objects.get()

    def detalle(self, venta, consulta=''):
        return self.client.get(reverse('detalle_venta', args=[venta.id]) + consulta)

    def test_guardar_redirige_al_detalle_con_nueva_1_y_deja_el_mensaje_de_exito(self):
        response = self.client.post(reverse('crear_venta'), self.datos())
        venta = Venta.objects.get()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url_detalle_nueva(venta.id))
        self.assertEqual(mensajes(response), [f'Venta {venta.numero_factura} creada exitosamente'])

    def test_con_nueva_1_el_detalle_muestra_el_panel_con_numero_total_y_acciones(self):
        venta = self.guardar()
        html = self.detalle(venta, '?nueva=1').content.decode()
        self.assertIn('id="panel-nueva-venta"', html)
        self.assertIn(f'Venta N° {venta.numero_factura} guardada — ${venta.total:.2f}', html)
        panel = html[html.index('id="panel-nueva-venta"'):]
        self.assertIn(f'data-url-ticket="{reverse("factura_pdf", args=[venta.id])}?html=1"', panel)
        self.assertIn('Imprimir ticket', panel)
        self.assertIn(f'href="{reverse("factura_pdf", args=[venta.id])}"', panel)
        self.assertIn('Descargar PDF', panel)
        self.assertIn('compartirDocumento(', panel)
        self.assertIn('Imprimir al guardar', panel)
        nueva = re.search(r'<a[^>]*id="btn-nueva-venta"[^>]*>', panel).group(0)
        self.assertIn(f'href="{reverse("crear_venta")}"', nueva)
        self.assertIn('autofocus', nueva)

    def test_sin_nueva_1_el_detalle_no_muestra_el_panel_pero_conserva_sus_botones(self):
        venta = self.guardar()
        for consulta in ('', '?nueva=0', '?nueva=si'):
            with self.subTest(consulta=consulta):
                html = self.detalle(venta, consulta).content.decode()
                self.assertNotIn('panel-nueva-venta', html)
                self.assertNotIn('guardada —', html)
                for existente in ('Volver a Ventas', 'Ver Cliente', 'Editar Venta', 'Compartir', 'Imprimir Ticket', 'Descargar PDF'):
                    self.assertIn(existente, html)

    def test_el_detalle_con_nueva_1_conserva_los_botones_existentes(self):
        html = self.detalle(self.guardar(), '?nueva=1').content.decode()
        for existente in ('Volver a Ventas', 'Ver Cliente', 'Editar Venta', 'Imprimir Ticket'):
            self.assertIn(existente, html)

    def test_venta_de_otra_empresa_con_nueva_1_da_404(self):
        otra, _ = crear_empresa_con_dueno('panel-otra')
        cliente = Cliente.objects.create(nombre='Cliente Ajeno', ruc_cedula='0987654321')
        cliente.empresas.add(otra)
        ajena = Venta.objects.create(empresa=otra, cliente=cliente)
        respuesta = self.detalle(ajena, '?nueva=1')
        self.assertEqual(respuesta.status_code, 404)
        self.assertNotContains(respuesta, 'panel-nueva-venta', status_code=404)

    def test_factura_html_se_puede_incrustar_en_el_iframe_oculto_de_impresion(self):
        venta = self.guardar()
        respuesta = self.client.get(reverse('factura_pdf', args=[venta.id]), {'html': '1'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['X-Frame-Options'], 'SAMEORIGIN')

    def test_factura_pdf_sigue_devolviendo_el_pdf(self):
        venta = self.guardar()
        respuesta = self.client.get(reverse('factura_pdf', args=[venta.id]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Type'], 'application/pdf')
        self.assertIn(f'factura-{venta.numero_factura}.pdf', respuesta['Content-Disposition'])

    def test_el_resto_de_la_aplicacion_sigue_sin_poder_incrustarse(self):
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertEqual(respuesta['X-Frame-Options'], 'DENY')

    def test_la_api_sin_empresa_devuelve_lista_vacia(self):
        superusuario = get_user_model().objects.create_superuser('root-panel', 'root-panel@example.com', 'clave-segura-1')
        self.client.force_login(superusuario)
        respuesta = self.client.get(reverse('api_buscar_productos'), {'q': 'camisa'})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), [])


class LimpiezaPantallaVentaTests(GastosVentaBase):
    """T7 (3.7.0): ids de productos del cliente como JSON seguro y buscador sin promesas falsas."""

    def pagina(self, **parametros):
        respuesta = self.client.get(reverse('crear_venta'), parametros)
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.content.decode()

    def test_los_ids_de_productos_del_cliente_van_como_json_en_su_elemento(self):
        otro = Producto.objects.create(
            empresa=self.empresa, nombre='Falda', precio=Decimal('10.00'), stock=1,
            estado='disponible', vendido_a='Ana García',
        )
        Producto.objects.filter(pk=self.producto.pk).update(vendido_a='Ana García')
        html = self.pagina(cliente='Ana García')
        bloque = re.search(
            r'<script id="productos-cliente-ids" type="application/json">(.*?)</script>', html, re.S,
        )
        self.assertIsNotNone(bloque)
        self.assertEqual(sorted(json.loads(bloque.group(1))), sorted([self.producto.id, otro.id]))

    def test_sin_cliente_preseleccionado_la_lista_de_ids_es_un_json_vacio(self):
        html = self.pagina()
        bloque = re.search(
            r'<script id="productos-cliente-ids" type="application/json">(.*?)</script>', html, re.S,
        )
        self.assertIsNotNone(bloque)
        self.assertEqual(json.loads(bloque.group(1)), [])

    def test_el_buscador_no_promete_buscar_por_codigo(self):
        html = self.pagina()
        buscador = re.search(r'<input[^>]*id="searchProductos"[^>]*>', html, re.S).group(0)
        self.assertIn('placeholder="Buscar producto por nombre (Enter agrega el primero)"', buscador)
        self.assertNotIn('código', buscador)

    def test_la_pantalla_no_deja_console_log_de_depuracion(self):
        self.assertNotIn('console.log(', self.pagina())

    def test_las_compras_del_cliente_se_escapan_al_insertarlas_en_el_buscador(self):
        self.assertIn('${escaparHtml(cliente.compras)} compras', self.pagina())


class BorradorVentaTests(GastosVentaBase):
    """T7 (3.7.1): tras un error de validación la pantalla avisa al JS para recuperar la venta.

    La restauración en sí (sessionStorage) solo se prueba a mano en el navegador.
    """

    MARCA = 'data-venta-error="1"'

    def test_un_envio_invalido_redirige_a_una_pantalla_que_marca_el_error(self):
        respuesta = self.client.post(reverse('crear_venta'), self.datos(descuento='abc'), follow=True)
        self.assertEqual(respuesta.redirect_chain, [(reverse('crear_venta'), 302)])
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.MARCA, count=1)
        self.assertEqual(Venta.objects.count(), 0)

    def test_sin_error_la_pantalla_no_marca_nada(self):
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertNotContains(respuesta, self.MARCA)

    def test_un_aviso_que_no_es_error_no_activa_la_recuperacion(self):
        # Un token de envío inválido solo registra una advertencia y la venta se crea.
        respuesta = self.client.post(
            reverse('crear_venta'), self.datos(token_envio='no-es-un-uuid'), follow=True,
        )
        self.assertEqual(Venta.objects.count(), 1)
        respuesta = self.client.get(reverse('crear_venta'))
        self.assertNotContains(respuesta, self.MARCA)

    def test_la_pantalla_de_edicion_no_marca_errores(self):
        venta = Venta.objects.create(empresa=self.empresa, cliente=self.cliente)
        DetalleVenta.objects.create(venta=venta, producto=self.producto, precio_unitario=Decimal('100.00'))
        respuesta = self.client.post(
            reverse('editar_venta', args=[venta.id]), {'descuento': 'abc', 'envio': '0', 'otros_gastos': '0'},
            follow=True,
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, self.MARCA)

    def test_la_pantalla_de_venta_trae_la_clave_del_borrador_y_el_aviso(self):
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn("'danstore.venta.borrador'", html)
        self.assertIn('Recuperamos los datos de la venta que no se pudo guardar.', html)

    def test_sin_error_la_pantalla_descarta_el_borrador_viejo(self):
        html = self.client.get(reverse('crear_venta')).content.decode()
        self.assertIn('sessionStorage.removeItem(CLAVE_BORRADOR)', html)
