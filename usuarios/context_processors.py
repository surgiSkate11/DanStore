from usuarios.models import UserProfile
from usuarios.utils import es_superadmin


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

            if es_superadmin(request.user):
                # El SuperAdmin no tiene rol de tenant (profile.rol='') ni
                # módulos operativos de tienda — es_superadmin() es la única
                # fuente de verdad, no un valor de texto en profile.rol.
                contexto['modulos_permitidos'] = set()
                contexto['permisos'] = {}
            elif profile.rol == 'owner':
                # Los módulos del dueño salen del Plan al que está suscrita
                # su empresa — nunca de "todos los módulos que existan en el
                # sistema". Si la empresa todavía no tiene una suscripción
                # activa con un plan asignado, no ve ningún módulo operativo
                # hasta que se le asigne uno (ver empresas/signals.py, que
                # crea la suscripción automáticamente al crear la Empresa).
                modulos = set()
                empresa = getattr(profile, 'empresa', None)
                suscripcion = getattr(empresa, 'suscripcion', None) if empresa else None
                plan = getattr(suscripcion, 'plan', None) if suscripcion else None
                if plan:
                    modulos = set(plan.modulos.values_list('codigo', flat=True))

                contexto['modulos_permitidos'] = modulos
                # Dueño tiene full acceso a los módulos que su plan incluye
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

        contexto['iniciar_tour'] = bool(
            contexto.get('rol_usuario') == 'owner'
            and not contexto.get('onboarding_completado', True)
            and hasattr(request, 'empresa') and request.empresa
            and getattr(request.resolver_match, 'url_name', None) == 'dashboard_tenant'

        )

    return contexto