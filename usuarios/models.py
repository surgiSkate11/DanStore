from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from empresas.models import Empresa


class ModuloSaaS(models.Model):
    """Módulos globales del sistema que el SuperAdmin puede habilitar/deshabilitar por plan"""
    codigo = models.CharField(max_length=50, unique=True, help_text="Ej: ventas, sorteos, catalogos")
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField(blank=True)
    icono = models.CharField(max_length=50, default="bi-box", help_text="Clase de Bootstrap Icon")
    requiere_plan_premium = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"

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
        unique_together = ['empresa', 'nombre']  # No pueden haber dos "Cajeros" en la misma empresa

    def __str__(self):
        return f"{self.nombre} - {self.empresa.nombre}"


class UserProfile(models.Model):
    """
    Perfil de usuario del dominio de NEGOCIO — exclusivo para dueño de
    empresa, empleado o cliente final.

    Un superadmin (is_superuser=True) NUNCA tiene fila en esta tabla.
    No pertenece al dominio empresarial, pertenece al sistema: su
    identidad y permisos se resuelven 100% desde ``User.is_superuser``
    (ver ``usuarios.utils.es_superadmin``). No crear un UserProfile
    "vacío" para representarlo — simplemente no existe fila para él.
    """

    TIPO_NEGOCIO_CHOICES = [
        ('ropa', 'Ropa'),
        ('tecnologia', 'Tecnología'),
        ('alimentos', 'Alimentos'),
        ('servicios', 'Servicios'),
        ('otro', 'Otro'),
    ]

    ROLES = (
        ('owner', 'Dueño de Empresa (Tenant Owner)'),
        ('employee', 'Empleado de Empresa'),
        ('cliente', 'Cliente Final'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Sistema Multi-tenant
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name='empleados')

    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='owner',
        blank=True,
        help_text="Rol dentro de una empresa. Queda vacío momentáneamente solo durante la "
                   "creación del usuario, hasta que el flujo que lo crea le asigna el rol "
                   "real (owner/employee/cliente) en la misma transacción."
    )

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

    # --- CORRECCIÓN DE SEGURIDAD ---
    # Fuerza al empleado a cambiar su contraseña temporal en su primer login,
    # para que el dueño que la creó deje de tener acceso permanente a la contraseña real.
    debe_cambiar_password = models.BooleanField(
        default=False,
        verbose_name="Debe cambiar contraseña",
        help_text="Se activa al crear un empleado con contraseña temporal; se desactiva cuando el usuario la cambia."
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

    def clean(self):
        """
        Un RolEmpresa (permisos granulares por módulo) solo tiene sentido
        para un empleado. Un 'owner' ya tiene acceso total y un 'cliente'
        no navega módulos internos, así que ninguno de los dos debería
        tener rol_empresa asignado.

        NOTA: Django no llama clean() automáticamente en .save() — solo
        lo dispara un ModelForm (por eso /admin/ ya queda protegido
        gratis). Para guardados directos desde una vista, hay que llamar
        profile.full_clean() a mano antes de perfil.save() si se quiere
        que esta validación se aplique ahí también.
        """
        if self.rol_empresa_id and self.rol != 'employee':
            raise ValidationError(
                {'rol_empresa': "Un rol de empresa (RolEmpresa) solo puede asignarse a un usuario con rol 'employee'."}
            )

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