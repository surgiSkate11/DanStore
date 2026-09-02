from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase

from empresas.models import Empresa
from clientes.models import Cliente
from clientes.views import lista_clientes


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
