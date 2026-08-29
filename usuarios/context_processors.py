from usuarios.models import UserProfile
from usuarios.utils import es_superadmin


def vocabulario(request):
    """Context processor que inyecta el vocabulario dinámico según el tipo de negocio del usuario"""

    contexto = {
        'vocab': {},
        'modulos_permitidos': set(),
        'permisos': {}
    }

    if not request.user.is_authenticated:
        return contexto

    # Un superadmin nunca tiene UserProfile — is_superuser es la única
    # fuente de verdad (ver usuarios.utils.es_superadmin). Se resuelve
    # ANTES de tocar request.user.profile para no disparar el descriptor
    # reverso del OneToOne sobre un usuario que nunca va a tener fila.
    if es_superadmin(request.user):
        return contexto

    # Un usuario autenticado SIN perfil es un estado válido (recién
    # creado, esperando que un admin le asigne empresa + rol desde el
    # panel). Este context processor NUNCA debe crear el perfil que
    # falta — eso rompería la validación 403 de dashboard_router, que
    # depende de que "sin perfil" siga siendo cierto en el próximo
    # request. Si no hay perfil, se devuelve el contexto vacío tal cual.
    profile = getattr(request.user, 'profile', None)
    if profile is None:
        return contexto

    contexto['vocab'] = profile.get_vocabulario()
    contexto['negocio_tipo'] = profile.negocio_tipo
    contexto['nombre_negocio'] = profile.nombre_negocio
    contexto['onboarding_completado'] = profile.onboarding_completado
    contexto['rol_usuario'] = profile.rol

    if profile.rol == 'owner':
        # Los módulos del dueño salen del Plan al que está suscrita su
        # empresa — nunca de "todos los módulos que existan en el
        # sistema". Si la empresa todavía no tiene una suscripción
        # activa con un plan asignado, no ve ningún módulo operativo
        # hasta que se le asigne uno.
        modulos = set()
        empresa = getattr(profile, 'empresa', None)
        suscripcion = getattr(empresa, 'suscripcion', None) if empresa else None
        plan = getattr(suscripcion, 'plan', None) if suscripcion else None
        if plan:
            modulos = set(plan.modulos.values_list('codigo', flat=True))

        contexto['modulos_permitidos'] = modulos
        # Dueño tiene full acceso a los módulos que su plan incluye
        contexto['permisos'] = {mod: ['ver', 'crear', 'editar', 'eliminar'] for mod in modulos}

    elif profile.rol == 'employee' and profile.cargo:
        modulos_permitidos = set(profile.cargo.modulos_permitidos.values_list('codigo', flat=True))
        contexto['modulos_permitidos'] = modulos_permitidos

        permisos_dict = profile.cargo.permisos_detallados or {}
        # Retrocompatibilidad: si tiene el módulo pero no hay JSON de permisos, asume full access por ahora
        for mod_code in modulos_permitidos:
            if mod_code not in permisos_dict:
                permisos_dict[mod_code] = ['ver', 'crear', 'editar', 'eliminar']

        contexto['permisos'] = permisos_dict

    # Verificar si tiene credenciales de Google Sheets conectadas
    if hasattr(request, 'empresa') and request.empresa:
        contexto['tiene_credentials_google'] = bool(request.empresa.google_oauth_credentials)
    else:
        contexto['tiene_credentials_google'] = False

    contexto['iniciar_tour'] = bool(
        contexto.get('rol_usuario') == 'owner'
        and not contexto.get('onboarding_completado', True)
        and hasattr(request, 'empresa') and request.empresa
        and getattr(request.resolver_match, 'url_name', None) == 'dashboard_tenant'
    )

    return contexto