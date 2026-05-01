from usuarios.models import UserProfile
import os
from django.conf import settings


def vocabulario(request):
    """Context processor que inyecta el vocabulario dinámico según el tipo de negocio del usuario"""
    
    contexto = {
        'vocab': {},
        'modulos_permitidos': set()
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
            
            if profile.rol == 'SUPERADMIN':
                # El SuperAdmin NO debe tener acceso a módulos operativos de las tiendas
                contexto['modulos_permitidos'] = set()
            elif profile.rol == 'DUEÑO':
                modulos = set(ModuloSaaS.objects.values_list('codigo', flat=True))
                # Fallback: Si aún no has creado módulos en la BD, inyectamos los básicos
                if not modulos:
                    modulos = {'productos', 'ventas', 'clientes', 'sorteos', 'catalogos'}
                contexto['modulos_permitidos'] = modulos
            elif profile.rol == 'EMPLEADO' and profile.rol_empresa:
                contexto['modulos_permitidos'] = set(profile.rol_empresa.modulos_permitidos.values_list('codigo', flat=True))
                
        except UserProfile.DoesNotExist:
            # Si no existe el perfil, crear uno
            profile = UserProfile.objects.create(user=request.user)
            contexto['vocab'] = profile.get_vocabulario()
            contexto['negocio_tipo'] = profile.negocio_tipo
            
        # Verificar si tiene credenciales de Google Sheets conectadas
        if hasattr(request, 'empresa') and request.empresa:
            creds_path = os.path.join(settings.MEDIA_ROOT, f'google_oauth_{request.empresa.id}.json')
            contexto['tiene_credentials_google'] = os.path.exists(creds_path)
        else:
            contexto['tiene_credentials_google'] = False
    
    return contexto
