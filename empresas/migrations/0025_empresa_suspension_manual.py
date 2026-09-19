from django.db import migrations, models


def marcar_suspensiones_existentes(apps, schema_editor):
    Empresa = apps.get_model('empresas', 'Empresa')
    Empresa.objects.filter(activa=False).update(suspension_manual=True)


class Migration(migrations.Migration):

    dependencies = [
        ('empresas', '0024_remove_empresa_session_timeout'),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='suspension_manual',
            field=models.BooleanField(
                default=False,
                help_text='Indica que la empresa fue suspendida manualmente por un administrador.',
                verbose_name='Suspensión administrativa',
            ),
        ),
        migrations.RunPython(
            marcar_suspensiones_existentes,
            migrations.RunPython.noop,
        ),
    ]