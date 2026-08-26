"""
Helpers de permisos para usuarios.

``is_superuser`` (booleano nativo de Django) es la ÚNICA fuente de verdad
para "es superadministrador del sistema". No existe un segundo campo de
texto que pueda desincronizarse: ``UserProfile.rol`` describe roles de
TENANT (owner/employee/cliente) únicamente y nunca vale 'superadmin'.
"""


def es_superadmin(user):
    """True si el usuario es superadministrador global del SaaS."""
    return bool(user and getattr(user, 'is_authenticated', False) and user.is_superuser)