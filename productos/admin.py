from django.contrib import admin
from .models import Producto, TipoProducto

@admin.register(TipoProducto)
class TipoProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'creado_en']
    search_fields = ['nombre']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'categoria', 'tipo_producto', 'variante', 'estado', 'precio', 'creado_en']
    list_filter = ['categoria', 'estado', 'tipo_producto']
    search_fields = ['nombre', 'descripcion']
    list_editable = ['estado']
    readonly_fields = ['creado_en', 'actualizado_en']
