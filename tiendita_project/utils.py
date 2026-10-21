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

    Detrás del proxy de Railway el último valor de X-Forwarded-For es el que
    agrega el proxy; los anteriores los escribe el cliente y se pueden falsear.
    Sin ese header, o si el valor no es una IP, se usa REMOTE_ADDR.
    """
    reenviadas = request.META.get('HTTP_X_FORWARDED_FOR', '')
    ultima = reenviadas.split(',')[-1].strip()
    if ultima:
        try:
            return str(ipaddress.ip_address(ultima))
        except ValueError:
            pass
    return request.META.get('REMOTE_ADDR', '')

