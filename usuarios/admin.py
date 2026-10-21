from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group
from django.utils.functional import empty
from django_otp import devices_for_user
from django_otp.admin import OTPAdminAuthenticationForm, OTPAdminSite
from .models import ModuloSaaS, RolEmpresa, UserProfile


class SuperusuarioAuthenticationForm(OTPAdminAuthenticationForm):
    """Login del panel: pide el código TOTP y solo deja pasar a superusuarios."""

    def _chosen_device(self, user):
        # django-otp 1.7.x exige elegir el dispositivo. Si no se eligió ninguno y la
        # cuenta tiene uno solo confirmado, se usa ese: solo hay que escribir el código.
        dispositivo = super()._chosen_device(user)
        if dispositivo is None and not self.cleaned_data.get('otp_device'):
            propios = list(devices_for_user(user))
            if len(propios) == 1:
                dispositivo = propios[0]
        return dispositivo

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        # Mismo error que una contraseña incorrecta: un mensaje distinto revelaría
        # que la contraseña de esa cuenta es válida.
        if not user.is_superuser:
            raise forms.ValidationError(
                self.error_messages['invalid_login'],
                code='invalid_login',
                params={'username': self.username_field.verbose_name},
            )


class SuperusuarioOTPAdminSite(OTPAdminSite):
    """Panel de Django: solo superusuarios con un dispositivo OTP verificado (S13)."""

    login_form = SuperusuarioAuthenticationForm

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser


# `admin.site` es un LazyObject: no se le puede cambiar `__class__` directamente.
# Se cambia la clase de la instancia que envuelve, así los `admin.site.register(...)`
# de todas las apps siguen valiendo y el espacio de nombres sigue siendo 'admin'.
if admin.site._wrapped is empty:
    admin.site._setup()
admin.site._wrapped.__class__ = SuperusuarioOTPAdminSite

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