from django.contrib import admin
from django.contrib.auth.models import Group
from .models import ModuloSaaS, RolEmpresa, UserProfile

# Ocultar el modelo de Grupos nativo de Django porque ahora usamos
# nuestro propio sistema SaaS (RolEmpresa)
admin.site.unregister(Group)


@admin.register(ModuloSaaS)
class ModuloSaaSAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo', 'icono', 'requiere_plan_premium')
    search_fields = ('nombre', 'codigo')
    list_filter = ('requiere_plan_premium',)


@admin.register(RolEmpresa)
class RolEmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'empresa', 'creado_en')
    search_fields = ('nombre', 'empresa__nombre')
    list_filter = ('empresa',)
    filter_horizontal = ('modulos_permitidos',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """
    Administra ÚNICAMENTE perfiles de tenant (owner/employee/cliente).
    Un superadmin nunca tiene fila en UserProfile — is_superuser es su
    única fuente de verdad — así que este admin nunca necesita
    distinguir "cuenta de tenant" vs "administrador global", ni ocultar
    campos empresariales: acá jamás aparece un superadmin.
    """
    list_display = ('user', 'rol', 'empresa', 'negocio_tipo')
    search_fields = ('user__username', 'user__email', 'empresa__nombre')
    list_filter = ('rol', 'negocio_tipo', 'onboarding_completado')