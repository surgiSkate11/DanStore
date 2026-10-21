from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone

from empresas.models import ConfiguracionSaaS
from empresas.testing import crear_empresa_con_dueno
from .backends import EmailOrUsernameModelBackend
from .models import LoginSecurityAttempt
from tiendita_project.utils import obtener_ip_cliente
from . import views as usuarios_views


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


class PaginasDeErrorTests(TestCase):
    """C11: Django solo lee handler403/404/500 desde el urls.py raíz."""

    def setUp(self):
        self.request = RequestFactory().get('/algo/')
        self.request.user = AnonymousUser()

    def test_handlers_se_declaran_en_urls(self):
        resolver = get_resolver()
        self.assertIs(resolver.resolve_error_handler(403), usuarios_views.error_403_view)
        self.assertIs(resolver.resolve_error_handler(404), getattr(usuarios_views, 'error_404_view', None))
        self.assertIs(resolver.resolve_error_handler(500), getattr(usuarios_views, 'error_500_view', None))

    def test_pagina_404_propia_en_espanol(self):
        respuesta = self.client.get('/esta-ruta-no-existe/')
        self.assertEqual(respuesta.status_code, 404)
        self.assertTemplateUsed(respuesta, '404.html')
        self.assertContains(respuesta, 'Página no encontrada', status_code=404)

    def test_pagina_404_propia_con_sesion_iniciada(self):
        _, dueno = crear_empresa_con_dueno('panaderia')
        self.client.force_login(dueno)
        respuesta = self.client.get('/esta-ruta-no-existe/')
        self.assertContains(respuesta, 'Página no encontrada', status_code=404)

    def test_pagina_403_propia_se_renderiza(self):
        respuesta = usuarios_views.error_403_view(self.request, PermissionDenied())
        self.assertEqual(respuesta.status_code, 403)
        self.assertIn('Acceso restringido', respuesta.content.decode())

    def test_pagina_500_propia_no_muestra_detalles(self):
        respuesta = usuarios_views.error_500_view(self.request)
        self.assertEqual(respuesta.status_code, 500)
        contenido = respuesta.content.decode()
        self.assertIn('Algo salió mal', contenido)
        self.assertNotIn('Traceback', contenido)


class LimitePorIpTests(TestCase):
    """S12: 10 intentos por minuto por IP en login y recuperación; el 11 recibe 429."""

    IP = '203.0.113.10'

    def setUp(self):
        caches['ratelimit'].clear()
        self.addCleanup(caches['ratelimit'].clear)
        # Congela el reloj de django_ratelimit: la ventana es fija y, si el minuto
        # cambiara a mitad de la prueba, el contador se reiniciaría.
        reloj = mock.patch('django_ratelimit.core.time')
        reloj.start().time.return_value = 1_700_000_000.0
        self.addCleanup(reloj.stop)

    def _post(self, url, datos, **extra):
        extra.setdefault('REMOTE_ADDR', self.IP)
        return self.client.post(url, datos, **extra)

    def _login(self, **extra):
        return self._post('/login/', {'username': 'nadie', 'password': 'incorrecta'}, **extra)

    def _password_reset(self, **extra):
        return self._post(reverse('password_reset'), {'username': 'nadie'}, **extra)

    def _username_reset(self, **extra):
        return self._post(reverse('username_reset'), {'email': 'nadie@example.com'}, **extra)

    def _assert_limite_en_el_intento_once(self, enviar):
        for numero in range(1, 11):
            self.assertNotEqual(enviar().status_code, 429, f'El intento {numero} no debe limitarse')
        respuesta = enviar()
        self.assertEqual(respuesta.status_code, 429)
        self.assertTemplateUsed(respuesta, '429.html')
        self.assertContains(respuesta, 'Demasiados intentos', status_code=429)
        self.assertContains(respuesta, 'un minuto', status_code=429)

    def test_login_responde_429_en_el_intento_once(self):
        self._assert_limite_en_el_intento_once(self._login)

    def test_login_otra_ip_no_se_ve_afectada(self):
        for _ in range(11):
            self._login()
        self.assertEqual(self._login().status_code, 429)
        respuesta = self._login(REMOTE_ADDR='203.0.113.11')
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Usuario o contraseña incorrectos.')

    def test_login_cuenta_la_ultima_ip_de_x_forwarded_for(self):
        proxy = {'REMOTE_ADDR': '10.0.0.1'}
        for numero in range(10):
            respuesta = self._login(HTTP_X_FORWARDED_FOR=f'falsa-{numero}, 198.51.100.7', **proxy)
            self.assertEqual(respuesta.status_code, 200)
        # El primer valor lo controla el cliente: cambiarlo no reinicia el contador.
        respuesta = self._login(HTTP_X_FORWARDED_FOR='otra-falsa, 198.51.100.7', **proxy)
        self.assertEqual(respuesta.status_code, 429)
        # Otra IP real detrás del mismo proxy no se ve afectada.
        respuesta = self._login(HTTP_X_FORWARDED_FOR='otra-falsa, 198.51.100.8', **proxy)
        self.assertEqual(respuesta.status_code, 200)

    def test_get_nunca_se_limita(self):
        for _ in range(15):
            self.assertEqual(self.client.get('/login/', REMOTE_ADDR=self.IP).status_code, 200)
        for _ in range(11):
            self._login()
        self.assertEqual(self._login().status_code, 429)
        self.assertEqual(self.client.get('/login/', REMOTE_ADDR=self.IP).status_code, 200)
        self.assertEqual(self.client.get(reverse('password_reset'), REMOTE_ADDR=self.IP).status_code, 200)
        self.assertEqual(self.client.get(reverse('username_reset'), REMOTE_ADDR=self.IP).status_code, 200)

    def test_recuperar_password_responde_429_en_el_intento_once(self):
        self._assert_limite_en_el_intento_once(self._password_reset)

    def test_recuperar_usuario_responde_429_en_el_intento_once(self):
        self._assert_limite_en_el_intento_once(self._username_reset)

    def test_cada_vista_lleva_su_propio_contador(self):
        for _ in range(11):
            self._login()
        self.assertEqual(self._login().status_code, 429)
        self.assertEqual(self._password_reset().status_code, 200)
        self.assertEqual(self._username_reset().status_code, 200)

    def test_el_limite_por_ip_no_impide_contar_intentos_por_cuenta(self):
        usuario = get_user_model().objects.create_user(
            username='cuenta_bloqueada', password='Correcta-123!',
        )
        ConfiguracionSaaS.objects.create(
            id=1, login_lockout_enabled=True, login_max_attempts=3, login_lockout_minutes=15,
        )
        for _ in range(3):
            self._post('/login/', {'username': usuario.username, 'password': 'incorrecta'})
        self.assertTrue(
            LoginSecurityAttempt.objects.filter(user=usuario, locked_until__gt=timezone.now()).exists()
        )


class ObtenerIpClienteTests(TestCase):
    """RATELIMIT_IP_META_KEY: detrás del proxy el primer valor de X-Forwarded-For lo controla el cliente."""

    def _ip(self, **meta):
        meta.setdefault('REMOTE_ADDR', '10.0.0.1')
        return obtener_ip_cliente(RequestFactory().get('/', **meta))

    def test_usa_el_ultimo_valor_de_x_forwarded_for(self):
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='falsa, 198.51.100.7'), '198.51.100.7')

    def test_quita_espacios_del_ultimo_valor(self):
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='1.2.3.4,   198.51.100.7  '), '198.51.100.7')

    def test_sin_x_forwarded_for_usa_remote_addr(self):
        self.assertEqual(self._ip(), '10.0.0.1')

    def test_valor_que_no_es_una_ip_usa_remote_addr(self):
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='198.51.100.7, basura'), '10.0.0.1')
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR=' '), '10.0.0.1')

    def test_acepta_ipv6(self):
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='falsa, 2001:db8::1'), '2001:db8::1')
