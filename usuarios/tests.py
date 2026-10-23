import base64
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import caches
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase
from django.urls import get_resolver, reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

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

    def test_en_render_cada_cliente_tiene_su_contador_aunque_compartan_borde_de_cloudflare(self):
        # Render: Cliente -> Cloudflare -> proxy de Render -> app. El último valor de
        # X-Forwarded-For es la IP pública del borde de Cloudflare, igual para muchos clientes.
        def detras_de_render(cliente, falsa='falsa'):
            return {
                'REMOTE_ADDR': '10.21.157.68',
                'HTTP_X_FORWARDED_FOR': f'{falsa}, {cliente}, 104.22.17.40',
                'HTTP_TRUE_CLIENT_IP': cliente,
                'HTTP_CF_CONNECTING_IP': cliente,
            }
        for numero in range(10):
            respuesta = self._login(**detras_de_render('99.61.165.29', falsa=f'falsa-{numero}'))
            self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(self._login(**detras_de_render('99.61.165.29')).status_code, 429)
        # Otro cliente que entra por el mismo borde de Cloudflare no queda bloqueado.
        self.assertEqual(self._login(**detras_de_render('99.61.165.30')).status_code, 200)

    def test_entrar_directo_a_render_rotando_cf_connecting_ip_igual_llega_al_limite(self):
        for numero in range(11):
            respuesta = self._login(REMOTE_ADDR='10.21.157.68', HTTP_CF_CONNECTING_IP=f'6.6.6.{numero}',
                                    HTTP_X_FORWARDED_FOR=f'6.6.6.{numero}, 203.0.113.5')
        self.assertEqual(respuesta.status_code, 429)

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
    """RATELIMIT_IP_META_KEY en Render: la IP real la pone Cloudflare en CF-Connecting-IP."""

    def _ip(self, **meta):
        meta.setdefault('REMOTE_ADDR', '10.21.157.68')
        meta.setdefault('HTTP_X_FORWARDED_FOR', '99.61.165.29, 104.22.17.40')  # borde de Cloudflare
        return obtener_ip_cliente(RequestFactory().get('/', **meta))

    def test_quien_entra_directo_a_render_no_puede_inventar_su_ip(self):
        self.assertEqual(self._ip(
            HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.5', HTTP_CF_CONNECTING_IP='6.6.6.6',
            HTTP_TRUE_CLIENT_IP='6.6.6.6',
        ), '203.0.113.5')

    def test_usa_la_ip_que_pone_cloudflare(self):
        self.assertEqual(self._ip(
            HTTP_TRUE_CLIENT_IP='99.61.165.29',
            HTTP_CF_CONNECTING_IP='99.61.165.29',
            HTTP_X_FORWARDED_FOR='99.61.165.29, 104.22.17.40',
        ), '99.61.165.29')

    def test_sin_cf_connecting_ip_usa_true_client_ip(self):
        self.assertEqual(self._ip(HTTP_TRUE_CLIENT_IP=' 99.61.165.29 '), '99.61.165.29')

    def test_cf_connecting_ip_gana_a_un_true_client_ip_falsificado(self):
        # Cloudflare siempre sobrescribe CF-Connecting-IP; True-Client-IP solo si la zona lo activa.
        self.assertEqual(self._ip(HTTP_TRUE_CLIENT_IP='6.6.6.6', HTTP_CF_CONNECTING_IP='99.61.165.29'), '99.61.165.29')

    def test_nunca_usa_x_forwarded_for(self):
        # Render lo agrega sin limpiarlo: el cliente lo controla y su último valor es Cloudflare.
        self.assertEqual(self._ip(HTTP_X_FORWARDED_FOR='198.51.100.7, 104.22.17.40'), '10.21.157.68')

    def test_sin_headers_de_cloudflare_usa_remote_addr(self):
        self.assertEqual(self._ip(), '10.21.157.68')

    def test_valor_que_no_es_una_ip_pasa_al_siguiente(self):
        self.assertEqual(self._ip(HTTP_CF_CONNECTING_IP='basura', HTTP_TRUE_CLIENT_IP='99.61.165.29'), '99.61.165.29')
        self.assertEqual(self._ip(HTTP_CF_CONNECTING_IP=' ', HTTP_TRUE_CLIENT_IP='1.2.3.4, 5.6.7.8'), '10.21.157.68')

    def test_acepta_ipv6(self):
        self.assertEqual(self._ip(HTTP_CF_CONNECTING_IP='2001:db8::1'), '2001:db8::1')

    def test_la_trampa_registra_la_misma_ip_que_el_limite(self):
        with self.assertLogs('seguridad', level='WARNING') as registro:
            self.client.get('/admin/', REMOTE_ADDR='10.21.157.68', HTTP_CF_CONNECTING_IP='99.61.165.29',
                            HTTP_X_FORWARDED_FOR='1.2.3.4, 104.22.17.40')
        self.assertIn("'99.61.165.29'", registro.output[0])
        self.assertNotIn('1.2.3.4', registro.output[0])


class BloqueoPorCuentaEnLoginTests(TestCase):
    """El bloqueo por cuenta (LoginSecurityAttempt) no se salta con otro backend."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='cuenta_bloqueada', email='bloqueada@example.com', password='Correcta-123!',
        )
        ConfiguracionSaaS.objects.create(
            id=1, login_lockout_enabled=True, login_max_attempts=3, login_lockout_minutes=15,
        )
        LoginSecurityAttempt.objects.create(
            user=self.user, failed_attempts=3, locked_until=timezone.now() + timedelta(minutes=15),
        )

    def test_cuenta_bloqueada_no_se_autentica_con_la_clave_correcta(self):
        self.assertIsNone(authenticate(username='cuenta_bloqueada', password='Correcta-123!'))

    def test_cuenta_bloqueada_no_inicia_sesion_por_la_vista_de_login(self):
        respuesta = self.client.post(reverse('login'), {
            'username': 'cuenta_bloqueada', 'password': 'Correcta-123!',
        }, REMOTE_ADDR='203.0.113.99')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


def _token_valido(dispositivo):
    """Código TOTP vigente de un dispositivo, como lo mostraría la app autenticadora."""
    return '{:06d}'.format(totp(
        dispositivo.bin_key, step=dispositivo.step, t0=dispositivo.t0, digits=dispositivo.digits,
    ))


class PanelAdminConDosFactoresTests(TestCase):
    """S13/RS-02: solo los superusuarios entran al panel, con segundo factor (2FA)."""

    PASSWORD = 'Clave-admin-123!'

    def setUp(self):
        caches['ratelimit'].clear()
        self.addCleanup(caches['ratelimit'].clear)
        self.indice = f'/{settings.ADMIN_URL}'
        self.login = f'/{settings.ADMIN_URL}login/'
        self.superusuario = get_user_model().objects.create_superuser(
            username='root', email='root@example.com', password=self.PASSWORD,
        )
        self.dispositivo = TOTPDevice.objects.create(user=self.superusuario, name='admin', confirmed=True)

    def _entrar(self, usuario='root', token=None):
        datos = {'username': usuario, 'password': self.PASSWORD, 'next': self.indice}
        if token is not None:
            datos['otp_token'] = token
        return self.client.post(self.login, datos)

    def test_superusuario_con_clave_pero_sin_segundo_factor_no_ve_el_panel(self):
        self.client.force_login(self.superusuario)
        respuesta = self.client.get(self.indice)
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(respuesta['Location'].startswith(self.login))

    def test_login_del_panel_pide_el_codigo_del_segundo_factor(self):
        respuesta = self.client.get(self.login)
        self.assertContains(respuesta, 'name="otp_token"')

    def test_login_del_panel_sin_codigo_falla(self):
        respuesta = self._entrar()
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(self.indice).status_code, 302)

    def test_login_del_panel_con_codigo_incorrecto_es_rechazado(self):
        respuesta = self._entrar(token='000000')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(self.indice).status_code, 302)

    def test_superusuario_con_codigo_valido_entra_al_panel(self):
        respuesta = self._entrar(token=_token_valido(self.dispositivo))
        self.assertRedirects(respuesta, self.indice, fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.indice).status_code, 200)

    def test_superusuario_sin_dispositivo_no_entra_aunque_la_clave_sea_correcta(self):
        self.dispositivo.delete()
        respuesta = self._entrar(token='123456')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_staff_que_no_es_superusuario_no_entra_aunque_tenga_dispositivo(self):
        staff = get_user_model().objects.create_user(
            username='staff', email='staff@example.com', password=self.PASSWORD, is_staff=True,
        )
        dispositivo = TOTPDevice.objects.create(user=staff, name='admin', confirmed=True)
        respuesta = self._entrar(usuario='staff', token=_token_valido(dispositivo))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get(self.indice).status_code, 302)

    def test_el_sitio_deniega_a_staff_verificado_que_no_es_superusuario(self):
        from django.contrib import admin
        staff = get_user_model().objects.create_user(username='staff2', password=self.PASSWORD, is_staff=True)
        peticion = RequestFactory().get(self.indice)
        peticion.user = staff
        staff.is_verified = lambda: True
        self.assertFalse(admin.site.has_permission(peticion))
        self.superusuario.is_verified = lambda: True
        peticion.user = self.superusuario
        self.assertTrue(admin.site.has_permission(peticion))

    def test_admin_por_defecto_sigue_siendo_404(self):
        with self.assertLogs('seguridad', level='WARNING'):
            self.assertEqual(self.client.get('/admin/').status_code, 404)

    def test_login_normal_de_un_dueno_de_empresa_no_pide_segundo_factor(self):
        crear_empresa_con_dueno('acme')
        respuesta = self.client.post(reverse('login'), {
            'username': 'dueno_acme', 'password': 'Clave-prueba-123',
        }, REMOTE_ADDR='203.0.113.50')
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn('_auth_user_id', self.client.session)


class CrearDosFactoresComandoTests(TestCase):
    """`manage.py crear_2fa <usuario>`: alta del dispositivo TOTP de un superusuario."""

    def setUp(self):
        self.superusuario = get_user_model().objects.create_superuser(
            username='root', email='root@example.com', password='Clave-admin-123!',
        )

    def _ejecutar(self, *args):
        salida = StringIO()
        call_command('crear_2fa', *args, stdout=salida)
        return salida.getvalue()

    def test_crea_un_dispositivo_confirmado_para_el_superusuario(self):
        self._ejecutar('root')
        dispositivo = TOTPDevice.objects.get(user=self.superusuario)
        self.assertEqual(dispositivo.name, 'admin')
        self.assertTrue(dispositivo.confirmed)

    def test_muestra_la_clave_base32_y_la_url_otpauth(self):
        salida = self._ejecutar('root')
        dispositivo = TOTPDevice.objects.get(user=self.superusuario)
        self.assertIn(base64.b32encode(dispositivo.bin_key).decode(), salida)
        self.assertIn('otpauth://totp/', salida)

    def test_el_codigo_generado_con_la_clave_entra_al_panel(self):
        self._ejecutar('root')
        dispositivo = TOTPDevice.objects.get(user=self.superusuario)
        respuesta = self.client.post(f'/{settings.ADMIN_URL}login/', {
            'username': 'root', 'password': 'Clave-admin-123!', 'otp_token': _token_valido(dispositivo),
        })
        self.assertEqual(respuesta.status_code, 302)

    def test_rechaza_a_un_usuario_que_no_es_superusuario(self):
        get_user_model().objects.create_user(username='staff', password='x', is_staff=True)
        with self.assertRaisesMessage(CommandError, 'superusuario'):
            self._ejecutar('staff')
        self.assertFalse(TOTPDevice.objects.exists())

    def test_rechaza_un_usuario_que_no_existe(self):
        with self.assertRaisesMessage(CommandError, 'no existe'):
            self._ejecutar('fantasma')

    def test_no_reemplaza_un_dispositivo_existente_sin_reemplazar(self):
        self._ejecutar('root')
        clave = TOTPDevice.objects.get(user=self.superusuario).key
        with self.assertRaisesMessage(CommandError, '--reemplazar'):
            self._ejecutar('root')
        self.assertEqual(TOTPDevice.objects.get(user=self.superusuario).key, clave)

    def test_reemplazar_cambia_la_clave_y_deja_un_solo_dispositivo(self):
        self._ejecutar('root')
        clave = TOTPDevice.objects.get(user=self.superusuario).key
        salida = self._ejecutar('root', '--reemplazar')
        dispositivo = TOTPDevice.objects.get(user=self.superusuario)
        self.assertNotEqual(dispositivo.key, clave)
        self.assertIn('otpauth://', salida)


class LoginPanelSinEnumeracionTests(TestCase):
    """El login del panel no revela si una contraseña de staff es correcta."""

    def setUp(self):
        get_user_model().objects.create_user('staff_comun', password='Correcta-123!', is_staff=True)

    def errores_del_login(self, password):
        respuesta = self.client.post(f'/{settings.ADMIN_URL}login/', {
            'username': 'staff_comun', 'password': password, 'otp_token': '123456',
        }, REMOTE_ADDR='203.0.113.50')
        self.assertEqual(respuesta.status_code, 200)
        return respuesta.context['form'].non_field_errors()

    def test_staff_con_clave_correcta_ve_el_mismo_error_que_con_clave_incorrecta(self):
        self.assertEqual(self.errores_del_login('Correcta-123!'), self.errores_del_login('incorrecta'))
