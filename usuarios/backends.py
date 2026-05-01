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
        try:
            # Buscar al usuario por nombre de usuario o email, sin importar mayúsculas
            user = User.objects.get(Q(username__iexact=username) | Q(email__iexact=username))
        except User.DoesNotExist:
            return None
        
        if user.check_password(password) and self.user_can_authenticate(user):
            return user