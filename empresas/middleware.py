from django.shortcuts import redirect
from django.urls import reverse
from django.utils.deprecation import MiddlewareMixin


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