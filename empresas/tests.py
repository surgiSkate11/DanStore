from datetime import timedelta
from unittest import mock

from django.test import TestCase

from django.contrib.auth.models import User
from django.contrib import admin
from django.contrib.sessions.backends.db import SessionStore
from django.core.cache import cache
from django.db import DatabaseError
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from usuarios.models import UserProfile
from .middleware import TenantMiddleware, _obtener_session_timeout_minutos
from .models import ConfiguracionSaaS, Empresa, Plan, SuscripcionEmpresa


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
		# Con 1 h restante ya está dentro de la ventana de 7 días (S3).
		self.assertTrue(suscripcion.puede_renovarse)

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


class VentanaRenovacionTests(TestCase):
	"""S3: una sola regla `puede_renovarse` (vencida o a 7 días o menos de vencer)."""

	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Ventana', slug='ventana')
		self.ahora = timezone.now().replace(microsecond=0)
		self.plan = Plan.objects.create(nombre='Basico')

	def _suscripcion(self, vence_en, tipo_plan='mensual'):
		return SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan=tipo_plan,
			fecha_inicio=self.ahora - timedelta(days=23),
			fecha_vencimiento=self.ahora + vence_en,
		)

	def _puede(self, suscripcion):
		with mock.patch('empresas.models.timezone.now', return_value=self.ahora):
			return suscripcion.puede_renovarse

	def test_faltando_8_dias_no_se_puede_renovar(self):
		self.assertFalse(self._puede(self._suscripcion(timedelta(days=8))))

	def test_faltando_mas_de_7_dias_por_un_segundo_no_se_puede_renovar(self):
		self.assertFalse(self._puede(self._suscripcion(timedelta(days=7, seconds=1))))

	def test_faltando_exactamente_7_dias_se_puede_renovar(self):
		self.assertTrue(self._puede(self._suscripcion(timedelta(days=7))))

	def test_faltando_3_dias_se_puede_renovar(self):
		self.assertTrue(self._puede(self._suscripcion(timedelta(days=3))))

	def test_vencida_se_puede_renovar(self):
		suscripcion = self._suscripcion(-timedelta(seconds=1))
		self.assertTrue(self._puede(suscripcion))
		suscripcion.fecha_vencimiento = self.ahora - timedelta(days=40)
		self.assertTrue(self._puede(suscripcion))

	def test_renovar_vigente_suma_el_periodo_desde_el_vencimiento_sin_tocar_el_inicio(self):
		from datetime import datetime, timezone as tz
		vencimiento = datetime(2027, 3, 10, 15, 30, tzinfo=tz.utc)
		inicio = datetime(2027, 2, 10, 15, 30, tzinfo=tz.utc)
		ahora = vencimiento - timedelta(days=3)
		suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=inicio, fecha_vencimiento=vencimiento,
		)
		with mock.patch('empresas.models.timezone.now', return_value=ahora):
			estaba_vencida = suscripcion.renovar()
		suscripcion.refresh_from_db()
		self.assertFalse(estaba_vencida)
		self.assertEqual(suscripcion.fecha_vencimiento, datetime(2027, 4, 10, 15, 30, tzinfo=tz.utc))
		self.assertEqual(suscripcion.fecha_inicio, inicio)


class BloqueoPorVencimientoTests(TestCase):
	"""S4: se bloquea solo cuando fecha_vencimiento <= ahora."""

	def _usuario_con_vencimiento(self, delta):
		empresa = Empresa.objects.create(nombre='Bloqueo', slug='bloqueo')
		SuscripcionEmpresa.objects.create(empresa=empresa, fecha_vencimiento=timezone.now() + delta)
		usuario = User.objects.create_user(username='owner_bloqueo', password='Correcta-123!')
		UserProfile.objects.create(user=usuario, empresa=empresa, rol='owner')
		self.client.force_login(usuario)
		return empresa

	def test_con_una_hora_restante_conserva_el_acceso(self):
		self._usuario_con_vencimiento(timedelta(hours=1))
		respuesta = self.client.get('/productos/')
		self.assertNotEqual(respuesta.status_code, 302, respuesta.get('Location'))
		self.assertEqual(respuesta.status_code, 200)

	def test_vencida_hace_un_segundo_es_redirigida_a_cuenta_suspendida(self):
		self._usuario_con_vencimiento(-timedelta(seconds=1))
		respuesta = self.client.get('/productos/')
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_acceso_activo_de_la_empresa_sigue_la_misma_regla(self):
		empresa = self._usuario_con_vencimiento(timedelta(hours=1))
		self.assertTrue(empresa.acceso_activo)
		SuscripcionEmpresa.objects.filter(empresa=empresa).update(
			fecha_vencimiento=timezone.now() - timedelta(seconds=1))
		empresa = Empresa.objects.get(pk=empresa.pk)
		self.assertFalse(empresa.acceso_activo)


class AccionAdminRenovarTests(TestCase):
	"""S3: la acción del admin de Django usa la misma regla que la vista y el modelo."""

	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Admin', slug='admin-renueva')
		self.plan = Plan.objects.create(nombre='Basico')
		self.suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=timezone.now() - timedelta(days=20),
			fecha_vencimiento=timezone.now() + timedelta(days=10),
		)
		self.superadmin = User.objects.create_superuser('super_admin', 'a@example.com', 'Clave-prueba-123')

	def _ejecutar_accion(self):
		"""Ejecuta la acción del admin directamente (el sitio admin exige OTP)."""
		modelo_admin = admin.site._registry[SuscripcionEmpresa]
		request = RequestFactory().post('/')
		request.user = self.superadmin
		mensajes = []
		with mock.patch.object(
			modelo_admin, 'message_user',
			side_effect=lambda req, texto, level=None: mensajes.append(str(texto)),
		):
			modelo_admin.renovar_suscripciones(
				request, SuscripcionEmpresa.objects.filter(pk=self.suscripcion.pk))
		return mensajes

	def _vencimiento(self):
		return SuscripcionEmpresa.objects.get(pk=self.suscripcion.pk).fecha_vencimiento

	def test_fuera_de_la_ventana_no_renueva(self):
		antes = self._vencimiento()
		textos = self._ejecutar_accion()
		self.assertEqual(self._vencimiento(), antes)
		self.assertTrue(any('7 días' in t and 'no puede renovarse' in t for t in textos), textos)

	def test_dentro_de_la_ventana_renueva_desde_el_vencimiento(self):
		SuscripcionEmpresa.objects.filter(pk=self.suscripcion.pk).update(
			fecha_vencimiento=timezone.now() + timedelta(days=3))
		antes = self._vencimiento()
		self._ejecutar_accion()
		self.assertGreaterEqual(self._vencimiento(), antes + timedelta(days=28))



class PagoExitosoNoRenuevaTests(TestCase):
	"""T7 (L12/L13): abrir `pago_exitoso` no verifica ningún pago, así que no puede renovar."""

	def setUp(self):
		from .testing import crear_empresa_con_dueno
		self.empresa, self.dueno = crear_empresa_con_dueno('pago-exitoso', suscripcion=False)
		self.plan = Plan.objects.create(nombre='Pro')
		self.client.force_login(self.dueno)

	def _suscripcion(self, vence_en):
		ahora = timezone.now().replace(microsecond=0)
		return SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=ahora - timedelta(days=5), fecha_vencimiento=ahora + vence_en,
		)

	def _url(self, plan_id=None, tipo_plan='anual'):
		return reverse('pago_exitoso', args=[plan_id or self.plan.id, tipo_plan])

	def _estado(self):
		suscripcion = SuscripcionEmpresa.objects.get(empresa=self.empresa)
		self.empresa.refresh_from_db()
		return (suscripcion.fecha_inicio, suscripcion.fecha_vencimiento, suscripcion.plan_id,
				suscripcion.tipo_plan, self.empresa.activa)

	def test_suscripcion_vigente_no_cambia_y_redirige_al_dashboard(self):
		self._suscripcion(timedelta(days=25))
		antes = self._estado()
		respuesta = self.client.get(self._url(), follow=False)
		self.assertRedirects(respuesta, reverse('dashboard_router'), fetch_redirect_response=False)
		self.assertEqual(self._estado(), antes)

	def test_suscripcion_vigente_con_otro_plan_y_tipo_no_cambia_plan_ni_tipo(self):
		self._suscripcion(timedelta(days=25))
		otro = Plan.objects.create(nombre='Premium')
		antes = self._estado()
		self.client.get(self._url(plan_id=otro.id, tipo_plan='anual'))
		self.assertEqual(self._estado(), antes)

	def test_suscripcion_vencida_sigue_bloqueada(self):
		self._suscripcion(-timedelta(days=2))
		antes = self._estado()
		respuesta = self.client.get(self._url())
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)
		self.assertEqual(self._estado(), antes)
		protegida = self.client.get('/productos/')
		self.assertRedirects(protegida, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_empresa_desactivada_sigue_desactivada(self):
		self._suscripcion(timedelta(days=25))
		Empresa.objects.filter(pk=self.empresa.pk).update(activa=False)
		antes = self._estado()
		respuesta = self.client.get(self._url())
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)
		self.assertEqual(self._estado(), antes)
		self.assertFalse(self._estado()[4])

	def test_sin_suscripcion_no_crea_ninguna(self):
		respuesta = self.client.get(self._url())
		self.assertEqual(respuesta.status_code, 302)
		self.assertFalse(SuscripcionEmpresa.objects.filter(empresa=self.empresa).exists())

	def test_muestra_mensaje_de_pago_recibido_en_espanol(self):
		self._suscripcion(timedelta(days=25))
		respuesta = self.client.get(self._url())
		textos = [str(m) for m in respuesta.wsgi_request._messages]
		self.assertEqual(len(textos), 1, textos)
		self.assertIn('Recibimos tu pago', textos[0])
		self.assertIn('24 horas', textos[0])
		self.assertIn('soporte', textos[0])
		self.assertNotIn('renovada por', textos[0])

	def test_registra_advertencia_con_empresa_plan_y_tipo(self):
		self._suscripcion(timedelta(days=25))
		with self.assertLogs('empresas.views', level='WARNING') as capturado:
			self.client.get(self._url(tipo_plan='mensual'))
		linea = '\n'.join(capturado.output)
		self.assertIn(f'empresa_id={self.empresa.id}', linea)
		self.assertIn(f'plan_id={self.plan.id}', linea)
		self.assertIn('tipo_plan=mensual', linea)

	def test_tipo_plan_invalido_da_404_y_no_cambia_nada(self):
		self._suscripcion(timedelta(days=25))
		antes = self._estado()
		respuesta = self.client.get(self._url(tipo_plan='semanal'))
		self.assertEqual(respuesta.status_code, 404)
		self.assertEqual(self._estado(), antes)

	def test_plan_inexistente_da_404_y_no_cambia_nada(self):
		self._suscripcion(timedelta(days=25))
		antes = self._estado()
		respuesta = self.client.get(self._url(plan_id=999999))
		self.assertEqual(respuesta.status_code, 404)
		self.assertEqual(self._estado(), antes)

	def test_plan_inexistente_sin_suscripcion_no_crea_ninguna(self):
		respuesta = self.client.get(self._url(plan_id=999999))
		self.assertEqual(respuesta.status_code, 404)
		self.assertFalse(SuscripcionEmpresa.objects.filter(empresa=self.empresa).exists())

	def test_anonimo_es_redirigido_al_login_sin_cambios(self):
		self._suscripcion(timedelta(days=25))
		antes = self._estado()
		self.client.logout()
		respuesta = self.client.get(self._url())
		self.assertEqual(respuesta.status_code, 302)
		self.assertIn('login', respuesta['Location'])
		self.assertEqual(self._estado(), antes)


class AdminSuscripcionFechasTests(TestCase):
	"""S6: en el admin de Django las fechas se calculan solas y no se pueden editar.

	El sitio admin exige OTP, así que se prueban las piezas del ModelAdmin directamente
	(`save_model`, `get_readonly_fields`, `get_form`) desde `admin.site._registry`.
	"""

	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='Fechas', slug='fechas-admin')
		self.plan = Plan.objects.create(nombre='Basico')
		self.superadmin = User.objects.create_superuser('super_fechas', 'f@example.com', 'Clave-prueba-123')
		self.modelo_admin = admin.site._registry[SuscripcionEmpresa]
		self.request = RequestFactory().post('/')
		self.request.user = self.superadmin

	def _crear_desde_admin(self, tipo_plan):
		obj = SuscripcionEmpresa(empresa=self.empresa, plan=self.plan, tipo_plan=tipo_plan)
		antes = timezone.now()
		self.modelo_admin.save_model(self.request, obj, None, change=False)
		despues = timezone.now()
		return SuscripcionEmpresa.objects.get(pk=obj.pk), antes, despues

	def test_crear_mensual_calcula_inicio_y_vencimiento(self):
		sub, antes, despues = self._crear_desde_admin('mensual')
		self.assertTrue(antes <= sub.fecha_inicio <= despues)
		self.assertTrue(timedelta(days=28) <= sub.fecha_vencimiento - sub.fecha_inicio <= timedelta(days=31))
		self.assertEqual(sub.fecha_vencimiento.time(), sub.fecha_inicio.time())

	def test_crear_anual_calcula_un_ano(self):
		sub, antes, despues = self._crear_desde_admin('anual')
		self.assertTrue(antes <= sub.fecha_inicio <= despues)
		self.assertTrue(timedelta(days=365) <= sub.fecha_vencimiento - sub.fecha_inicio <= timedelta(days=366))
		self.assertEqual(sub.fecha_vencimiento.year, sub.fecha_inicio.year + 1)

	def test_crear_ignora_fechas_que_traiga_el_objeto(self):
		obj = SuscripcionEmpresa(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=timezone.now() - timedelta(days=400),
			fecha_vencimiento=timezone.now() - timedelta(days=370),
		)
		self.modelo_admin.save_model(self.request, obj, None, change=False)
		sub = SuscripcionEmpresa.objects.get(pk=obj.pk)
		self.assertGreater(sub.fecha_vencimiento, timezone.now() + timedelta(days=27))
		self.assertGreater(sub.fecha_inicio, timezone.now() - timedelta(minutes=5))

	def test_fechas_son_de_solo_lectura_al_agregar_y_al_cambiar(self):
		existente = SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=timezone.now(), fecha_vencimiento=timezone.now() + timedelta(days=30))
		for obj in (None, existente):
			with self.subTest(obj=obj):
				solo_lectura = self.modelo_admin.get_readonly_fields(self.request, obj)
				self.assertIn('fecha_inicio', solo_lectura)
				self.assertIn('fecha_vencimiento', solo_lectura)
				formulario = self.modelo_admin.get_form(self.request, obj, fields=None)
				self.assertNotIn('fecha_inicio', formulario.base_fields)
				self.assertNotIn('fecha_vencimiento', formulario.base_fields)

	def test_cambiar_tipo_de_plan_no_recalcula_las_fechas(self):
		sub, _, _ = self._crear_desde_admin('mensual')
		inicio, vencimiento = sub.fecha_inicio, sub.fecha_vencimiento
		sub.tipo_plan = 'anual'
		self.modelo_admin.save_model(self.request, sub, None, change=True)
		sub = SuscripcionEmpresa.objects.get(pk=sub.pk)
		self.assertEqual(sub.tipo_plan, 'anual')
		self.assertEqual((sub.fecha_inicio, sub.fecha_vencimiento), (inicio, vencimiento))

	def test_el_admin_explica_que_el_cambio_aplica_en_la_proxima_renovacion(self):
		descripciones = ' '.join(
			str(opciones.get('description', ''))
			for _, opciones in self.modelo_admin.get_fieldsets(self.request, None))
		self.assertIn('próxima renovación', descripciones)
		self.assertIn('automáticamente', descripciones)


class AccionAdminSoloSuperusuarioTests(TestCase):
	"""M1 (L15): la acción de renovar del admin solo la puede ejecutar un superusuario."""

	def setUp(self):
		self.empresa = Empresa.objects.create(nombre='M1', slug='m1-admin')
		self.plan = Plan.objects.create(nombre='Basico')
		self.suscripcion = SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=timezone.now() - timedelta(days=28),
			fecha_vencimiento=timezone.now() + timedelta(days=2),
		)
		self.modelo_admin = admin.site._registry[SuscripcionEmpresa]

	def _estado(self):
		s = SuscripcionEmpresa.objects.get(pk=self.suscripcion.pk)
		return s.fecha_inicio, s.fecha_vencimiento, s.tipo_plan, s.plan_id

	def _ejecutar(self, usuario):
		request = RequestFactory().post('/')
		request.user = usuario
		mensajes = []
		with mock.patch.object(
			self.modelo_admin, 'message_user',
			side_effect=lambda req, texto, level=None: mensajes.append((str(texto), level)),
		):
			self.modelo_admin.renovar_suscripciones(
				request, SuscripcionEmpresa.objects.filter(pk=self.suscripcion.pk))
		return mensajes

	def test_personal_sin_superusuario_recibe_error_y_no_cambia_nada(self):
		personal = User.objects.create_user('staff_m1', 'st@example.com', 'Clave-prueba-123', is_staff=True)
		antes = self._estado()
		mensajes = self._ejecutar(personal)
		self.assertEqual(self._estado(), antes)
		self.assertEqual(len(mensajes), 1, mensajes)
		texto, nivel = mensajes[0]
		self.assertIn('superadministrador', texto)
		self.assertEqual(nivel, 'ERROR')

	def test_la_accion_no_se_ofrece_al_personal_sin_superusuario(self):
		personal = User.objects.create_user('staff_m1b', 'stb@example.com', 'Clave-prueba-123', is_staff=True)
		request = RequestFactory().get('/')
		request.user = personal
		self.assertNotIn('renovar_suscripciones', self.modelo_admin.get_actions(request))

	def test_superusuario_si_renueva(self):
		superusuario = User.objects.create_superuser('super_m1', 'sm@example.com', 'Clave-prueba-123')
		antes = self._estado()
		self._ejecutar(superusuario)
		self.assertGreaterEqual(self._estado()[1], antes[1] + timedelta(days=28))
		request = RequestFactory().get('/')
		request.user = superusuario
		self.assertIn('renovar_suscripciones', self.modelo_admin.get_actions(request))



class EmpresaSinSuscripcionTests(TestCase):
	"""S7 (defensa): una empresa sin suscripción se trata como suspendida (no hay acceso gratis)."""

	def setUp(self):
		from .testing import crear_empresa_con_dueno
		self.empresa, self.dueno = crear_empresa_con_dueno('sin-suscripcion', suscripcion=False)
		self.plan = Plan.objects.create(nombre='Pro')

	def _suscribir(self, vence_en):
		ahora = timezone.now().replace(microsecond=0)
		return SuscripcionEmpresa.objects.create(
			empresa=self.empresa, plan=self.plan, tipo_plan='mensual',
			fecha_inicio=ahora - timedelta(days=5), fecha_vencimiento=ahora + vence_en,
		)

	def test_acceso_activo_es_falso_sin_suscripcion(self):
		self.assertFalse(Empresa.objects.get(pk=self.empresa.pk).acceso_activo)

	def test_acceso_activo_es_verdadero_con_suscripcion_vigente(self):
		self._suscribir(timedelta(days=10))
		self.assertTrue(Empresa.objects.get(pk=self.empresa.pk).acceso_activo)

	def test_usuario_de_empresa_sin_suscripcion_va_a_cuenta_suspendida(self):
		self.client.force_login(self.dueno)
		respuesta = self.client.get(reverse('dashboard_router'))
		self.assertRedirects(respuesta, reverse('cuenta_suspendida'), fetch_redirect_response=False)

	def test_pagina_de_cuenta_suspendida_carga_sin_suscripcion(self):
		self.client.force_login(self.dueno)
		respuesta = self.client.get(reverse('cuenta_suspendida'))
		self.assertEqual(respuesta.status_code, 200)

	def test_usuario_de_empresa_con_suscripcion_vigente_no_es_bloqueado(self):
		self._suscribir(timedelta(days=10))
		self.client.force_login(self.dueno)
		respuesta = self.client.get(reverse('dashboard_router'))
		self.assertNotEqual(respuesta.get('Location'), reverse('cuenta_suspendida'))

	def test_superadmin_no_se_ve_afectado(self):
		superadmin = User.objects.create_superuser('super_sin_sub', 'ss@example.com', 'Clave-prueba-123')
		self.client.force_login(superadmin)
		respuesta = self.client.get(reverse('dashboard_router'))
		self.assertRedirects(respuesta, reverse('dashboard_saas'), fetch_redirect_response=False)


class PagoExitosoSuperadminTests(TestCase):
	"""B2 (L15): un superadmin sin empresa que abre `pago_exitoso` no debe dar 500."""

	def test_superadmin_sin_empresa_vuelve_al_router_con_mensaje(self):
		from django.contrib.messages import get_messages
		plan = Plan.objects.create(nombre='Pro')
		superadmin = User.objects.create_superuser('super_pago', 'sp@example.com', 'Clave-prueba-123')
		self.client.force_login(superadmin)
		respuesta = self.client.get(reverse('pago_exitoso', args=[plan.id, 'mensual']))
		self.assertRedirects(respuesta, reverse('dashboard_router'), fetch_redirect_response=False)
		mensajes = [str(m) for m in get_messages(respuesta.wsgi_request)]
		self.assertTrue(any('empresa' in m.lower() for m in mensajes), mensajes)


class AdminNoBorraEmpresasNiSuscripcionesTests(TestCase):
	"""S7: el admin de Django no permite borrar Empresa ni SuscripcionEmpresa.

	El sitio admin exige OTP, así que se prueban los ModelAdmin directamente.
	"""

	def setUp(self):
		self.superusuario = User.objects.create_superuser('super_adm_del', 'sad@example.com', 'Clave-prueba-123')
		self.request = RequestFactory().get('/')
		self.request.user = self.superusuario

	def test_has_delete_permission_es_falso_para_empresa_y_suscripcion(self):
		for modelo in (Empresa, SuscripcionEmpresa):
			modelo_admin = admin.site._registry[modelo]
			self.assertFalse(modelo_admin.has_delete_permission(self.request), modelo.__name__)
			self.assertFalse(modelo_admin.has_delete_permission(self.request, obj=modelo()), modelo.__name__)

	def test_no_se_ofrece_la_accion_de_borrado_masivo(self):
		for modelo in (Empresa, SuscripcionEmpresa):
			acciones = admin.site._registry[modelo].get_actions(self.request)
			self.assertNotIn('delete_selected', acciones, modelo.__name__)

	def test_otros_modelos_conservan_el_borrado(self):
		modelo_admin = admin.site._registry[Plan]
		self.assertTrue(modelo_admin.has_delete_permission(self.request))
		self.assertIn('delete_selected', modelo_admin.get_actions(self.request))
