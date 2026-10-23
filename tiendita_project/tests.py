from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.files.storage import default_storage
from django.core.management import call_command, get_commands
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import formats, timezone, translation


class LocalizacionEcuadorTests(SimpleTestCase):
    def test_idioma_y_zona_horaria_de_ecuador(self):
        self.assertEqual(settings.LANGUAGE_CODE, 'es-ec')
        self.assertEqual(settings.TIME_ZONE, 'America/Guayaquil')
        self.assertTrue(settings.USE_TZ)

    def test_hora_se_muestra_en_hora_de_ecuador(self):
        # 17:00 UTC son las 12:00 en Guayaquil (UTC-5, sin horario de verano).
        momento = datetime(2026, 10, 20, 17, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(timezone.localtime(momento).hour, 12)

    def test_precios_siguen_con_punto_decimal(self):
        with translation.override(settings.LANGUAGE_CODE):
            self.assertEqual(formats.localize(Decimal('1234.50')), '1234.50')
            self.assertEqual(formats.number_format(Decimal('1234.5'), 2, force_grouping=True), '1,234.50')


class MigracionesAlDiaTests(TestCase):
    """Todo cambio de modelo lleva su migración (regla del AGENTS.md)."""

    def test_no_hay_cambios_de_modelo_sin_migracion(self):
        salida = StringIO()
        try:
            call_command('makemigrations', '--check', '--dry-run', stdout=salida, stderr=salida)
        except SystemExit:
            self.fail(f'Hay cambios de modelo sin migración:\n{salida.getvalue()}')


class AlmacenamientoTests(SimpleTestCase):
    """Django 5.1 quitó DEFAULT_FILE_STORAGE y STATICFILES_STORAGE: se usa STORAGES."""

    def test_backends_configurados(self):
        self.assertEqual(
            settings.STORAGES['default']['BACKEND'],
            'cloudinary_storage.storage.MediaCloudinaryStorage',
        )
        self.assertEqual(
            settings.STORAGES['staticfiles']['BACKEND'],
            'whitenoise.storage.CompressedStaticFilesStorage',
        )

    def test_storages_resuelven_a_las_clases_esperadas(self):
        from cloudinary_storage.storage import MediaCloudinaryStorage
        from whitenoise.storage import CompressedStaticFilesStorage

        self.assertIsInstance(default_storage, MediaCloudinaryStorage)
        self.assertIsInstance(staticfiles_storage, CompressedStaticFilesStorage)

    def test_collectstatic_es_el_de_django(self):
        # El de django-cloudinary-storage no copia nada si el almacenamiento estático
        # no es StaticCloudinaryStorage; la app debe ir después de staticfiles.
        self.assertEqual(get_commands()['collectstatic'], 'django.contrib.staticfiles')

    def test_collectstatic_copia_archivos(self):
        with TemporaryDirectory() as destino:
            with override_settings(STATIC_ROOT=destino):
                salida = StringIO()
                call_command('collectstatic', '--noinput', stdout=salida, verbosity=1)
            copiados = [p for p in Path(destino).rglob('*') if p.is_file()]
            self.assertGreater(len(copiados), 0, salida.getvalue())
            self.assertTrue((Path(destino) / 'admin' / 'css' / 'base.css').exists())
