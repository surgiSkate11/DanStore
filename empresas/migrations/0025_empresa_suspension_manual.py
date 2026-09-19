from django.db import migrations, models


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
    ]