from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from empresas.models import ConfiguracionSaaS
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