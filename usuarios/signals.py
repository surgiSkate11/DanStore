from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile


@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    """Crea automáticamente un perfil cuando se crea un usuario"""
    if created:
        rol_inicial = 'superadmin' if instance.is_superuser else 'owner'
        UserProfile.objects.create(user=instance, rol=rol_inicial)


@receiver(post_save, sender=User)
def guardar_perfil_usuario(sender, instance, **kwargs):
    """Guarda el perfil cuando se actualiza el usuario"""
    if hasattr(instance, 'profile'):
        instance.profile.save()