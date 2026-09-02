import unicodedata

from django.db import migrations, models


def normalizar(valor):
    texto = unicodedata.normalize('NFKD', str(valor or ''))
    return ''.join(
        caracter for caracter in texto
        if not unicodedata.combining(caracter)
    ).casefold()


def rellenar_texto_busqueda(apps, schema_editor):
    Producto = apps.get_model('productos', 'Producto')
    productos = Producto.objects.select_related('tipo_producto').all()

    for producto in productos.iterator():
        valores = [
            producto.nombre,
            producto.descripcion,
            producto.marca,
            producto.categoria,
            producto.variante,
            producto.color,
            producto.vendido_a,
        ]
        if producto.tipo_producto_id and producto.tipo_producto:
            valores.append(producto.tipo_producto.nombre)
        producto.texto_busqueda = normalizar(' '.join(
            str(valor or '') for valor in valores
        ))
        producto.save(update_fields=['texto_busqueda'])


class Migration(migrations.Migration):

    dependencies = [
        ('productos', '0005_alter_producto_nombre_alter_producto_precio'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='texto_busqueda',
            field=models.TextField(
                blank=True,
                db_index=True,
                default='',
                editable=False,
                verbose_name='Texto de búsqueda normalizado',
            ),
        ),
        migrations.RunPython(
            rellenar_texto_busqueda,
            migrations.RunPython.noop,
        ),
    ]