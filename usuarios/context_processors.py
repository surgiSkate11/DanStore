from usuarios.models import UserProfile


def vocabulario(request):
    """Context processor que inyecta el vocabulario dinámico según el tipo de negocio del usuario"""
    
    contexto = {
        'vocab': {},
        'modulos_permitidos': set(),
        'permisos': {}
    }
    
    # Si el usuario está autenticado, obtener su perfil
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            contexto['vocab'] = profile.get_vocabulario()
            contexto['negocio_tipo'] = profile.negocio_tipo
            contexto['nombre_negocio'] = profile.nombre_negocio
            contexto['onboarding_completado'] = profile.onboarding_completado
            contexto['usa_demo_data'] = profile.usa_demo_data
            contexto['rol_usuario'] = profile.rol
            
            # Lógica dinámica de Módulos (SaaS)
            from usuarios.models import ModuloSaaS
            
            if profile.rol == 'superadmin':
                # El SuperAdmin NO debe tener acceso a módulos operativos de las tiendas
                contexto['modulos_permitidos'] = set()
                contexto['permisos'] = {}
            elif profile.rol == 'owner':
                modulos = set(ModuloSaaS.objects.values_list('codigo', flat=True))
                # Fallback: Si aún no has creado módulos en la BD, inyectamos los básicos
                if not modulos:
                    modulos = {'productos', 'ventas', 'clientes', 'sorteos', 'catalogos'}
                contexto['modulos_permitidos'] = modulos
                # Dueño tiene full acceso a todo automáticamente
                contexto['permisos'] = {mod: ['ver', 'crear', 'editar', 'eliminar'] for mod in modulos}
            elif profile.rol == 'employee' and profile.rol_empresa:
                modulos_permitidos = set(profile.rol_empresa.modulos_permitidos.values_list('codigo', flat=True))
                contexto['modulos_permitidos'] = modulos_permitidos
                
                permisos_dict = profile.rol_empresa.permisos_detallados or {}
                # Retrocompatibilidad: Si tiene el módulo pero no hay JSON de permisos, asume full access por ahora
                for mod_code in modulos_permitidos:
                    if mod_code not in permisos_dict:
                        permisos_dict[mod_code] = ['ver', 'crear', 'editar', 'eliminar']
                
                contexto['permisos'] = permisos_dict
                
        except UserProfile.DoesNotExist:
            # Si no existe el perfil, crear uno
            profile = UserProfile.objects.create(user=request.user)
            contexto['vocab'] = profile.get_vocabulario()
            contexto['negocio_tipo'] = profile.negocio_tipo
            
        # Verificar si tiene credenciales de Google Sheets conectadas
        if hasattr(request, 'empresa') and request.empresa:
            contexto['tiene_credentials_google'] = bool(request.empresa.google_oauth_credentials)
        else:
            contexto['tiene_credentials_google'] = False

        # Tour guiado (Shepherd.js, ver base.html): se dispara solo para
        # el dueño de una empresa que todavía no lo completó, y solo si
        # ya tiene una Empresa real asignada (si no, está en la pantalla
        # de espera, donde no hay nada que recorrer).
        contexto['iniciar_tour'] = bool(
            contexto.get('rol_usuario') == 'owner'
            and not contexto.get('onboarding_completado', True)
            and hasattr(request, 'empresa') and request.empresa
        )
    
    return contexto