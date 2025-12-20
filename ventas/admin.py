from django.contrib import admin
from .models import Cliente, Venta, DetalleVenta, ConfiguracionFactura


class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 1
    raw_id_fields = ['producto']


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'telefono', 'email', 'creado_en']
    search_fields = ['nombre', 'telefono', 'email']
    list_filter = ['creado_en']


@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ['numero_factura', 'cliente', 'fecha', 'total', 'creado_en']
    list_filter = ['fecha', 'creado_en']
    search_fields = ['cliente__nombre']
    inlines = [DetalleVentaInline]
    readonly_fields = ['creado_en', 'actualizado_en']


@admin.register(ConfiguracionFactura)
class ConfiguracionFacturaAdmin(admin.ModelAdmin):
    list_display = ['nombre_empresa', 'telefono_empresa', 'actualizado_en']
    
    def has_add_permission(self, request):
        # Solo permitir un registro
        return not ConfiguracionFactura.objects.exists()
    
    def has_delete_permission(self, request, obj=None):
        # No permitir eliminar
        return False
