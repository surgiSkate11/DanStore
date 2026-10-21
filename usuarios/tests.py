from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empresas.models import ConfiguracionSaaS
from empresas.testing import crear_empresa_con_dueno
from .backends import EmailOrUsernameModelBackend
from .models import LoginSecurityAttempt


class LoginSecurityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='usuario_seguro',
            email='usuario_seguro@example.com',
            password='Correcta-123!',
        )
        self.config = ConfiguracionSaaS.objects.create(
            id=1,
            login_lockout_enabled=True,
            login_max_attempts=3,
            login_lockout_minutes=15,
        )
        self.backend = EmailOrUsernameModelBackend()

    def tearDown(self):
        LoginSecurityAttempt.objects.filter(user=self.user).delete()

    def test_bloquea_despues_del_limite_y_rechaza_password_correcta(self):
        for _ in range(3):
            self.assertIsNone(self.backend.authenticate(None, self.user.username, 'incorrecta'))

        intento = LoginSecurityAttempt.objects.get(user=self.user)
        self.assertGreater(intento.locked_until, timezone.now())
        self.assertIsNone(self.backend.authenticate(None, self.user.username, 'Correcta-123!'))

    def test_permite_login_y_limpia_estado_despues_del_bloqueo(self):
        for _ in range(3):
            self.backend.authenticate(None, self.user.username, 'incorrecta')

        intento = LoginSecurityAttempt.objects.get(user=self.user)
        intento.locked_until = timezone.now() - timedelta(seconds=1)
        intento.save(update_fields=['locked_until', 'updated_at'])

        self.assertEqual(
            self.backend.authenticate(None, self.user.username, 'Correcta-123!'),
            self.user,
        )
        self.assertFalse(LoginSecurityAttempt.objects.filter(user=self.user).exists())

    def test_login_muestra_mensaje_corto(self):
        response = self.client.post(
            '/login/',
            {'username': self.user.username, 'password': 'incorrecta'},
            follow=True,
        )

        self.assertContains(response, 'Usuario o contraseña incorrectos.')
        self.assertNotContains(response, 'Note que puede que ambos campos')

class PanelAdminOcultoTests(TestCase):
    """C10: el panel vive en ADMIN_URL y /admin/ es una trampa que responde 404."""

    def test_admin_por_defecto_responde_404_y_registra_el_intento(self):
        with self.assertLogs('seguridad', level='WARNING') as registro:
            respuesta = self.client.get('/admin/', REMOTE_ADDR='203.0.113.7')
        self.assertEqual(respuesta.status_code, 404)
        self.assertIn('/admin/', registro.output[0])
        self.assertIn('203.0.113.7', registro.output[0])

    def test_registro_no_acepta_lineas_falsas_desde_x_forwarded_for(self):
        with self.assertLogs('seguridad', level='WARNING') as registro:
            self.client.get('/admin/', HTTP_X_FORWARDED_FOR='1.2.3.4\nLINEA FALSA')
        self.assertEqual(len(registro.records), 1)
        self.assertNotIn('\n', registro.records[0].getMessage())

    def test_subrutas_del_admin_por_defecto_tambien_son_trampa(self):
        with self.assertLogs('seguridad', level='WARNING'):
            respuesta = self.client.get('/admin/login/')
        self.assertEqual(respuesta.status_code, 404)

    def test_rutas_que_prueban_los_robots_responden_404(self):
        for ruta in ['/wp-admin/', '/wp-login.php', '/.env', '/phpmyadmin/']:
            with self.subTest(ruta), self.assertLogs('seguridad', level='WARNING'):
                self.assertEqual(self.client.get(ruta).status_code, 404)

    def test_admin_url_muestra_el_login_del_panel(self):
        respuesta = self.client.get(f'/{settings.ADMIN_URL}login/')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'name="username"')

    def test_admin_url_no_tiene_valor_por_defecto(self):
        self.assertNotEqual(settings.ADMIN_URL, 'admin/')
        self.assertTrue(settings.ADMIN_URL.endswith('/'))
        self.assertFalse(settings.ADMIN_URL.startswith('/'))


class PanelAdminCuentaSuspendidaTests(TestCase):
    def test_cuenta_suspendida_puede_abrir_el_login_de_admin_url(self):
        empresa, dueno = crear_empresa_con_dueno('vencida')
        empresa.activa = False
        empresa.save()
        self.client.force_login(dueno)
        respuesta = self.client.get(f'/{settings.ADMIN_URL}login/')
        self.assertNotEqual(respuesta.get('Location'), reverse('cuenta_suspendida'))
