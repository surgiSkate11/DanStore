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

    CREAR UN User NO CREA UN UserProfile. Son dos procesos deliberadamente
    independientes (ver el panel de Control de BD, que es hoy el único
    lugar del sistema que crea filas de este modelo para un dueño/cliente
    nuevo — el alta de empleados en empresas/views.py::lista_empleados es
    la otra vía, y ya asigna rol='employee' explícitamente en el mismo
    flujo). Un User sin UserProfile es un estado válido: intentar entrar
    a un módulo que requiere perfil debe dar 403, nunca crear uno solo.
    """

    TIPO_NEGOCIO_CHOICES = [
        ('ropa', 'Ropa'),
        ('tecnologia', 'Tecnología'),
        ('alimentos', 'Alimentos'),
        ('servicios', 'Servicios'),
        ('otro', 'Otro'),
    ]

    ROLES = (
        # CORRECCIÓN DE SEGURIDAD: placeholder explícito como PRIMERA opción.
        # Un <select> HTML sin opción vacía siempre queda con la primera
        # opción real preseleccionada visualmente — eso era el problema
        # original (quedaba "Dueño" marcado aunque nadie lo eligiera). Con
        # este placeholder como opción 0 y el campo marcado como
        # obligatorio (blank=False más abajo), el navegador y
        # full_clean() bloquean el guardado hasta que se elija un rol
        # real. No es un rol de negocio válido — nunca debe usarse como
        # valor guardado.
        ('', 'Selecciona un rol...'),
        ('owner', 'Dueño de Empresa (Tenant Owner)'),
        ('employee', 'Empleado de Empresa'),
        ('cliente', 'Cliente Final'),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # Sistema Multi-tenant
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, null=True, blank=True, related_name='empleados')

    # CORRECCIÓN DE SEGURIDAD (punto 8): antes default='owner', blank=True.
    # Un olvido al crear el perfil NUNCA debe convertir a alguien en dueño
    # por omisión. Ahora no hay valor por defecto seguro: el rol es
    # OBLIGATORIO y debe elegirse conscientemente en el formulario que lo
    # crea. Si se deja el placeholder ('') o no se envía, el guardado se
    # rechaza (a través del ModelForm, que valida esto en full_clean())
    # y el error ya llega al usuario por el sistema de mensajes existente
    # (ver form_errors_to_messages en dashboard/views.py::saas_crear_registro).
    #
    # El superadmin/dueño del software es un concepto TOTALMENTE aparte:
    # se determina por User.is_superuser (ver usuarios.utils.es_superadmin)
    # y nunca depende de este campo ni de este modelo.
    rol = models.CharField(
        max_length=20,
        choices=ROLES,
        default='',
        blank=False,
        help_text="Rol de negocio dentro de una empresa"
    )

    # Si el usuario es EMPLEADO, aquí se asigna qué cargo/puesto tiene
    # dentro de la empresa (ej. "Cajero", "Gerente de Ventas"). Antes se
    # llamaba 'rol_empresa', pero ese nombre confundía con 'rol' de arriba
    # (que es la categoría amplia de sistema: owner/employee/cliente).
    # 'cargo' deja claro que son dos conceptos distintos: 'rol' = qué TIPO
    # de cuenta es, 'cargo' = qué PUESTO ocupa dentro de la empresa (solo
    # aplica si rol == 'employee').
    cargo = models.ForeignKey(RolEmpresa, on_delete=models.SET_NULL, null=True, blank=True, related_name='usuarios')

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
        Dos reglas de integridad del dominio de negocio:

        1. Un superadmin (is_superuser=True) NUNCA puede tener fila en
           UserProfile — ni creada por código, ni a mano desde el botón
           "Add" de /admin/. Esta validación cierra ese camino también
           para una creación manual desde el admin eligiendo un user
           existente (eso nunca dispara un signal de User).

        2. Un RolEmpresa (permisos granulares por módulo, asignado vía el
           campo 'cargo') solo tiene sentido para un empleado. Un 'owner'
           ya tiene acceso total y un 'cliente' no navega módulos
           internos, así que ninguno de los dos debería tener un cargo
           asignado.

        NOTA: Django no llama clean() automáticamente en .save() — solo
        lo dispara un ModelForm (por eso /admin/ y el panel de Control de
        BD ya quedan protegidos gratis en ambos casos). Para guardados
        directos desde una vista, hay que llamar profile.full_clean() a
        mano antes de perfil.save() si se quiere que esta validación se
        aplique ahí también.
        """
        if self.user_id and self.user.is_superuser:
            raise ValidationError(
                "Un superadministrador (is_superuser=True) no puede tener un UserProfile: "
                "is_superuser ya es su única fuente de verdad, no pertenece al dominio de negocio."
            )

        if self.cargo_id and self.rol != 'employee':
            raise ValidationError(
                {'cargo': "Un cargo de empresa (RolEmpresa) solo puede asignarse a un usuario con rol 'employee'."}
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