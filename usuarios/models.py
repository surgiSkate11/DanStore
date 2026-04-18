from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Perfil extendido del usuario con información del negocio"""
    
    TIPO_NEGOCIO_CHOICES = [
        ('ropa', 'Ropa'),
        ('tecnologia', 'Tecnología'),
        ('alimentos', 'Alimentos'),
        ('servicios', 'Servicios'),
        ('otro', 'Otro'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Tipo de negocio (define vocabulario dinámico)
    negocio_tipo = models.CharField(
        max_length=20,
        choices=TIPO_NEGOCIO_CHOICES,
        default='ropa',
        verbose_name="Tipo de negocio"
    )
    
    # Nombre del negocio
    nombre_negocio = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Nombre del negocio"
    )
    
    # Información adicional
    descripcion_negocio = models.TextField(blank=True, verbose_name="Descripción del negocio")
    
    # Configuración de onboarding
    onboarding_completado = models.BooleanField(
        default=False,
        verbose_name="Onboarding completado"
    )
    
    # Demo data
    usa_demo_data = models.BooleanField(
        default=False,
        verbose_name="Usando datos de demostración"
    )
    
    # Auditoría
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Perfil de Usuario"
        verbose_name_plural = "Perfiles de Usuario"
    
    def __str__(self):
        return f"Perfil de {self.user.username}"
    
    def get_vocabulario(self):
        """Retorna diccionario de términos según el tipo de negocio"""
        vocabularios = {
            'ropa': {
                'unidad': 'Prenda',
                'unidad_plural': 'Prendas',
                'separado': 'Separado',
                'separado_plural': 'Separados',
                'unidad_inventario': 'Tipo de Prenda',
            },
            'tecnologia': {
                'unidad': 'Producto',
                'unidad_plural': 'Productos',
                'separado': 'Reservado',
                'separado_plural': 'Reservados',
                'unidad_inventario': 'Tipo de Producto',
            },
            'alimentos': {
                'unidad': 'Producto',
                'unidad_plural': 'Productos',
                'separado': 'En proceso',
                'separado_plural': 'En proceso',
                'unidad_inventario': 'Tipo de Producto',
            },
            'servicios': {
                'unidad': 'Servicio',
                'unidad_plural': 'Servicios',
                'separado': 'Contratado',
                'separado_plural': 'Contratados',
                'unidad_inventario': 'Tipo de Servicio',
            },
            'otro': {
                'unidad': 'Artículo',
                'unidad_plural': 'Artículos',
                'separado': 'Reservado',
                'separado_plural': 'Reservados',
                'unidad_inventario': 'Tipo de Artículo',
            },
        }
        return vocabularios.get(self.negocio_tipo, vocabularios['otro'])
