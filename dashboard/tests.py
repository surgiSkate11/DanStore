from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

import re
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


class BotonRenovarEnInquilinosTests(TestCase):
	"""S2/S5: las listas de inquilinos ofrecen renovar por fila, solo al superadmin."""

	def setUp(self):
		self.plan = Plan.objects.create(nombre='Basico')
		self.superadmin = User.objects.create_superuser('super_inq', 'si@example.com', 'Clave-prueba-123')
		self.cerca, self.dueno_cerca = crear_empresa_con_dueno('cerca')
		self.lejos, _ = crear_empresa_con_dueno('lejos')
		self.sin_plan, _ = crear_empresa_con_dueno('sinplan')
		self.sin_suscripcion, _ = crear_empresa_con_dueno('sinsuscripcion')
		ahora = timezone.now()
		self.sub_cerca = self._suscripcion(self.cerca, self.plan, ahora + timedelta(days=3))
		self.sub_lejos = self._suscripcion(self.lejos, self.plan, ahora + timedelta(days=20))
		self.sub_sin_plan = self._suscripcion(self.sin_plan, None, ahora + timedelta(days=3))

	def _suscripcion(self, empresa, plan, vencimiento):
		return SuscripcionEmpresa.objects.create(
			empresa=empresa, plan=plan, tipo_plan='mensual',
			fecha_inicio=vencimiento - timedelta(days=30), fecha_vencimiento=vencimiento.replace(microsecond=0),
		)

	def _url_renovar(self, suscripcion):
		return reverse('saas_renovar_suscripcion', args=[suscripcion.id])

	def _fechas(self, suscripcion):
		s = SuscripcionEmpresa.objects.get(pk=suscripcion.pk)
		return s.fecha_inicio, s.fecha_vencimiento

	def _formulario_de(self, html, url):
		"""Devuelve el <form> cuyo action es `url`, o None."""
		for formulario in re.findall(r'<form\b.*?</form>', html, flags=re.S):
			if f'action="{url}"' in formulario:
				return formulario
		return None

	def _paginas(self):
		return [reverse('saas_empresas'), reverse('dashboard_saas')]

	def test_superadmin_ve_el_boton_dentro_de_la_ventana_con_post_y_csrf(self):
		self.client.force_login(self.superadmin)
		for pagina in self._paginas():
			with self.subTest(pagina=pagina):
				html = self.client.get(pagina).content.decode()
				formulario = self._formulario_de(html, self._url_renovar(self.sub_cerca))
				self.assertIsNotNone(formulario, 'falta el botón de renovar')
				self.assertRegex(formulario, r'(?i)method="POST"')
				self.assertIn('csrfmiddlewaretoken', formulario)

	def test_no_hay_boton_para_una_empresa_con_20_dias_restantes(self):
		self.client.force_login(self.superadmin)
		for pagina in self._paginas():
			with self.subTest(pagina=pagina):
				html = self.client.get(pagina).content.decode()
				self.assertIsNone(self._formulario_de(html, self._url_renovar(self.sub_lejos)))

	def test_no_hay_boton_para_una_suscripcion_sin_plan(self):
		self.client.force_login(self.superadmin)
		for pagina in self._paginas():
			with self.subTest(pagina=pagina):
				html = self.client.get(pagina).content.decode()
				self.assertIsNone(self._formulario_de(html, self._url_renovar(self.sub_sin_plan)))

	def test_empresa_sin_suscripcion_se_muestra_sin_error_y_sin_boton(self):
		self.client.force_login(self.superadmin)
		respuesta = self.client.get(reverse('saas_empresas'))
		self.assertEqual(respuesta.status_code, 200)
		html = respuesta.content.decode()
		self.assertIn('Sin suscripción', html)
		# Solo la empresa "cerca" tiene botón: ni la de sin suscripción ni otras.
		self.assertEqual(html.count('/renovar-suscripcion/'), 1)

	def test_dueno_no_puede_ver_las_listas_de_inquilinos(self):
		for pagina in self._paginas():
			with self.subTest(pagina=pagina):
				self.client.force_login(self.dueno_cerca)
				respuesta = self.client.get(pagina)
				self.assertEqual(respuesta.status_code, 403)
				self.assertNotIn('/renovar-suscripcion/', respuesta.content.decode())

	def test_dueno_no_renueva_ni_con_el_formulario_de_la_lista(self):
		antes = self._fechas(self.sub_cerca)
		self.client.force_login(self.dueno_cerca)
		respuesta = self.client.post(self._url_renovar(self.sub_cerca), {'next': reverse('saas_empresas')})
		self.assertIn(respuesta.status_code, (302, 403))
		self.assertEqual(self._fechas(self.sub_cerca), antes)

	def test_enviar_el_formulario_renueva_desde_el_vencimiento_y_vuelve_a_la_lista(self):
		inicio, vencimiento = self._fechas(self.sub_cerca)
		self.client.force_login(self.superadmin)
		for pagina in self._paginas():
			with self.subTest(pagina=pagina):
				SuscripcionEmpresa.objects.filter(pk=self.sub_cerca.pk).update(
					fecha_inicio=inicio, fecha_vencimiento=vencimiento)
				html = self.client.get(pagina).content.decode()
				formulario = self._formulario_de(html, self._url_renovar(self.sub_cerca))
				self.assertIn('name="next"', formulario)
				respuesta = self.client.post(self._url_renovar(self.sub_cerca), {'next': pagina}, follow=True)
				self.assertRedirects(respuesta, pagina)
				nuevo_inicio, nuevo_vencimiento = self._fechas(self.sub_cerca)
				self.assertEqual(nuevo_inicio, inicio)
				self.assertGreaterEqual(nuevo_vencimiento, vencimiento + timedelta(days=28))
				self.assertLessEqual(nuevo_vencimiento, vencimiento + timedelta(days=31))
				textos = [str(m) for m in get_messages(respuesta.wsgi_request)]
				self.assertTrue(any('renovada' in t and self.cerca.nombre in t for t in textos), textos)

	def test_next_externo_se_ignora(self):
		self.client.force_login(self.superadmin)
		respuesta = self.client.post(self._url_renovar(self.sub_cerca), {'next': 'https://malo.example.com/'})
		self.assertEqual(respuesta.status_code, 302)
		self.assertNotIn('malo.example.com', respuesta['Location'])

	def test_renovar_sin_next_conserva_el_destino_anterior(self):
		self.client.force_login(self.superadmin)
		respuesta = self.client.post(self._url_renovar(self.sub_cerca))
		self.assertEqual(
			respuesta['Location'],
			reverse('saas_listar_registros', args=['empresas', 'suscripcionempresa']))

	def test_renovar_fuera_de_ventana_desde_la_lista_no_cambia_nada(self):
		antes = self._fechas(self.sub_lejos)
		self.client.force_login(self.superadmin)
		self.client.post(self._url_renovar(self.sub_lejos), {'next': reverse('saas_empresas')})
		self.assertEqual(self._fechas(self.sub_lejos), antes)


class FechasSuscripcionSaasTests(TestCase):
	"""S6: el módulo de base de datos calcula las fechas solo y no deja editarlas."""

	def setUp(self):
		self.superadmin = User.objects.create_superuser('super_fechas', 'sf@example.com', 'Clave-prueba-123')
		self.plan = Plan.objects.create(nombre='Basico')
		self.empresa = Empresa.objects.create(nombre='Fechas Saas', slug='fechas-saas')
		self.client.force_login(self.superadmin)

	def _url_crear(self):
		return reverse('saas_crear_registro', args=['empresas', 'suscripcionempresa'])

	def _url_editar(self, sub):
		return reverse('saas_editar_registro', args=['empresas', 'suscripcionempresa', sub.id])

	def _existente(self):
		return SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=(timezone.now() - timedelta(days=10)).replace(microsecond=0),
			fecha_vencimiento=(timezone.now() + timedelta(days=20)).replace(microsecond=0))

	def _fechas(self, sub):
		s = SuscripcionEmpresa.objects.get(pk=sub.pk)
		return s.fecha_inicio, s.fecha_vencimiento

	def test_crear_calcula_las_fechas_segun_tipo_plan_e_ignora_las_enviadas(self):
		respuesta = self.client.post(self._url_crear(), {
			'empresa': self.empresa.id, 'plan': self.plan.id, 'tipo_plan': 'anual',
			'fecha_inicio': '2001-01-01 00:00:00', 'fecha_vencimiento': '2001-02-01 00:00:00',
		})
		self.assertEqual(respuesta.status_code, 302)
		sub = SuscripcionEmpresa.objects.get(empresa=self.empresa)
		self.assertGreater(sub.fecha_inicio, timezone.now() - timedelta(minutes=5))
		self.assertTrue(timedelta(days=365) <= sub.fecha_vencimiento - sub.fecha_inicio <= timedelta(days=366))

	def test_formulario_de_edicion_no_tiene_las_fechas_y_avisa_de_la_proxima_renovacion(self):
		sub = self._existente()
		respuesta = self.client.get(self._url_editar(sub))
		campos = respuesta.context['form'].fields
		self.assertNotIn('fecha_inicio', campos)
		self.assertNotIn('fecha_vencimiento', campos)
		ayuda = f"{campos['plan'].help_text} {campos['tipo_plan'].help_text}"
		self.assertIn('próxima renovación', ayuda)

	def test_editar_ignora_fechas_manipuladas(self):
		sub = self._existente()
		antes = self._fechas(sub)
		self.client.post(self._url_editar(sub), {
			'empresa': self.empresa.id, 'plan': self.plan.id, 'tipo_plan': 'mensual',
			'fecha_inicio': '2001-01-01 00:00:00', 'fecha_vencimiento': '2099-01-01 00:00:00',
		})
		self.assertEqual(self._fechas(sub), antes)
