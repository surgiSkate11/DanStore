from datetime import timedelta

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Autenticación personalizada para SaaS.
    Permite a los usuarios iniciar sesión usando su correo electrónico
    o su nombre de usuario de forma transparente.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        # Buscar candidatos por nombre de usuario o email, sin importar mayúsculas
        candidatos = User.objects.filter(
            Q(username__iexact=username) | Q(email__iexact=username)
        )

        if not candidatos.exists():
            return None

        # Un username exacto es inequívoco. Para correo, no elegir una cuenta
        # arbitraria si existen varias cuentas con el mismo email.
        user = candidatos.filter(username__iexact=username).first()
        if user is None:
            if candidatos.count() != 1:
                return None
            user = candidatos.first()

        from empresas.models import ConfiguracionSaaS
        from .models import LoginSecurityAttempt

        config = ConfiguracionSaaS.objects.filter(id=1).first()
        ahora = timezone.now()

        with transaction.atomic():
            security_attempt = LoginSecurityAttempt.objects.select_for_update().filter(user=user).first()

            if (
                config
                and config.login_lockout_enabled
                and security_attempt
                and security_attempt.locked_until
                and security_attempt.locked_until > ahora
            ):
                return None

            if user.check_password(password) and self.user_can_authenticate(user):
                if security_attempt:
                    security_attempt.delete()
                return user

            if config and config.login_lockout_enabled:
                es_nuevo = security_attempt is None
                if security_attempt is None:
                    security_attempt = LoginSecurityAttempt(user=user)
                security_attempt.failed_attempts += 1
                if security_attempt.failed_attempts >= config.login_max_attempts:
                    security_attempt.locked_until = ahora + timedelta(minutes=config.login_lockout_minutes)
                    security_attempt.failed_attempts = 0
                if es_nuevo:
                    security_attempt.save()
                else:
                    security_attempt.save(update_fields=['failed_attempts', 'locked_until', 'updated_at'])
        return None