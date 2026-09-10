from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


# --- Duración de sesión global definida por el dueño del software ---
SESSION_TIMEOUT_CACHE_KEY = 'saas_session_timeout'
SESSION_TIMEOUT_CACHE_TTL_SEGUNDOS = 300
SESSION_TIMEOUT_DEFAULT_MINUTOS = 1440

def _obtener_session_timeout_minutos():
    """
    Devuelve la duración global configurada por el superadmin.
    """
    def _leer_de_bd():
        from .models import ConfiguracionSaaS
        valor = ConfiguracionSaaS.objects.values_list('session_timeout', flat=True).first()
        return valor or SESSION_TIMEOUT_DEFAULT_MINUTOS

    return cache.get_or_set(SESSION_TIMEOUT_CACHE_KEY, _leer_de_bd, SESSION_TIMEOUT_CACHE_TTL_SEGUNDOS)


class TenantMiddleware(MiddlewareMixin):
    """
    Asigna la empresa activa a cada petición y garantiza el aislamiento de datos.
    """
    def process_request(self, request):
        request.empresa = None
        request.rol = None

        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return

        if not request.user.is_authenticated:
            return

        try:
            minutos = _obtener_session_timeout_minutos()
            expiry_seconds = minutos * 60
            # Evita escribir la sesión en cada request si la política no cambió.
            if request.session.get('_session_expiry') != expiry_seconds:
                request.session.set_expiry(expiry_seconds)
            request.session_expiry_seconds = request.session.get_expiry_age()

            # La empresa y la suscripción se resuelven en una sola consulta.
            from usuarios.models import UserProfile
            perfil = UserProfile.objects.select_related('empresa', 'empresa__suscripcion').filter(user=request.user).first()

            # El rol se asigna siempre que exista perfil, sin importar si tiene empresa.
            # Antes solo se asignaba dentro del bloque de empresa, dejando a los
            # superadmins (sin empresa) sin rol_usuario disponible en los templates.
            if perfil:
                request.rol = perfil.rol

            # Si el empleado tiene este flag, no puede navegar por el sistema hasta que la cambie.
            if perfil and perfil.debe_cambiar_password:
                # El usuario solo puede ir a la página de cambio de pass o desloguearse.
                allowed_paths = [reverse('logout'), reverse('forzar_cambio_password')]
                if request.path not in allowed_paths:
                    return redirect('forzar_cambio_password')

            if perfil and perfil.empresa:
                empresa = perfil.empresa
                request.empresa = empresa

                suspendida_admin = not empresa.activa
                suspendida_pago = hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() <= 0

                if suspendida_admin or suspendida_pago:
                    try:
                        rutas_permitidas = [reverse('logout'), reverse('cuenta_suspendida'), reverse('crear_ticket')]
                    except Exception:
                        rutas_permitidas = ['/logout/', '/empresa/suspendida/', '/empresa/soporte/crear/']

                    if request.path not in rutas_permitidas and not request.path.startswith('/admin/'):
                        return redirect('cuenta_suspendida')

        except Exception:
            request.session_expiry_seconds = None

    def process_response(self, request, response):
        segundos = getattr(request, 'session_expiry_seconds', None)
        if segundos is not None and request.user.is_authenticated:
            response['X-Session-Expires-In'] = str(max(0, int(segundos)))
        return response
