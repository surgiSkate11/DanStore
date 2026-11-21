from django.contrib import admin
from .models import Empresa, Plan, SuscripcionEmpresa, Ticket, MensajeTicket, ConfiguracionSaaS


class SinBorradoAdmin(admin.ModelAdmin):
    """Empresa y SuscripcionEmpresa no se borran (S7): borrar la empresa arrastra todos sus datos
    y borrar la suscripción dejaría acceso gratis. Dar de baja = desactivar la empresa."""

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        acciones = super().get_actions(request)
        acciones.pop('delete_selected', None)
        return acciones


@admin.register(Empresa)
class EmpresaAdmin(SinBorradoAdmin):
    list_display = ('nombre', 'slug', 'activa', 'fecha_creacion')
    search_fields = ('nombre', 'slug')
    list_filter = ('activa',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_mensual', 'precio_anual')
    filter_horizontal = ('modulos',)


@admin.register(SuscripcionEmpresa)
class SuscripcionEmpresaAdmin(SinBorradoAdmin):
    list_display = ('empresa', 'plan', 'tipo_plan', 'fecha_inicio', 'fecha_vencimiento')
    search_fields = ('empresa__nombre', 'plan__nombre')
    list_filter = ('tipo_plan', 'plan')
    readonly_fields = ('fecha_inicio', 'fecha_vencimiento')
    fieldsets = (
        (None, {
            'fields': ('empresa', 'plan', 'tipo_plan'),
            'description': (
                'Las fechas se calculan automáticamente al crear la suscripción según el tipo de plan. '
                'Si cambias el plan o el tipo, el cambio se aplica en la próxima renovación.'
            ),
        }),
        ('Periodo', {'fields': ('fecha_inicio', 'fecha_vencimiento')}),
    )
    actions = ('renovar_suscripciones',)

    def save_model(self, request, obj, form, change):
        # Al crear, las fechas salen del tipo de plan (S6); al editar no se recalculan.
        if not change:
            obj.iniciar_periodo()
        super().save_model(request, obj, form, change)

    def get_actions(self, request):
        acciones = super().get_actions(request)
        if not request.user.is_superuser:
            acciones.pop('renovar_suscripciones', None)
        return acciones

    @admin.action(description='Renovar suscripciones según su periodo')
    def renovar_suscripciones(self, request, queryset):
        if not request.user.is_superuser:
            self.message_user(request, 'Solo un superadministrador puede renovar suscripciones.', level='ERROR')
            return
        renovadas = 0
        reactivadas = 0

        for suscripcion in queryset.select_related('empresa', 'plan'):
            if not suscripcion.plan:
                self.message_user(
                    request,
                    f"{suscripcion.empresa.nombre} no tiene un plan asignado y no fue renovada.",
                    level='ERROR',
                )
                continue
            if not suscripcion.puede_renovarse:
                self.message_user(
                    request,
                    suscripcion.mensaje_fuera_de_ventana(),
                    level='WARNING',
                )
                continue

            suscripcion.renovar()
            renovadas += 1

            empresa = suscripcion.empresa
            if not empresa.suspension_manual and not empresa.activa:
                empresa.activa = True
                empresa.save(update_fields=['activa'])
                reactivadas += 1

        self.message_user(
            request,
            f"{renovadas} suscripción(es) renovada(s); {reactivadas} empresa(s) reactivada(s).",
        )


class MensajeTicketInline(admin.TabularInline):
    model = MensajeTicket
    extra = 1

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'asunto', 'empresa', 'categoria', 'prioridad', 'estado', 'actualizado_en')
    list_filter = ('estado', 'prioridad', 'categoria', 'creado_en')
    search_fields = ('asunto', 'empresa__nombre', 'id')
    inlines = [MensajeTicketInline]

@admin.register(MensajeTicket)
class MensajeTicketAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'remitente', 'es_staff', 'creado_en')
    list_filter = ('es_staff', 'creado_en')
    search_fields = ('mensaje', 'ticket__asunto', 'remitente__username')

@admin.register(ConfiguracionSaaS)
class ConfiguracionSaaSAdmin(admin.ModelAdmin):
    list_display = ('__str__',)
    def has_add_permission(self, request):
        try:
            # Solo permitir crear un único registro de configuración
            return not ConfiguracionSaaS.objects.exists()
        except Exception:
            return True