import importlib
from decimal import Decimal
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError
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
        self.assertEqual(response.url, reverse('detalle_venta', args=[Venta.objects.latest('id').id]))

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
        self.assertContains(respuesta, 'baguette')  # la plantilla pinta data-nombre en minúsculas
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
