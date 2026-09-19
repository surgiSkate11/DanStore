from django.contrib import admin
from .models import Empresa, Plan, SuscripcionEmpresa, Ticket, MensajeTicket, ConfiguracionSaaS


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'slug', 'activa', 'fecha_creacion')
    search_fields = ('nombre', 'slug')
    list_filter = ('activa',)


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'precio_mensual', 'precio_anual')
    filter_horizontal = ('modulos',)


@admin.register(SuscripcionEmpresa)
class SuscripcionEmpresaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'plan', 'tipo_plan', 'fecha_inicio', 'fecha_vencimiento')
    search_fields = ('empresa__nombre', 'plan__nombre')
    list_filter = ('tipo_plan', 'plan')
    readonly_fields = ('fecha_inicio', 'fecha_vencimiento')
    actions = ('renovar_suscripciones',)

    @admin.action(description='Renovar suscripciones según su periodo')
    def renovar_suscripciones(self, request, queryset):
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