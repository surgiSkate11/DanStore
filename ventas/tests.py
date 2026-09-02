from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import reverse

from clientes.models import Cliente
from empresas.models import Empresa
from productos.models import Producto, TipoProducto
from ventas.models import ConfiguracionFactura, Venta
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
