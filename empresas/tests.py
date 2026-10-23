from datetime import timedelta
from unittest import mock

from django.test import TestCase

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.db import DatabaseError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from usuarios.models import UserProfile
from .middleware import TenantMiddleware, _obtener_session_timeout_minutos
from .models import ConfiguracionSaaS, Empresa, SuscripcionEmpresa


class SessionTimeoutTests(TestCase):
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

# Create your tests here.
