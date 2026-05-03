from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from functools import wraps

class TenantMixin:
    """
    Mixin protector para Vistas Basadas en Clases (CBV).
    Asegura que todos los querysets se filtren de manera predeterminada para que el 
    usuario vea SOLAMENTE los datos de su propia empresa.
    """
    def get_queryset(self):
        qs = super().get_queryset()
        # Automáticamente restringe los objetos a la empresa del usuario actual
        if hasattr(self.request, 'empresa') and self.request.empresa:
            return qs.filter(empresa=self.request.empresa)
        
        # Si el usuario no tiene empresa seteada en el request, devuelve un queryset vacío 
        # por medidas de seguridad, evitando fuga de datos al no ser superadmin.
        if self.request.user.is_superuser:
            return qs  # Solo el dueño podría esquivar esto si accede a una vista general
            
        return qs.none()

    def form_valid(self, form):
        """
        Asigna la empresa automáticamente al objeto al guardarlo desde un formulario
        antes de pasárselo a la base de datos.
        """
        if hasattr(self.request, 'empresa') and self.request.empresa:
            form.instance.empresa = self.request.empresa
        return super().form_valid(form)


def requiere_rol_dueño(view_func):
    """
    Decorador para proteger vistas (Function-Based Views) y asegurar 
    que sólo el dueño de la empresa pueda acceder (Ej: Ver reportes o empleados).
    """
    def _wrapped_view(request, *args, **kwargs):
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            raise PermissionDenied("Debe iniciar sesión.")
            
        if hasattr(request.user, 'profile') and request.user.profile.rol == 'owner':
            return view_func(request, *args, **kwargs)
        elif request.user.is_superuser:
            return view_func(request, *args, **kwargs)
            
        raise PermissionDenied("No tienes permiso, sólo el DUEÑO puede acceder a esta área.")
        
    return _wrapped_view


def requiere_modulo(modulo_codigo, accion='ver'):
    """
    Decorador SaaS: Verifica si la empresa tiene el módulo activo en su plan,
    y si el usuario (si es empleado) tiene permiso asignado para verlo.
    Permite validación granular: 'ver', 'crear', 'editar', 'eliminar'.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not hasattr(request, 'user') or not request.user.is_authenticated:
                raise PermissionDenied("Debe iniciar sesión.")
                
            perfil = getattr(request.user, 'profile', None)
            
            if perfil and perfil.rol in ['superadmin', 'owner']:
                return view_func(request, *args, **kwargs)
                
            if perfil and perfil.rol == 'employee':
                if perfil.rol_empresa and perfil.rol_empresa.modulos_permitidos.filter(codigo__iexact=modulo_codigo).exists():
                    permisos = perfil.rol_empresa.permisos_detallados.get(modulo_codigo, None)
                    
                    # Si es un rol antiguo sin JSON de permisos explícito, por retrocompatibilidad lo dejamos pasar
                    if permisos is not None and accion not in permisos:
                        raise PermissionDenied(f"Tu rol no tiene permiso de '{accion}' en el módulo '{modulo_codigo}'.")
                        
                    return view_func(request, *args, **kwargs)
                raise PermissionDenied(f"Tu rol no tiene acceso al módulo: {modulo_codigo}")
                
            raise PermissionDenied("Acceso denegado.")
        return _wrapped_view
    return decorator
