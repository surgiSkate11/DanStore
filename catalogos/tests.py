import shutil
import tempfile
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from catalogos import utils
from empresas.testing import crear_empresa_con_dueno
from productos.models import Producto, TipoProducto


class AislamientoCatalogosTests(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        ajustes = override_settings(MEDIA_ROOT=self.media)
        ajustes.enable()
        self.addCleanup(ajustes.disable)

        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')
        Producto.objects.create(
            empresa=self.empresa_a, nombre='Pan de yuca', categoria='Panes',
            precio=Decimal('0.50'), stock=20, estado='disponible',
        )
        self.tipo_b = TipoProducto.objects.create(empresa=self.empresa_b, nombre='Bebida caliente')
        self.producto_b = Producto.objects.create(
            empresa=self.empresa_b, nombre='Capuchino', categoria='Cafes', marca='Cafe Andino',
            tipo_producto=self.tipo_b, precio=Decimal('2.00'), stock=10, estado='disponible',
        )
        self.client.force_login(self.dueno_a)

    def test_contar_solo_cuenta_productos_de_la_empresa(self):
        respuesta = self.client.get(reverse('contar_productos_catalogo'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {'total': 1})

    def test_seleccionar_producto_ajeno_no_lo_incluye(self):
        respuesta = self.client.get(reverse('contar_productos_catalogo'), {'seleccion': str(self.producto_b.pk)})
        self.assertEqual(respuesta.json(), {'total': 0})

    def test_generar_no_muestra_productos_ni_filtros_de_otra_empresa(self):
        respuesta = self.client.get(reverse('generar_catalogo'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['total_productos'], 1)
        self.assertContains(respuesta, 'Panes')
        for texto in ('Capuchino', 'Cafes', 'Cafe Andino', 'Bebida caliente'):
            self.assertNotContains(respuesta, texto)

    def test_filtrar_por_tipo_ajeno_no_devuelve_sus_productos(self):
        respuesta = self.client.get(reverse('preview_catalogo'), {'tipos_producto': self.tipo_b.pk})
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Capuchino')

    def test_vista_previa_no_muestra_productos_de_otra_empresa(self):
        respuesta = self.client.get(reverse('preview_catalogo'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Pan de yuca')
        self.assertNotContains(respuesta, 'Capuchino')

    def test_descargar_con_producto_ajeno_da_catalogo_vacio(self):
        respuesta = self.client.get(reverse('descargar_catalogo'), {'seleccion': str(self.producto_b.pk)})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['Content-Disposition'], 'attachment; filename="catalogo_vacio.pdf"')

    def test_personalizar_no_muestra_ni_modifica_el_diseno_de_otra_empresa(self):
        carpeta_b = utils.catalogo_dir(self.empresa_b.id)
        utils.save_catalogo_config(carpeta_b, {'nombre_negocio': 'Cafe Secreto'})

        respuesta = self.client.get(reverse('personalizar_catalogo'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Cafe Secreto')

        self.client.post(reverse('personalizar_catalogo'), {'nombre_negocio': 'Panaderia A'})
        self.assertEqual(utils.load_catalogo_config(carpeta_b)['nombre_negocio'], 'Cafe Secreto')
