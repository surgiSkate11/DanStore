from datetime import timedelta
from unittest import mock

from django.test import TestCase

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.db import DatabaseError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from usuarios.models import UserProfile
from .middleware import TenantMiddleware, _obtener_session_timeout_minutos
from .models import ConfiguracionSaaS, Empresa, SuscripcionEmpresa


class SessionTimeoutTests(TestCase):
	def setUp(self):
		# Otras pruebas dejan el timeout de sesión cacheado.
		cache.clear()
		self.addCleanup(cache.clear)

	def test_timeout_global_se_aplica_a_usuario_de_empresa(self):
		empresa = Empresa.objects.create(nombre='Empresa A', slug='empresa-a')
		usuario = User.objects.create_user(username='owner_a', password='Correcta-123!')
		UserProfile.objects.create(user=usuario, empresa=empresa, rol='owner')
		ConfiguracionSaaS.objects.create(id=1, session_timeout=30)

		self.assertEqual(_obtener_session_timeout_minutos(), 30)

		request = RequestFactory().get('/dashboard/')
		request.user = usuario
		request.session = SessionStore()
		TenantMiddleware(lambda request: None).process_request(request)

		self.assertEqual(request.session.get_expiry_age(), 30 * 60)


class SuspensionMiddlewareTests(TestCase):
	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Vencida', slug='vencida')
		SuscripcionEmpresa.objects.create(
			empresa=self.empresa,
			fecha_vencimiento=timezone.now() - timedelta(days=1),
		)
		self.usuario = User.objects.create_user(username='owner_vencida', password='Correcta-123!')
		UserProfile.objects.create(user=self.usuario, empresa=self.empresa, rol='owner')
		self.client.force_login(self.usuario)

	def test_cuenta_vencida_es_redirigida_a_cuenta_suspendida(self):
		respuesta = self.client.get('/productos/')
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_cuenta_vencida_sigue_bloqueada_si_falla_la_duracion_de_sesion(self):
		with mock.patch(
			'empresas.middleware._obtener_session_timeout_minutos',
			side_effect=DatabaseError('bd caida'),
		), self.assertLogs('empresas.middleware', level='ERROR'):
			respuesta = self.client.get('/productos/')
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_error_inesperado_al_leer_el_perfil_no_se_esconde(self):
		request = RequestFactory().get('/productos/')
		request.user = self.usuario
		request.session = SessionStore()
		with mock.patch.object(UserProfile.objects, 'select_related', side_effect=RuntimeError('fallo')):
			with self.assertRaises(RuntimeError):
				TenantMiddleware(lambda request: None).process_request(request)

	def test_empresa_desactivada_es_redirigida_aunque_la_suscripcion_este_al_dia(self):
		self.empresa.suscripcion.fecha_vencimiento = timezone.now() + timedelta(days=30)
		self.empresa.suscripcion.save()
		self.empresa.activa = False
		self.empresa.save()
		respuesta = self.client.get('/productos/')
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_cuenta_al_dia_no_es_redirigida(self):
		self.empresa.suscripcion.fecha_vencimiento = timezone.now() + timedelta(days=30)
		self.empresa.suscripcion.save()
		request = RequestFactory().get('/productos/')
		request.user = self.usuario
		request.session = SessionStore()
		self.assertIsNone(TenantMiddleware(lambda request: None).process_request(request))
		self.assertEqual(request.empresa, self.empresa)


class SuscripcionEmpresaTests(TestCase):
	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Empresa suscrita', slug='empresa-suscrita')

	def test_dias_restantes_no_redondea_a_cero_una_fecha_futura(self):
		suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa,
			fecha_inicio=timezone.now() - timedelta(days=30),
			fecha_vencimiento=timezone.now() + timedelta(hours=1),
		)

		self.assertEqual(suscripcion.dias_restantes(), 1)
		self.assertFalse(suscripcion.puede_renovarse)

	def test_suscripcion_vencida_muestra_cien_por_ciento(self):
		suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa,
			fecha_inicio=timezone.now() - timedelta(days=31),
			fecha_vencimiento=timezone.now() - timedelta(seconds=1),
		)

		self.assertEqual(suscripcion.porcentaje_consumido(), 100)
		self.assertTrue(suscripcion.puede_renovarse)

# Create your tests here.


class PorcentajeConsumidoTests(TestCase):
	"""S1: la barra se calcula con segundos y marca 100 % al vencer."""

	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Barra', slug='barra')
		self.inicio = timezone.now().replace(microsecond=0)
		self.vencimiento = self.inicio + timedelta(days=30)
		self.suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa,
			fecha_inicio=self.inicio,
			fecha_vencimiento=self.vencimiento,
		)

	def _porcentaje_en(self, ahora):
		with mock.patch('empresas.models.timezone.now', return_value=ahora):
			return self.suscripcion.porcentaje_consumido()

	def test_ultima_hora_antes_de_vencer_marca_99_o_mas(self):
		porcentaje = self._porcentaje_en(self.vencimiento - timedelta(hours=1))
		self.assertGreaterEqual(porcentaje, 99)
		self.assertLess(porcentaje, 100)

	def test_ultimo_segundo_antes_de_vencer_no_llega_a_100_antes_de_tiempo(self):
		self.assertEqual(self._porcentaje_en(self.vencimiento - timedelta(seconds=1)), 99)

	def test_mitad_del_periodo_marca_50(self):
		self.assertEqual(self._porcentaje_en(self.inicio + timedelta(days=15)), 50)

	def test_un_dia_y_medio_consumido_usa_segundos_no_dias_enteros(self):
		# 36 h de 720 h = 5 %; con días truncados serían 1/30 = 3 %.
		self.assertEqual(self._porcentaje_en(self.inicio + timedelta(hours=36)), 5)

	def test_al_iniciar_marca_0(self):
		self.assertEqual(self._porcentaje_en(self.inicio), 0)

	def test_vencida_marca_100(self):
		self.assertEqual(self._porcentaje_en(self.vencimiento), 100)
		self.assertEqual(self._porcentaje_en(self.vencimiento + timedelta(days=5)), 100)

	def test_quedando_cero_dias_marca_100(self):
		with mock.patch('empresas.models.timezone.now', return_value=self.vencimiento):
			self.assertEqual(self.suscripcion.dias_restantes(), 0)
			self.assertEqual(self.suscripcion.porcentaje_consumido(), 100)

	def test_periodo_sin_duracion_marca_100(self):
		self.suscripcion.fecha_vencimiento = self.inicio
		self.assertEqual(self._porcentaje_en(self.inicio - timedelta(hours=1)), 100)

	def test_color_de_la_barra_sigue_los_umbrales(self):
		with mock.patch('empresas.models.timezone.now', return_value=self.vencimiento - timedelta(hours=1)):
			self.assertEqual(self.suscripcion.estado_color(), 'danger')
		with mock.patch('empresas.models.timezone.now', return_value=self.inicio + timedelta(days=15)):
			self.assertEqual(self.suscripcion.estado_color(), 'success')

