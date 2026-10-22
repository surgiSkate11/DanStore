import ipaddress

from django.contrib import messages
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.html import strip_tags


def form_errors_to_messages(request, form):
    """
    Itera sobre los errores de un formulario (field y non_field) 
    y los agrega al sistema de mensajes de Django (toasts).
    """
    # Errores generales (Rojos)
    for error in form.non_field_errors():
        messages.error(request, strip_tags(error))
        
    # Errores específicos de un input (Amarillos - Advertencias)
    for field in form:
        for error in field.errors:
            messages.warning(request, f"{field.label}: {strip_tags(error)}")


def cerrar_sesiones_de_usuario(user):
    """
    Busca y elimina de la base de datos todas las sesiones activas de un
    usuario (usado al cambiar username/email/password, y al desactivar
    o eliminar un empleado).

    Implementación ÚNICA y centralizada. Antes existía duplicada como
    `_invalidar_sesiones_de_usuario` en empresas/views.py y
    `cerrar_todas_las_sesiones` en usuarios/views.py — ambas con el
    mismo cuerpo. Se centraliza acá porque ninguna de las dos apps
    depende de la otra para esta operación.
    """
    sesiones_activas = Session.objects.filter(expire_date__gte=timezone.now())
    for sesion in sesiones_activas:
        data = sesion.get_decoded()
        if str(user.pk) == str(data.get('_auth_user_id', '')):
            sesion.delete()


def obtener_ip_cliente(request):
    """
    IP real del cliente para el límite de intentos (RATELIMIT_IP_META_KEY).

    En Render el camino es Cliente -> Cloudflare -> proxy de Render -> app. El
    último valor de X-Forwarded-For lo agrega el proxy de Render: es quien se
    conectó de verdad. Si es un borde de Cloudflare, la IP del cliente viene en
    CF-Connecting-IP (o True-Client-IP). Si no lo es, alguien entró directo a
    Render saltando Cloudflare, y esos headers los escribió él: se usa su IP real.
    Sin X-Forwarded-For (desarrollo local) se usa REMOTE_ADDR.
    """
    par = _ip_valida(request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[-1])
    if par is None:
        return request.META.get('REMOTE_ADDR', '')
    if not any(par in red for red in _REDES_CLOUDFLARE):
        return str(par)
    for header in ('HTTP_CF_CONNECTING_IP', 'HTTP_TRUE_CLIENT_IP'):
        cliente = _ip_valida(request.META.get(header, ''))
        if cliente is not None:
            return str(cliente)
    return request.META.get('REMOTE_ADDR', '')


def _ip_valida(valor):
    try:
        return ipaddress.ip_address(valor.strip())
    except ValueError:
        return None


# Rangos publicados en https://www.cloudflare.com/ips/ (revisados 2026-10-21).
_REDES_CLOUDFLARE = [ipaddress.ip_network(red) for red in (
    '173.245.48.0/20', '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22',
    '141.101.64.0/18', '108.162.192.0/18', '190.93.240.0/20', '188.114.96.0/20',
    '197.234.240.0/22', '198.41.128.0/17', '162.158.0.0/15', '104.16.0.0/13',
    '104.24.0.0/14', '172.64.0.0/13', '131.0.72.0/22',
    '2400:cb00::/32', '2606:4700::/32', '2803:f800::/32', '2405:b500::/32',
    '2405:8100::/32', '2a06:98c0::/29', '2c0f:f248::/32',
)]

