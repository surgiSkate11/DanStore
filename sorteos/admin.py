from django.contrib import admin
from .models import Sorteo, Participante, Premio, ResultadoSorteo, Cupon


class PremioInline(admin.TabularInline):
    model = Premio
    extra = 1
    fields = ['nombre', 'tipo', 'valor_descuento', 'numero_cofre', 'color', 'cantidad_disponible']


class ParticipanteInline(admin.TabularInline):
    model = Participante
    extra = 0
    raw_id_fields = ['cliente']


class ResultadoInline(admin.TabularInline):
    model = ResultadoSorteo
    extra = 0
    readonly_fields = ['fecha_resultado']
    raw_id_fields = ['cliente', 'premio']


@admin.register(Sorteo)
class SorteoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo', 'criterio', 'cantidad_participantes', 'activo', 'completado', 'fecha_creacion']
    list_filter = ['tipo', 'criterio', 'activo', 'completado', 'fecha_creacion']
    search_fields = ['nombre', 'descripcion']
    inlines = [PremioInline, ParticipanteInline, ResultadoInline]
    readonly_fields = ['fecha_creacion', 'cantidad_participantes']
    
    fieldsets = (
        ('Información Básica', {
            'fields': ('nombre', 'tipo', 'descripcion')
        }),
        ('Criterios de Participación', {
            'fields': ('criterio', 'monto_minimo', 'cantidad_minima', 'top_cantidad')
        }),
        ('Configuración Específica', {
            'fields': ('cantidad_cofres',)
        }),
        ('Estado', {
            'fields': ('activo', 'completado', 'fecha_creacion', 'fecha_sorteo')
        }),
    )


@admin.register(Premio)
class PremioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'tipo', 'sorteo', 'valor_descuento', 'numero_cofre', 'color', 'asignado']
    list_filter = ['tipo', 'asignado', 'sorteo']
    search_fields = ['nombre', 'descripcion']


@admin.register(ResultadoSorteo)
class ResultadoSorteoAdmin(admin.ModelAdmin):
    list_display = ['cliente', 'sorteo', 'premio', 'posicion', 'premio_canjeado', 'fecha_resultado']
    list_filter = ['premio_canjeado', 'fecha_resultado', 'sorteo']
    search_fields = ['cliente__nombre', 'sorteo__nombre']
    raw_id_fields = ['cliente', 'premio', 'sorteo']


@admin.register(Cupon)
class CuponAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'resultado', 'tipo_descuento', 'valor', 'usado', 'fecha_creacion', 'fecha_expiracion']
    list_filter = ['usado', 'tipo_descuento', 'fecha_creacion']
    search_fields = ['codigo', 'resultado__cliente__nombre']
    readonly_fields = ['fecha_creacion', 'fecha_uso']
    
    def has_add_permission(self, request):
        # Los cupones se crean automáticamente
        return False
