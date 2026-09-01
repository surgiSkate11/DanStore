from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


# --- Duración de sesión configurable por el SuperAdmin (ConfiguracionSaaS.session_timeout) ---
# Es una configuración GLOBAL del SaaS (singleton, id=1), igual que el resto de
# ConfiguracionSaaS: no depende de la empresa/tenant, aplica a todos por igual.
SESSION_TIMEOUT_CACHE_KEY = 'saas_session_timeout'
SESSION_TIMEOUT_CACHE_TTL_SEGUNDOS = 300  # 5 minutos: evita ir a BD en cada request
SESSION_TIMEOUT_DEFAULT_MINUTOS = 1440  # Mismo default que el modelo, por si aún no existe fila

def _obtener_session_timeout_minutos():
    """
    Devuelve la duración de sesión configurada (en MINUTOS), leyendo de una
    caché de corta duración para no golpear la base de datos en cada
    request. La vista `saas_configuracion` invalida esta caché
    (cache.delete('saas_session_timeout')) al guardar un nuevo valor, así
    que el cambio se aplica como máximo con unos minutos de retraso, o de
    inmediato si el admin acaba de guardar.
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

        # Aplica la duración de sesión configurada en ConfiguracionSaaS a
        # CUALQUIER usuario autenticado (superadmin, dueños y empleados).
        # set_expiry() reinicia el conteo en cada request ("rolling
        # session"), por lo que la sesión expira tras N minutos de
        # INACTIVIDAD, no N minutos desde el login. No usamos
        # SESSION_COOKIE_AGE porque esa constante es fija a nivel de
        # settings.py y no puede recargarse en caliente desde este modelo.
        try:
            minutos = _obtener_session_timeout_minutos()
            request.session.set_expiry(minutos * 60)
        except Exception:
            # Nunca debe tumbar la petición por un problema leyendo la
            # configuración de sesión; en el peor caso, Django usa el
            # comportamiento de sesión por defecto.
            pass

        if request.user.is_superuser and request.path.startswith('/admin/'):
            return

        try:
            # OPTIMIZACIÓN EXTREMA: Cargar Perfil, Empresa y Suscripción en UNA sola consulta
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

                suspendida_admin = not empresa.activa
                suspendida_pago = hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() <= 0

                if suspendida_admin or suspendida_pago:
                    try:
                        rutas_permitidas = [reverse('logout'), reverse('cuenta_suspendida'), reverse('crear_ticket')]
                    except Exception:
                        rutas_permitidas = ['/logout/', '/empresa/suspendida/', '/empresa/soporte/crear/']

                    if request.path not in rutas_permitidas and not request.path.startswith('/admin/'):
                        request.empresa = empresa
                        return redirect('cuenta_suspendida')

                request.empresa = empresa
        except Exception as e:
            pass