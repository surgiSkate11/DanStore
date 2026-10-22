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

    En Render el camino es Cliente -> Cloudflare -> proxy de Render -> app.
    Cloudflare siempre sobrescribe CF-Connecting-IP con la IP del cliente, por eso
    va primero; True-Client-IP solo es confiable si la zona lo tiene activado.
    X-Forwarded-For no sirve: Render le agrega valores sin limpiarlo, así que
    el cliente lo controla, y su último valor es el borde de Cloudflare,
    compartido por muchos clientes. Sin esos headers (desarrollo local), o si
    el valor no es una IP, se usa REMOTE_ADDR.
    """
    for header in ('HTTP_CF_CONNECTING_IP', 'HTTP_TRUE_CLIENT_IP'):
        valor = request.META.get(header, '').strip()
        if valor:
            try:
                return str(ipaddress.ip_address(valor))
            except ValueError:
                continue
    return request.META.get('REMOTE_ADDR', '')

