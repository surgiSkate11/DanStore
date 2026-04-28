from usuarios.models import UserProfile
import os
from django.conf import settings


def vocabulario(request):
    """Context processor que inyecta el vocabulario dinámico según el tipo de negocio del usuario"""
    
    contexto = {
        'vocab': {}
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
