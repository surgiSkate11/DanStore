from django.core.management import call_command
from django.db import migrations

# Debe coincidir con CACHES['ratelimit']['LOCATION'] en settings.py.
TABLA_CACHE = 'ratelimit_cache'


def crear_tabla_cache(apps, schema_editor):
    # createcachetable no hace nada si la tabla ya existe.
    call_command('createcachetable', TABLA_CACHE, database=schema_editor.connection.alias)


def borrar_tabla_cache(apps, schema_editor):
    connection = schema_editor.connection
    if TABLA_CACHE in connection.introspection.table_names():
        with connection.cursor() as cursor:
            cursor.execute('DROP TABLE %s' % connection.ops.quote_name(TABLA_CACHE))


class Migration(migrations.Migration):
    """Tabla de la caché que cuenta los intentos por IP (django-ratelimit)."""

    dependencies = [
        ('usuarios', '0010_loginsecurityattempt'),
    ]

    operations = [
        migrations.RunPython(crear_tabla_cache, borrar_tabla_cache),
    ]
