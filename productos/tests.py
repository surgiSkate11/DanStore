import importlib
import os
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from empresas.testing import crear_empresa_con_dueno
from productos import sheets_sync
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


class SheetsSyncAislamientoTests(TestCase):
    """La hoja de Google Sheets de una empresa nunca la usa otra."""

    URL_A = 'https://docs.google.com/spreadsheets/d/hoja-de-a'
    URL_B = 'https://docs.google.com/spreadsheets/d/hoja-de-b'

    def setUp(self):
        self.empresa_a, _ = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')
        self.empresa_a.google_sheets_config = {'sheet_url': self.URL_A}
        self.empresa_a.save(update_fields=['google_sheets_config'])
        # Antes, la última URL sincronizada quedaba en una clave global de caché.
        cache.set('last_sheet_url', self.URL_A)
        self.addCleanup(cache.clear)

    def agregar_cliente(self, empresa):
        cliente_google = mock.Mock()
        cliente_google.open_by_url.return_value.get_worksheet.return_value.row_values.return_value = ['Cliente']
        cliente_google.open_by_url.return_value.get_worksheet.return_value.col_values.return_value = ['Cliente']
        with mock.patch.object(sheets_sync, 'conectar_google_sheets', return_value=(cliente_google, None)):
            resultado = sheets_sync.agregar_cliente_a_sheets('Ana', empresa=empresa)
        return resultado, cliente_google

    def test_sin_hoja_propia_no_usa_la_hoja_de_otra_empresa(self):
        (exito, mensaje), cliente_google = self.agregar_cliente(self.empresa_b)
        self.assertFalse(exito)
        self.assertEqual(mensaje, 'No se ha configurado la URL del Google Sheet')
        cliente_google.open_by_url.assert_not_called()

    def test_usa_la_hoja_guardada_en_su_propia_empresa(self):
        self.empresa_b.google_sheets_config = {'sheet_url': self.URL_B}
        self.empresa_b.save(update_fields=['google_sheets_config'])
        (exito, _), cliente_google = self.agregar_cliente(self.empresa_b)
        self.assertTrue(exito)
        cliente_google.open_by_url.assert_called_once_with(self.URL_B)


class SheetsSyncOAuthTests(TestCase):
    def test_oauth_por_http_solo_en_desarrollo(self):
        for debug, esperado in [(False, None), (True, '1')]:
            with self.subTest(DEBUG=debug), override_settings(DEBUG=debug), \
                    mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop('OAUTHLIB_INSECURE_TRANSPORT', None)
                importlib.reload(sheets_sync)
                self.assertEqual(os.environ.get('OAUTHLIB_INSECURE_TRANSPORT'), esperado)
        importlib.reload(sheets_sync)
