from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class BaseTemplateClientesExportTest(SimpleTestCase):
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
