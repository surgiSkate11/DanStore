from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from datetime import timedelta

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.utils import timezone

from empresas.models import Empresa, Plan, SuscripcionEmpresa
from empresas.testing import crear_empresa_con_dueno


class XFrameOptionsTests(TestCase):
    def test_paginas_del_sitio_no_se_pueden_embeber(self):
        respuesta = self.client.get(reverse('login'))
        self.assertEqual(respuesta['X-Frame-Options'], 'DENY')

    def test_tienda_publica_se_puede_embeber_en_la_vista_previa_propia(self):
        empresa = Empresa.objects.create(nombre='Panaderia', slug='panaderia')
        respuesta = self.client.get(reverse('tienda_publica', args=[empresa.slug]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['X-Frame-Options'], 'SAMEORIGIN')


@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
)
class RedireccionHttpsTests(TestCase):
    def test_http_redirige_a_https(self):
        respuesta = self.client.get('/login/')
        self.assertEqual(respuesta.status_code, 301)
        self.assertEqual(respuesta['Location'], 'https://testserver/login/')

    def test_peticion_https_del_proxy_no_redirige(self):
        respuesta = self.client.get('/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(respuesta.status_code, 200)

    def test_healthcheck_de_railway_en_la_raiz_no_redirige_a_https(self):
        with self.settings(SECURE_REDIRECT_EXEMPT=settings.SECURE_REDIRECT_EXEMPT):
            respuesta = self.client.get('/')
        self.assertNotEqual(respuesta.status_code, 301)


class RenovarSuscripcionTests(TestCase):
	"""S3/S5: solo el superadmin renueva, por POST y dentro de la ventana de 7 días."""

	def setUp(self):
		self.empresa, self.dueno = crear_empresa_con_dueno('renueva')
		self.plan = Plan.objects.create(nombre='Basico')
		self.inicio = (timezone.now() - timedelta(days=27)).replace(microsecond=0)
		self.vencimiento = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
		self.suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=self.inicio, fecha_vencimiento=self.vencimiento,
		)
		self.url = reverse('saas_renovar_suscripcion', args=[self.suscripcion.id])
		self.superadmin = User.objects.create_superuser('super', 's@example.com', 'Clave-prueba-123')

	def _fechas(self):
		s = SuscripcionEmpresa.objects.get(pk=self.suscripcion.pk)
		return s.fecha_inicio, s.fecha_vencimiento

	def _mover_vencimiento(self, delta):
		SuscripcionEmpresa.objects.filter(pk=self.suscripcion.pk).update(
			fecha_vencimiento=timezone.now() + delta)
		return self._fechas()

	def test_superadmin_renueva_3_dias_antes_sumando_desde_el_vencimiento(self):
		self.client.force_login(self.superadmin)
		respuesta = self.client.post(self.url)
		self.assertEqual(respuesta.status_code, 302)
		inicio, vencimiento = self._fechas()
		# Mensual: vencimiento anterior + 1 mes (misma hora), inicio intacto.
		self.assertEqual(inicio, self.inicio)
		self.assertGreaterEqual(vencimiento, self.vencimiento + timedelta(days=28))
		self.assertLessEqual(vencimiento, self.vencimiento + timedelta(days=31))
		self.assertEqual(vencimiento.time(), self.vencimiento.time())

	def test_renovar_8_dias_antes_se_rechaza_con_mensaje_y_no_cambia_nada(self):
		antes = self._mover_vencimiento(timedelta(days=8))
		self.client.force_login(self.superadmin)
		respuesta = self.client.post(self.url, follow=True)
		self.assertEqual(self._fechas(), antes)
		textos = [str(m) for m in get_messages(respuesta.wsgi_request)]
		self.assertTrue(any('7 días' in t and 'no puede renovarse' in t for t in textos), textos)

	def test_renovar_dentro_de_la_ventana_si_se_permite(self):
		antes = self._mover_vencimiento(timedelta(days=7) - timedelta(minutes=1))
		self.client.force_login(self.superadmin)
		self.client.post(self.url)
		self.assertGreater(self._fechas()[1], antes[1])

	def test_renovar_una_vencida_si_se_permite(self):
		antes = self._mover_vencimiento(-timedelta(days=2))
		self.client.force_login(self.superadmin)
		self.client.post(self.url)
		self.assertGreater(self._fechas()[1], antes[1] + timedelta(days=30))

	def test_dueno_de_empresa_no_puede_renovar(self):
		antes = self._fechas()
		self.client.force_login(self.dueno)
		respuesta = self.client.post(self.url)
		self.assertIn(respuesta.status_code, (302, 403))
		self.assertEqual(self._fechas(), antes)

	def test_dueno_de_una_suscripcion_vencida_tampoco_puede_renovar(self):
		antes = self._mover_vencimiento(-timedelta(days=2))
		self.client.force_login(self.dueno)
		respuesta = self.client.post(self.url)
		self.assertIn(respuesta.status_code, (302, 403))
		self.assertEqual(self._fechas(), antes)

	def test_get_no_renueva_ni_siquiera_al_superadmin(self):
		antes = self._fechas()
		self.client.force_login(self.superadmin)
		respuesta = self.client.get(self.url)
		self.assertEqual(respuesta.status_code, 403)
		self.assertEqual(self._fechas(), antes)

	def test_anonimo_no_renueva(self):
		antes = self._fechas()
		respuesta = self.client.post(self.url)
		self.assertEqual(respuesta.status_code, 302)
		self.assertEqual(self._fechas(), antes)

	def test_suscripcion_sin_plan_no_se_renueva(self):
		SuscripcionEmpresa.objects.filter(pk=self.suscripcion.pk).update(plan=None)
		antes = self._fechas()
		self.client.force_login(self.superadmin)
		self.client.post(self.url)
		self.assertEqual(self._fechas(), antes)

