from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.conf import settings
from django.test import SimpleTestCase
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
