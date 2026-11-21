from django import forms
from django.contrib import admin
from .models import Producto, TipoProducto


class ProductoAdminForm(forms.ModelForm):
    """Valida en el admin la misma regla de estado y stock que el resto del sistema (S8)."""

    class Meta:
        model = Producto
        fields = '__all__'

    def clean(self):
        datos = super().clean()
        error = Producto.error_estado_stock(datos.get('estado'), datos.get('stock'))
        if error:
            self.add_error('stock', error)
        return datos

@admin.register(TipoProducto)
class TipoProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'creado_en']
    search_fields = ['nombre']


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['id', 'nombre', 'categoria', 'tipo_producto', 'variante', 'estado', 'precio', 'creado_en']
    list_filter = ['categoria', 'estado', 'tipo_producto']
    search_fields = ['nombre', 'descripcion']
    # El estado no se edita desde la lista: ahí no se ve ni se valida el stock (S8).
    form = ProductoAdminForm
    readonly_fields = ['creado_en', 'actualizado_en']
