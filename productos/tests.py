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
from ventas.models import ConfiguracionFactura, Venta


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


class StockCeroTests(TestCase):
    """Stock 0 es una cantidad válida (agotado); lo que se vigila es la coherencia con el estado."""

    MENSAJE = 'Un producto disponible necesita al menos 1 unidad en stock. Si se agotó, márcalo como vendido.'

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('panaderia')
        self.client.force_login(self.dueno)

    def crear(self, **extra):
        datos = dict(
            empresa=self.empresa, nombre='Pan de yuca', categoria='Panes',
            precio=Decimal('0.25'), stock=5, estado='disponible',
        )
        datos.update(extra)
        return Producto.objects.create(**datos)

    def datos_post(self, **extra):
        datos = {
            'nombre': 'Pan de yuca', 'categoria': 'Panes', 'precio': '0.25',
            'stock': '1', 'estado': 'disponible',
        }
        datos.update(extra)
        return datos

    def test_editar_producto_vendido_con_stock_cero_conserva_el_stock(self):
        producto = self.crear(stock=0, estado='vendido')
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(nombre='Pan de yuca grande', stock='0', estado='vendido'),
        )
        self.assertRedirects(respuesta, reverse('lista_productos'))
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pan de yuca grande')
        self.assertEqual(producto.stock, 0)
        self.assertEqual(producto.estado, 'vendido')

    def test_editar_producto_reservado_con_stock_cero_se_guarda(self):
        producto = self.crear(stock=0, estado='reservado')
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(descripcion='Apartado', stock='0', estado='reservado'),
        )
        self.assertRedirects(respuesta, reverse('lista_productos'))
        producto.refresh_from_db()
        self.assertEqual(producto.descripcion, 'Apartado')
        self.assertEqual(producto.stock, 0)

    def test_disponible_con_stock_cero_se_rechaza_y_no_guarda(self):
        producto = self.crear(stock=3, estado='disponible')
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(nombre='Cambiado', stock='0', estado='disponible'),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form'].errors['stock'], [self.MENSAJE])
        self.assertIn('Stock / Cantidad: ' + self.MENSAJE, [str(m) for m in respuesta.context['messages']])
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pan de yuca')
        self.assertEqual(producto.stock, 3)
        self.assertEqual(producto.estado, 'disponible')

    def test_reactivar_producto_vendido_sin_reponer_stock_se_rechaza(self):
        producto = self.crear(stock=0, estado='vendido')
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(stock='0', estado='disponible'),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form'].errors['stock'], [self.MENSAJE])
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 0)
        self.assertEqual(producto.estado, 'vendido')

    def test_crear_producto_sin_stock_usa_el_valor_por_defecto_de_uno(self):
        self.assertEqual(Producto._meta.get_field('stock').default, 1)
        respuesta = self.client.get(reverse('crear_producto'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form'].fields['stock'].initial, 1)

    def test_stock_negativo_se_rechaza_y_no_guarda(self):
        producto = self.crear(stock=3)
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(nombre='Cambiado', stock='-1'),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn('stock', respuesta.context['form'].errors)
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pan de yuca')
        self.assertEqual(producto.stock, 3)

    def test_crear_producto_disponible_con_stock_valido_se_guarda(self):
        respuesta = self.client.post(reverse('crear_producto'), self.datos_post(stock='4'))
        self.assertRedirects(respuesta, reverse('lista_productos'))
        self.assertEqual(Producto.objects.get(empresa=self.empresa).stock, 4)


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


class SheetsVentaSinIvaTests(TestCase):
    """Los precios de Google Sheets son finales: sus ventas se crean y se editan sin IVA."""

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('tienda-sheets')
        self.tipo = TipoProducto.objects.create(empresa=self.empresa, nombre='Ropa')
        self.producto = Producto.objects.create(
            empresa=self.empresa, nombre='Camisa', tipo_producto=self.tipo,
            precio=Decimal('10.00'), precio_real=Decimal('8.00'), stock=0,
            estado='vendido', vendido_a='Juan Perez',
        )
        self.client.force_login(self.dueno)

    def test_venta_de_sheets_se_crea_sin_iva_y_conserva_su_descuento(self):
        resultado = sheets_sync.sincronizar_ventas_desde_sheets(self.empresa)

        self.assertEqual(resultado['ventas_creadas'], 1)
        venta = Venta.objects.get(empresa=self.empresa)
        self.assertEqual(venta.origen, 'sheets')
        self.assertEqual(venta.porcentaje_iva, Decimal('0'))
        self.assertEqual(venta.iva, Decimal('0'))
        self.assertEqual(venta.subtotal, Decimal('10.00'))
        self.assertEqual(venta.descuento, Decimal('2.00'))
        self.assertEqual(venta.total, Decimal('8.00'))

    def test_venta_de_sheets_sigue_sin_iva_despues_de_editarla(self):
        Producto.objects.filter(pk=self.producto.pk).update(precio_real=Decimal('10.00'))
        sheets_sync.sincronizar_ventas_desde_sheets(self.empresa)
        venta = Venta.objects.get(empresa=self.empresa)
        # Aunque la configuración de la empresa cobre IVA, la venta de Sheets no lo recibe.
        ConfiguracionFactura.objects.update_or_create(
            empresa=self.empresa, defaults={'porcentaje_iva': Decimal('15.00')},
        )

        response = self.client.post(reverse('editar_venta', args=[venta.id]), {
            'descuento': '0', 'envio': '3.00', 'otros_gastos': '0',
            'descripcion_otros': '', 'notas': 'ajuste', 'metodo_pago': 'efectivo',
        })

        self.assertRedirects(response, reverse('detalle_venta', args=[venta.id]))
        venta.refresh_from_db()
        self.assertEqual(venta.iva, Decimal('0.00'))
        self.assertEqual(venta.porcentaje_iva, Decimal('0.00'))
        self.assertEqual(venta.total, Decimal('13.00'))


MENSAJE_VENDIDO_CON_STOCK = (
    'Un producto con stock no puede estar vendido. Si se vendió todo, pon el stock en 0.'
)
MENSAJE_DISPONIBLE_SIN_STOCK = (
    'Un producto disponible necesita al menos 1 unidad en stock. Si se agotó, márcalo como vendido.'
)


class StockSegunEstadoReglaTests(TestCase):
    """L21: cuando manda el estado (Google Sheets), una sola regla ajusta el stock."""

    def test_regla_de_stock_segun_estado(self):
        regla = Producto.stock_segun_estado
        self.assertEqual(regla('vendido', 6), 0)
        self.assertEqual(regla('vendido', 0), 0)
        self.assertEqual(regla('vendido', None), 0)
        self.assertEqual(regla('disponible', 0), 1)
        self.assertEqual(regla('disponible', 3), 3)
        self.assertEqual(regla('disponible', None), 1)
        self.assertEqual(regla('reservado', 0), 0)
        self.assertEqual(regla('reservado', 6), 6)
        self.assertEqual(regla('reservado', None), 1)


class EstadoSegunStockEdicionTests(TestCase):
    """S8: la edición manual no permite vendido con stock."""

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('estado-stock-form')
        self.client.force_login(self.dueno)

    def crear(self, **extra):
        datos = dict(
            empresa=self.empresa, nombre='Pan', categoria='Panes',
            precio=Decimal('0.25'), stock=6, estado='disponible',
        )
        datos.update(extra)
        return Producto.objects.create(**datos)

    def datos_post(self, **extra):
        datos = {
            'nombre': 'Pan', 'categoria': 'Panes', 'precio': '0.25',
            'stock': '6', 'estado': 'disponible',
        }
        datos.update(extra)
        return datos

    def test_editar_a_vendido_con_stock_se_rechaza_y_no_guarda(self):
        producto = self.crear(stock=6, estado='disponible')
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(nombre='Cambiado', stock='6', estado='vendido'),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form'].errors['stock'], [MENSAJE_VENDIDO_CON_STOCK])
        producto.refresh_from_db()
        self.assertEqual(producto.nombre, 'Pan')
        self.assertEqual(producto.stock, 6)
        self.assertEqual(producto.estado, 'disponible')

    def test_crear_vendido_con_stock_se_rechaza_y_no_crea(self):
        respuesta = self.client.post(
            reverse('crear_producto'), self.datos_post(stock='1', estado='vendido'),
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context['form'].errors['stock'], [MENSAJE_VENDIDO_CON_STOCK])
        self.assertEqual(Producto.objects.filter(empresa=self.empresa).count(), 0)

    def test_vendido_con_stock_cero_se_guarda(self):
        producto = self.crear(stock=6)
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(stock='0', estado='vendido'),
        )
        self.assertRedirects(respuesta, reverse('lista_productos'))
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))

    def test_reservado_se_guarda_con_cualquier_stock(self):
        producto = self.crear(stock=6)
        for stock in ('6', '0'):
            respuesta = self.client.post(
                reverse('editar_producto', args=[producto.pk]),
                self.datos_post(stock=stock, estado='reservado'),
            )
            self.assertRedirects(respuesta, reverse('lista_productos'))
            producto.refresh_from_db()
            self.assertEqual((producto.stock, producto.estado), (int(stock), 'reservado'))

    def test_disponible_con_stock_cero_conserva_el_mensaje_anterior(self):
        producto = self.crear(stock=6)
        respuesta = self.client.post(
            reverse('editar_producto', args=[producto.pk]),
            self.datos_post(stock='0', estado='disponible'),
        )
        self.assertEqual(respuesta.context['form'].errors['stock'], [MENSAJE_DISPONIBLE_SIN_STOCK])
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (6, 'disponible'))


class EstadoSegunStockCambioRapidoTests(TestCase):
    """S8: el cambio rápido de estado (AJAX) respeta el stock."""

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('estado-stock-rapido')
        self.client.force_login(self.dueno)

    def crear(self, stock, estado):
        return Producto.objects.create(
            empresa=self.empresa, nombre='Pan', categoria='Panes',
            precio=Decimal('0.25'), stock=stock, estado=estado,
        )

    def cambiar(self, producto, estado):
        return self.client.post(
            reverse('cambiar_estado_producto', args=[producto.pk]), {'estado': estado},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )

    def test_vendido_con_stock_se_rechaza_sin_tocar_la_base(self):
        producto = self.crear(6, 'disponible')
        respuesta = self.cambiar(producto, 'vendido')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(
            respuesta.json(), {'success': False, 'error': MENSAJE_VENDIDO_CON_STOCK},
        )
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (6, 'disponible'))

    def test_disponible_con_stock_cero_se_rechaza_sin_tocar_la_base(self):
        producto = self.crear(0, 'vendido')
        respuesta = self.cambiar(producto, 'disponible')
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(
            respuesta.json(), {'success': False, 'error': MENSAJE_DISPONIBLE_SIN_STOCK},
        )
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))

    def test_reservado_se_permite_con_cualquier_stock(self):
        for stock in (6, 0):
            producto = self.crear(stock, 'disponible' if stock else 'vendido')
            respuesta = self.cambiar(producto, 'reservado')
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(respuesta.json(), {'success': True, 'estado': 'Reservado'})
            producto.refresh_from_db()
            self.assertEqual((producto.stock, producto.estado), (stock, 'reservado'))

    def test_cambios_coherentes_se_siguen_guardando(self):
        con_stock = self.crear(3, 'reservado')
        self.assertEqual(self.cambiar(con_stock, 'disponible').status_code, 200)
        con_stock.refresh_from_db()
        self.assertEqual(con_stock.estado, 'disponible')
        sin_stock = self.crear(0, 'reservado')
        self.assertEqual(self.cambiar(sin_stock, 'vendido').status_code, 200)
        sin_stock.refresh_from_db()
        self.assertEqual(sin_stock.estado, 'vendido')

    def test_estado_invalido_sigue_dando_400(self):
        producto = self.crear(2, 'disponible')
        self.assertEqual(self.cambiar(producto, 'inventado').status_code, 400)
        producto.refresh_from_db()
        self.assertEqual(producto.estado, 'disponible')


class EstadoSegunStockSheetsTests(TestCase):
    """S8 / L21: la hoja no trae stock, así que manda su estado y el stock se ajusta; cada ajuste queda anotado."""

    ENCABEZADOS = ['Nombre', 'Tipo', 'Categoría', 'Variante', 'Precio Venta',
                   'Precio Real', 'Estado', 'Vendido a']

    def setUp(self):
        self.empresa, self.dueno = crear_empresa_con_dueno('estado-stock-sheets')
        self.client.force_login(self.dueno)

    def fila(self, nombre, estado, vendido_a=''):
        return [nombre, 'Ropa', 'Camisas', 'M', '10', '8', estado, vendido_a]

    def crear(self, nombre, fila_hoja, stock, estado):
        tipo, _ = TipoProducto.objects.get_or_create(empresa=self.empresa, nombre='Ropa')
        return Producto.objects.create(
            empresa=self.empresa, nombre=nombre, categoria='Camisas', variante='M',
            precio=Decimal('10'), precio_real=Decimal('8'), stock=stock, estado=estado,
            google_sheets_row=fila_hoja, origen='sheets', tipo_producto=tipo,
        )

    def sincronizar(self, filas):
        hoja = mock.Mock()
        hoja.get_all_values.return_value = [self.ENCABEZADOS] + filas
        libro = mock.Mock()
        libro.get_worksheet.return_value = hoja
        cliente = mock.Mock()
        cliente.open_by_url.return_value = libro
        with mock.patch.object(sheets_sync, 'conectar_google_sheets', return_value=(cliente, None)):
            respuesta = self.client.post(
                reverse('sincronizar_sheets'),
                {'sheet_url': 'https://docs.google.com/spreadsheets/d/x'}, follow=True,
            )
        return [str(m) for m in respuesta.context['messages']]

    def correcciones(self, mensajes):
        return [m for m in mensajes if 'se ajustó el stock' in m.lower()]

    def test_vendido_en_la_hoja_deja_el_stock_en_cero_y_se_anota(self):
        producto = self.crear('Camisa A', 2, 6, 'disponible')
        mensajes = self.sincronizar([self.fila('Camisa A', 'Vendido')])
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))
        resumen = self.correcciones(mensajes)
        self.assertEqual(len(resumen), 1, mensajes)
        self.assertIn('Fila 2', resumen[0])

    def test_vendido_importado_con_stock_uno_sigue_vendido(self):
        # Antes de L21 los vendidos de Sheets quedaban con el stock por defecto (1):
        # la hoja manda, siguen vendidos y no se pierden como disponibles.
        producto = self.crear('Camisa A', 2, 1, 'vendido')
        self.sincronizar([self.fila('Camisa A', 'Vendido', 'Ana')])
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))

    def test_disponible_en_la_hoja_con_stock_cero_pasa_a_uno_y_se_anota(self):
        producto = self.crear('Camisa A', 2, 0, 'vendido')
        mensajes = self.sincronizar([self.fila('Camisa A', 'Disponible')])
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (1, 'disponible'))
        resumen = self.correcciones(mensajes)
        self.assertEqual(len(resumen), 1, mensajes)
        self.assertIn('Fila 2', resumen[0])

    def test_reservado_no_se_toca_con_ningun_stock(self):
        con_stock = self.crear('Camisa A', 2, 6, 'disponible')
        sin_stock = self.crear('Camisa B', 3, 0, 'vendido')
        mensajes = self.sincronizar([
            self.fila('Camisa A', 'Reservado'), self.fila('Camisa B', 'Reservado'),
        ])
        for producto, stock in ((con_stock, 6), (sin_stock, 0)):
            producto.refresh_from_db()
            self.assertEqual((producto.stock, producto.estado), (stock, 'reservado'))
        self.assertEqual(self.correcciones(mensajes), [])

    def test_coherente_no_se_corrige_ni_se_anota(self):
        producto = self.crear('Camisa A', 2, 0, 'vendido')
        mensajes = self.sincronizar([self.fila('Camisa A', 'Vendido')])
        producto.refresh_from_db()
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))
        self.assertEqual(self.correcciones(mensajes), [])

    def test_producto_nuevo_vendido_se_crea_con_stock_cero(self):
        mensajes = self.sincronizar([self.fila('Camisa N', 'Vendido', 'Ana')])
        producto = Producto.objects.get(empresa=self.empresa, nombre='Camisa N')
        self.assertEqual((producto.stock, producto.estado), (0, 'vendido'))
        self.assertEqual(self.correcciones(mensajes), [])

    def test_producto_nuevo_disponible_se_crea_con_stock_uno(self):
        self.sincronizar([self.fila('Camisa N', 'Disponible')])
        producto = Producto.objects.get(empresa=self.empresa, nombre='Camisa N')
        self.assertEqual((producto.stock, producto.estado), (1, 'disponible'))
