"""Utilidades compartidas por las pruebas de aislamiento entre empresas."""
from django.contrib.auth.models import User

from empresas.models import Empresa
from usuarios.models import UserProfile


def crear_empresa_con_dueno(slug):
    empresa = Empresa.objects.create(nombre=slug.title(), slug=slug)
    user = User.objects.create_user(username=f'dueno_{slug}', password='Clave-prueba-123')
    UserProfile.objects.update_or_create(user=user, defaults={'empresa': empresa, 'rol': 'owner'})
    return empresa, user
