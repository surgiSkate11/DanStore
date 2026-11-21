"""Utilidades compartidas por las pruebas de aislamiento entre empresas."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone

from empresas.models import Empresa, SuscripcionEmpresa
from usuarios.models import UserProfile


def crear_empresa_con_dueno(slug, suscripcion=True):
    """Empresa con dueño y, por defecto, una suscripción vigente de 30 días.

    Una empresa sin suscripción queda suspendida (S7), así que la mayoría de las
    pruebas necesitan una; las de suspensión pasan suscripcion=False.
    """
    empresa = Empresa.objects.create(nombre=slug.title(), slug=slug)
    if suscripcion:
        ahora = timezone.now()
        SuscripcionEmpresa.objects.create(
            empresa=empresa, fecha_inicio=ahora, fecha_vencimiento=ahora + timedelta(days=30),
        )
    user = User.objects.create_user(username=f'dueno_{slug}', password='Clave-prueba-123')
    UserProfile.objects.update_or_create(user=user, defaults={'empresa': empresa, 'rol': 'owner'})
    return empresa, user
