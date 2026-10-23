from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from empresas.testing import crear_empresa_con_dueno
from productos.models import Producto, TipoProducto


class AislamientoProductosTests(TestCase):
    def setUp(self):
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')
        self.tipo_b = TipoProducto.objects.create(empresa=self.empresa_b, nombre='Bebida caliente')
        self.producto_b = Producto.objects.create(
            empresa=self.empresa_b,
            nombre='Capuchino',
            categoria='Cafes',
            tipo_producto=self.tipo_b,
            precio=Decimal('2.00'),
            stock=10,
            estado='disponible',
        )
        self.client.force_login(self.dueno_a)

    def assertProductoBIntacto(self):
        self.producto_b.refresh_from_db()
        self.assertEqual(self.producto_b.nombre, 'Capuchino')
        self.assertEqual(self.producto_b.categoria, 'Cafes')
        self.assertEqual(self.producto_b.estado, 'disponible')

    def test_lista_no_muestra_productos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('lista_productos'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Capuchino')
        self.assertNotContains(respuesta, 'Bebida caliente')

    def test_editar_producto_ajeno_da_404(self):
        respuesta = self.client.get(reverse('editar_producto', args=[self.producto_b.pk]))
        self.assertEqual(respuesta.status_code, 404)

    def test_eliminar_producto_ajeno_da_404_y_no_lo_borra(self):
        respuesta = self.client.post(reverse('eliminar_producto', args=[self.producto_b.pk]))
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(Producto.objects.filter(pk=self.producto_b.pk).exists())

    def test_cambios_ajax_sobre_producto_ajeno_dan_404_y_no_lo_modifican(self):
        cambios = [
            ('cambiar_estado_producto', {'estado': 'vendido'}),
            ('cambiar_categoria_producto', {'categoria': 'Robada'}),
            ('cambiar_variante_producto', {'variante': 'Robada'}),
        ]
        for nombre_url, datos in cambios:
            with self.subTest(nombre_url):
                respuesta = self.client.post(reverse(nombre_url, args=[self.producto_b.pk]), datos)
                self.assertEqual(respuesta.status_code, 404)
        self.assertProductoBIntacto()

    def test_formulario_de_producto_no_ofrece_tipos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('crear_producto'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Bebida caliente')

    def test_crear_producto_no_acepta_tipo_de_otra_empresa(self):
        respuesta = self.client.post(reverse('crear_producto'), {
            'nombre': 'Pan de yuca',
            'categoria': 'Panes',
            'tipo_producto': self.tipo_b.pk,
            'precio': '0.25',
            'stock': '20',
            'estado': 'disponible',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('tipo_producto', respuesta.context['form'].errors)
        self.assertFalse(Producto.objects.filter(empresa=self.empresa_a).exists())
