from django.db import migrations

from empresas.fields import EncryptedTextField, encrypt_secret


SECRET_FIELDS = [
    'smtp_password',
    'stripe_secret_key',
    'paypal_secret_key',
    'payphone_token',
    'mercadopago_token',
    'coinbase_api_key',
    'razorpay_key_secret',
]


def encrypt_existing_secret_values(apps, schema_editor):
    ConfiguracionSaaS = apps.get_model('empresas', 'ConfiguracionSaaS')
    table_name = ConfiguracionSaaS._meta.db_table
    connection = schema_editor.connection

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, {', '.join(SECRET_FIELDS)} FROM {table_name}"
        )
        rows = cursor.fetchall()

    if not rows:
        return

    with connection.cursor() as cursor:
        for row in rows:
            record_id = row[0]
            current_values = dict(zip(SECRET_FIELDS, row[1:]))
            updates = {}

            for field_name, value in current_values.items():
                if value in (None, ''):
                    continue
                if isinstance(value, str) and value.startswith('fernet:'):
                    continue
                updates[field_name] = encrypt_secret(value)

            if not updates:
                continue

            set_clause = ', '.join(f'{field_name} = %s' for field_name in updates)
            params = list(updates.values()) + [record_id]
            cursor.execute(
                f"UPDATE {table_name} SET {set_clause} WHERE id = %s",
                params,
            )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ('empresas', '0017_configuracionsaas_smtp_daily_limit_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configuracionsaas',
            name='stripe_secret_key',
            field=EncryptedTextField(blank=True, verbose_name='Stripe Secret Key'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='paypal_secret_key',
            field=EncryptedTextField(blank=True, verbose_name='PayPal Secret Key'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='payphone_token',
            field=EncryptedTextField(blank=True, verbose_name='PayPhone Bearer Token'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='smtp_password',
            field=EncryptedTextField(blank=True, verbose_name='Contraseña SMTP'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='mercadopago_token',
            field=EncryptedTextField(blank=True, verbose_name='MercadoPago Access Token'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='coinbase_api_key',
            field=EncryptedTextField(blank=True, verbose_name='Coinbase API Key'),
        ),
        migrations.AlterField(
            model_name='configuracionsaas',
            name='razorpay_key_secret',
            field=EncryptedTextField(blank=True, verbose_name='Razorpay Key Secret'),
        ),
        migrations.RunPython(encrypt_existing_secret_values, reverse_code=noop_reverse),
    ]
