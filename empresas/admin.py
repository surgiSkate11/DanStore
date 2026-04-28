from django.contrib import admin
from .models import Empresa, Modulo, Plan


@admin.register(Modulo)
class ModuloAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'url_name', 'icono', 'activo', 'orden')
    list_editable = ('activo', 'orden')
    search_fields = ('nombre', 'url_name')

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio')
    filter_horizontal = ('modulos',) # Facilita la selección múltiple en el panel
    search_fields = ('nombre',)

@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'activa', 'plan', 'fecha_creacion')
    list_filter = ('activa', 'plan')
    search_fields = ('nombre', 'slug')
