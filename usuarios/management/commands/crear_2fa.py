from base64 import b32encode

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django_otp.plugins.otp_totp.models import TOTPDevice

NOMBRE_DISPOSITIVO = 'admin'


class Command(BaseCommand):
    help = 'Crea el dispositivo TOTP (2FA) de un superusuario para entrar al panel de administración'

    def add_arguments(self, parser):
        parser.add_argument('username', help='Nombre de usuario de un superusuario existente')
        parser.add_argument(
            '--reemplazar',
            action='store_true',
            help='Reemplaza el dispositivo existente por uno nuevo (la app autenticadora deberá configurarse de nuevo)',
        )

    def handle(self, *args, **options):
        username = options['username']
        usuario = get_user_model().objects.filter(**{get_user_model().USERNAME_FIELD: username}).first()
        if usuario is None:
            raise CommandError(f'El usuario "{username}" no existe.')
        if not usuario.is_superuser:
            raise CommandError(f'El usuario "{username}" no es superusuario: el 2FA del panel es solo para superusuarios.')

        with transaction.atomic():
            existentes = TOTPDevice.objects.filter(user=usuario)
            if existentes.exists():
                if not options['reemplazar']:
                    raise CommandError(
                        f'"{username}" ya tiene un dispositivo 2FA. Usa --reemplazar para crear uno nuevo.'
                    )
                existentes.delete()
            dispositivo = TOTPDevice.objects.create(user=usuario, name=NOMBRE_DISPOSITIVO, confirmed=True)

        self.stdout.write(self.style.SUCCESS(f'Dispositivo 2FA creado para "{username}".'))
        self.stdout.write('Escribe esta clave en tu app autenticadora (Google Authenticator, Authy), '
                          'con codificación base32 y basada en tiempo:')
        self.stdout.write(f'Clave: {b32encode(dispositivo.bin_key).decode()}')
        self.stdout.write(f'URL otpauth: {dispositivo.config_url}')
        self.stdout.write(self.style.WARNING('Guarda la clave en un lugar seguro: quien la tenga puede generar tus códigos.'))
