from django.core.cache import cache
from usuarios.utils import es_superadmin


def empresa_actual(request):
    """
    Context Processor que inyecta la información de la empresa
    en todas las plantillas (templates) de Django.
    """
    context = {}
    if hasattr(request, 'empresa') and request.empresa:
        context['empresa'] = request.empresa

    # OPTIMIZACIÓN: Reutilizar el rol ya cargado por el middleware en RAM
    if hasattr(request, 'rol') and request.rol:
        context['rol_usuario'] = request.rol
    elif hasattr(request, 'user') and hasattr(request.user, 'profile'):
        context['rol_usuario'] = request.user.profile.rol

    # Fuente única de verdad: usa el mismo helper que las vistas saas_*,
    # así el navbar y los permisos de acceso nunca se desincronizan entre
    # sí (antes esto solo miraba is_superuser, mientras las vistas miraban
    # el campo de texto 'rol' — podían quedar en desacuerdo).
    if hasattr(request, 'user') and request.user.is_authenticated:
        context['es_superadmin'] = es_superadmin(request.user)

    # OPTIMIZACIÓN EXTREMA: Leer nombre de la app y correo de soporte desde
    # la memoria RAM (Caché) en lugar de consultar la base de datos en cada
    # recarga de página. Los dos valores viven en el MISMO registro
    # ConfiguracionSaaS (singleton), así que si falta cualquiera de los dos
    # en caché se hace UNA sola consulta y se rellenan ambos huecos juntos
    # — nunca dos SELECT separados para leer el mismo objeto.
    #
    # 'saas_app_name' es también leído directamente (sin pasar por este
    # context processor) desde empresas/views.py y usuarios/views.py para
    # armar asuntos de correo — por eso se mantiene como su propia key,
    # en vez de fusionarla con support_email en un único diccionario.
    app_name = cache.get('saas_app_name')
    support_email = cache.get('saas_support_email')

    if app_name is None or support_email is None:
        try:
            from .models import ConfiguracionSaaS
            config = ConfiguracionSaaS.objects.first()
            app_name = config.nombre_plataforma if config and config.nombre_plataforma else "Tiendita SaaS"
            support_email = config.support_email if config and config.support_email else ""
        except Exception:
            app_name = app_name or "Tiendita SaaS"
            support_email = support_email or ""
        cache.set('saas_app_name', app_name, 3600)
        cache.set('saas_support_email', support_email, 3600)

    context['app_name'] = app_name
    context['support_email'] = support_email

    return context