from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Empresa, Plan, SuscripcionEmpresa


@receiver(post_save, sender=Empresa)
def crear_suscripcion_inicial(sender, instance, created, **kwargs):
    """
    Al crear una Empresa nueva, le asigna automáticamente el Plan Básico
    con una suscripción de prueba de 30 días.

    Este es el ÚNICO lugar donde se crea una suscripción para una
    empresa — antes se generaba como efecto secundario de visitar la
    vista de Perfil, lo cual era una sorpresa oculta (una pantalla de
    "ver mi perfil" no debería crear un producto de facturación). Ahora
    ocurre en el momento exacto en que la empresa nace, de forma
    trazable.

    Requiere que el Plan Básico ya exista (creado una sola vez vía
    shell, con sus módulos ya asignados) — si por algún motivo no
    existe todavía, no se crea uno vacío acá: se registra un warning y
    la empresa queda sin plan hasta que un superadmin se lo asigne
    manualmente, en vez de arrancar con 0 módulos configurados
    silenciosamente.
    """
    if not created:
        return

    if hasattr(instance, 'suscripcion'):
        return

    plan_basico = Plan.objects.filter(nombre="Plan Básico").first()
    if not plan_basico:
        import logging
        logging.getLogger(__name__).warning(
            "No existe 'Plan Básico' al crear la empresa %s — no se generó "
            "suscripción automática. Creá el Plan Básico (con sus módulos) "
            "y asignaselo manualmente a esta empresa.", instance.pk
        )
        return

    SuscripcionEmpresa.objects.create(
        empresa=instance,
        plan=plan_basico,
        tipo_plan='mensual',
        fecha_inicio=timezone.now(),
        fecha_vencimiento=timezone.now() + timedelta(days=30),
    )