from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ventas', '0005_alter_venta_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='venta',
            name='iva',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='IVA'),
        ),
    ]
