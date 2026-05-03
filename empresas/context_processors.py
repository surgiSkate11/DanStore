from django.core.cache import cache

def empresa_actual(request):
    """
    Context Processor que inyecta la información de la empresa
    en todas las plantillas (templates) de Django.
    """
    context = {}
    if hasattr(request, 'empresa') and request.empresa:
        context['empresa'] = request.empresa
        
    if hasattr(request, 'user') and hasattr(request.user, 'profile'):
        context['rol_usuario'] = request.user.profile.rol
        
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
