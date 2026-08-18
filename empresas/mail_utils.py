import time
from email.utils import formataddr

from django.conf import settings
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives, get_connection
from django.utils import timezone
from django.utils.html import strip_tags


def _normalizar_cifrado(valor):
    if valor in ('none', 'ssl', 'starttls'):
        return valor
    return 'starttls'


def obtener_config_smtp(config=None, overrides=None):
    overrides = overrides or {}

    def pick(attribute, default=''):
        if attribute in overrides and overrides[attribute] not in (None, ''):
            return overrides[attribute]
        if config is not None:
            value = getattr(config, attribute, None)
            if value not in (None, ''):
                return value
        return getattr(settings, default, '') if isinstance(default, str) and default.isupper() else default

    # FIX: antes esto ignoraba el cifrado guardado en config si 'overrides'
    # traía cualquier otra clave (aunque no incluyera 'smtp_encryption').
    # Ahora usa la misma cadena de prioridad que el resto de los campos:
    # overrides > config (ConfiguracionSaaS) > default.
    encryption = _normalizar_cifrado(pick('smtp_encryption', None))

    port = overrides.get('smtp_port') if overrides else getattr(config, 'smtp_port', None)
    if port in (None, ''):
        port = {'none': 25, 'ssl': 465, 'starttls': 587}[encryption]

    host = pick('smtp_host', 'EMAIL_HOST')
    username = pick('smtp_user', 'EMAIL_HOST_USER')
    password = pick('smtp_password', 'EMAIL_HOST_PASSWORD')
    timeout = getattr(settings, 'EMAIL_TIMEOUT', 10)

    return {
        'host': host,
        'port': int(port),
        'username': username,
        'password': password,
        'use_tls': encryption == 'starttls',
        'use_ssl': encryption == 'ssl',
        'timeout': timeout,
        'encryption': encryption,
        'from_name': overrides.get('smtp_from_name') or getattr(config, 'smtp_from_name', '') or getattr(settings, 'DEFAULT_FROM_EMAIL', 'Tiendita SaaS'),
        'from_email': overrides.get('smtp_from_email') or getattr(config, 'smtp_from_email', '') or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@tiendita.local'),
        'test_mode': bool(overrides.get('smtp_test_mode', getattr(config, 'smtp_test_mode', False))),
        'test_recipient': overrides.get('smtp_test_recipient') or getattr(config, 'smtp_test_recipient', ''),
        'retry_attempts': int(overrides.get('smtp_retry_attempts') or getattr(config, 'smtp_retry_attempts', 3) or 3),
        'retry_delay_seconds': int(overrides.get('smtp_retry_delay_seconds') or getattr(config, 'smtp_retry_delay_seconds', 2) or 2),
        'max_attachment_mb': int(overrides.get('smtp_max_attachment_mb') or getattr(config, 'smtp_max_attachment_mb', 25) or 25),
        'daily_limit': int(overrides.get('smtp_daily_limit') or getattr(config, 'smtp_daily_limit', 500) or 500),
    }


def construir_remitente(nombre, correo):
    if nombre and correo:
        return formataddr((nombre, correo))
    if correo:
        return correo
    return getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@tiendita.local')


def enviar_correo_saas(subject, body, recipients, *, html_message=None, config=None, overrides=None, attachments=None, fail_silently=False):
    # FIX CRÍTICO: ninguna vista del proyecto (reseteo de contraseña, recuperación
    # de usuario, verificación de email) pasaba 'config' explícitamente. Sin esto,
    # obtener_config_smtp() nunca leía ConfiguracionSaaS y caía siempre a las
    # variables EMAIL_* de settings.py, ignorando el SMTP configurado en el panel.
    if config is None:
        from .models import ConfiguracionSaaS
        config = ConfiguracionSaaS.objects.first()

    smtp = obtener_config_smtp(config=config, overrides=overrides)
    final_recipients = list(recipients)
    if smtp['test_mode'] and smtp['test_recipient']:
        final_recipients = [smtp['test_recipient']]

    total_attachment_bytes = 0
    if attachments:
        for attachment in attachments:
            if hasattr(attachment, 'size') and attachment.size:
                total_attachment_bytes += int(attachment.size)
                max_bytes = smtp['max_attachment_mb'] * 1024 * 1024
                if attachment.size > max_bytes:
                    raise ValueError(f'El adjunto supera el límite de {smtp["max_attachment_mb"]} MB.')
        if total_attachment_bytes > smtp['max_attachment_mb'] * 1024 * 1024:
            raise ValueError(f'El mensaje completo supera el límite de {smtp["max_attachment_mb"]} MB.')

    today_key = f"saas:smtp:daily:{timezone.localdate().isoformat()}"
    current_count = cache.get(today_key, 0)
    intended_count = max(1, len(final_recipients))
    if smtp['test_mode'] and smtp['test_recipient']:
        intended_count = 1
    if current_count + intended_count > smtp['daily_limit']:
        raise ValueError(f'Se alcanzó el límite diario de {smtp["daily_limit"]} correos.')

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=construir_remitente(smtp['from_name'], smtp['from_email']),
        to=final_recipients,
    )

    if html_message:
        message.attach_alternative(html_message, 'text/html')

    if attachments:
        for attachment in attachments:
            message.attach(attachment)

    attempts = max(1, smtp['retry_attempts'])
    last_error = None
    for attempt in range(attempts):
        connection = None
        try:
            # Crear una conexión nueva para cada intento
            connection = get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=smtp['host'],
                port=smtp['port'],
                username=smtp['username'],
                password=smtp['password'],
                use_tls=smtp['use_tls'],
                use_ssl=smtp['use_ssl'],
                timeout=smtp['timeout'],
                fail_silently=fail_silently,
            )
            message.connection = connection
            sent_count = message.send()
            if sent_count:
                cache.set(today_key, current_count + sent_count, timeout=86400)
            return sent_count  # Éxito, salir de la función
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(max(0, smtp['retry_delay_seconds']))
        finally:
            # Cerrar siempre la conexión de este intento
            if connection:
                connection.close()

    if last_error and not fail_silently:
        raise last_error
    return 0