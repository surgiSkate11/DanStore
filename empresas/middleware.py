from django.utils.deprecation import MiddlewareMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.core.exceptions import PermissionDenied

class TenantMiddleware(MiddlewareMixin):
    """
    Middleware Multi-tenant: Asigna la empresa activa a cada petición.
    Garantiza el aislamiento de datos identificando a qué empresa pertenece el usuario actual.
    """
    def process_request(self, request):
        # Por defecto no hay empresa en el request
        request.empresa = None
        
        # Ignorar rutas estáticas o de media
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return

        # Si no está autenticado, no procesamos la empresa
        if not request.user.is_authenticated:
            return

        # El superusuario y las rutas del admin nativo 
        # pueden funcionar de manera global sin estar atados a una empresa.
        if request.user.is_superuser and request.path.startswith('/admin/'):
            return

        # Obtener el perfil del usuario para identificar su empresa
        try:
            perfil = getattr(request.user, 'profile', None)
            
            if perfil and perfil.empresa:
                empresa = perfil.empresa
                
                # Evaluar motivos de suspensión
                suspendida_admin = not empresa.activa
                suspendida_pago = False
                
                if hasattr(empresa, 'suscripcion') and empresa.suscripcion.dias_restantes() <= 0:
                    suspendida_pago = True
                    
                if suspendida_admin or suspendida_pago:
                    # Permitir solo "Cerrar sesión", "Pantalla de Suspensión" y "Crear Tickets"
                    try:
                        rutas_permitidas = [reverse('logout'), reverse('cuenta_suspendida'), reverse('crear_ticket')]
                    except Exception:
                        rutas_permitidas = ['/logout/', '/empresa/suspendida/', '/empresa/soporte/crear/']
                        
                    if request.path not in rutas_permitidas and not request.path.startswith('/admin/'):
                        request.empresa = empresa # Inyectar para la vista de suspensión
                        return redirect('cuenta_suspendida')
                
                # Inyectar la empresa en el request
                request.empresa = empresa
                request.rol = perfil.rol
            else:
                # Autenticado pero sin empresa y no es ruta del admin
                if not request.user.is_superuser and not request.path.startswith('/admin/'):
                    # El usuario no tiene empresa asignada (y no es superadmin)
                    pass 
                    
        except Exception as e:
            # Manejo preventivo de errores
            pass
