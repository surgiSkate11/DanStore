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
        
    return context
