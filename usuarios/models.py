from django.db import models
from django.contrib.auth.models import User
from empresas.models import Empresa
from django.utils import timezone


class ModuloSaaS(models.Model):
    """Módulos globales del sistema que el SuperAdmin puede habilitar/deshabilitar por plan"""
    codigo = models.CharField(max_length=50, unique=True, help_text="Ej: ventas, sorteos, catalogos")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    icono = models.CharField(max_length=50, default="bi-box", help_text="Clase de Bootstrap Icon")
    requiere_plan_premium = models.BooleanField(default=False)

    def __str__(self):
        return self.nombre


class RolEmpresa(models.Model):
    """Roles personalizados creados por el Dueño para SU empresa (Tenant RBAC)"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='roles_personalizados')
    nombre = models.CharField(max_length=100, help_text="Ej: Cajero, Gerente de Ventas")
    
    # Módulos enteros a los que este rol tiene acceso
    modulos_permitidos = models.ManyToManyField(ModuloSaaS, blank=True)
    
    # Permisos granulares (JSON) ej: {"ventas": {"crear": true, "eliminar": false}}
    permisos_detallados = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['empresa', 'nombre'] # No pueden haber dos "Cajeros" en la misma empresa

    def __str__(self):
        return f"{self.nombre} - {self.empresa.nombre}"


class UserProfile(models.Model):
    """Perfil extendido del usuario con información del negocio"""
    
    TIPO_NEGOCIO_CHOICES = [
        ('ropa', 'Ropa'),
        ('tecnologia', 'Tecnología'),
        ('alimentos', 'Alimentos'),
        ('servicios', 'Servicios'),
        ('otro', 'Otro'),
    ]

    ROLES = (
        ('SUPERADMIN', 'Dueño del Software'),
        ('DUEÑO', 'Dueño de Empresa (Tenant Owner)'),
        ('EMPLEADO', 'Empleado de Empresa'),
        ('CLIENTE', 'Cliente Final'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    
    # Sistema Multi-tenant
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name='empleados')
    rol = models.CharField(max_length=20, choices=ROLES, default='DUEÑO')
    
    # Si el usuario es EMPLEADO, aquí se asigna qué rol tiene dentro de la empresa
    rol_empresa = models.ForeignKey(RolEmpresa, on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios')
    
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
