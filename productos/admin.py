from django.contrib import admin
from .models import Producto, TipoPrenda

@admin.register(TipoPrenda)
class TipoPrendaAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'creado_en']
    search_fields = ['nombre']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'categoria_grupo', 'tipo_prenda', 'rango_edad', 'estado', 'precio', 'creado_en']
    list_filter = ['categoria_grupo', 'estado', 'tipo_prenda']
    search_fields = ['descripcion']
    list_editable = ['estado']
    readonly_fields = ['creado_en', 'actualizado_en']
