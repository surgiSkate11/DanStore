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

    # OPTIMIZACIÓN EXTREMA: Leer el nombre de la app desde la memoria RAM (Caché)
    # en lugar de consultar la base de datos en cada recarga de página
    app_name = cache.get('saas_app_name')
    if not app_name:
        try:
            from .models import ConfiguracionSaaS
            config = ConfiguracionSaaS.objects.first()
            app_name = config.nombre_plataforma if config and config.nombre_plataforma else "Tiendita SaaS"
            cache.set('saas_app_name', app_name, 3600)  # Guardar en memoria por 1 hora
        except Exception:
            app_name = "Tiendita SaaS"

    context['app_name'] = app_name

    return context