from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'negocio_tipo', 'nombre_negocio', 'onboarding_completado']
    list_filter = ['negocio_tipo', 'onboarding_completado', 'creado_en']
    search_fields = ['user__username', 'nombre_negocio']
    fieldsets = (
        ('Usuario', {'fields': ('user',)}),
        ('Negocio', {'fields': ('negocio_tipo', 'nombre_negocio', 'descripcion_negocio')}),
        ('Onboarding', {'fields': ('onboarding_completado',)}),
        ('Demo', {'fields': ('usa_demo_data',)}),
    )
    readonly_fields = ['creado_en', 'actualizado_en']
