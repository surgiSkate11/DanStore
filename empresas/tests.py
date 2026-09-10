from django.test import TestCase

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

from usuarios.models import UserProfile
from .middleware import TenantMiddleware, _obtener_session_timeout_minutos
from .models import ConfiguracionSaaS, Empresa


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

# Create your tests here.
