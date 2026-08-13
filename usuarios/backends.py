from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.db.models import Q

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

        # Si hay más de un candidato (ej. email duplicado en otra cuenta),
        # priorizamos la coincidencia exacta por username; si no hay, tomamos el primero.
        user = candidatos.filter(username__iexact=username).first() or candidatos.first()

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None