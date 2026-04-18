from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from productos.models import Producto, TipoPrenda
from ventas.models import Cliente
from decimal import Decimal
import random
from django.utils import timezone


class Command(BaseCommand):
    help = 'Carga datos de demostración en la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            'user_id',
            type=int,
            help='ID del usuario para cargar demo data'
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Elimina la demo data existente antes de cargar'
        )

    def handle(self, *args, **options):
        user_id = options['user_id']
        
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Usuario con ID {user_id} no encontrado')
            )
            return

        # Si está el flag --clear, eliminar demo data
        if options['clear']:
            Producto.objects.filter(sincronizado_sheets=False).delete()
            Cliente.objects.all().delete()
            user.profile.usa_demo_data = False
            user.profile.save()
            self.stdout.write(
                self.style.SUCCESS('Demo data eliminada')
            )
            return

        # Crear tipos de prendas si no existen
        tipos = [
            'Remera', 'Pantalón', 'Vestido', 'Campera', 'Shorts',
            'Falda', 'Blusa', 'Sweater', 'Abrigo', 'Chaleco'
        ]
        
        tipo_objects = []
        for tipo in tipos:
            obj, _ = TipoPrenda.objects.get_or_create(nombre=tipo)
            tipo_objects.append(obj)

        # Datos de productos ficticios (para ropa)
        productos_data = [
            {'nombre': 'Remera básica negra', 'precio': Decimal('15.00')},
            {'nombre': 'Remera básica blanca', 'precio': Decimal('15.00')},
            {'nombre': 'Pantalón jean azul', 'precio': Decimal('35.00')},
            {'nombre': 'Pantalón jean negro', 'precio': Decimal('35.00')},
            {'nombre': 'Vestido floral', 'precio': Decimal('45.00')},
            {'nombre': 'Campera de cuero', 'precio': Decimal('80.00')},
            {'nombre': 'Shorts deportivos', 'precio': Decimal('25.00')},
            {'nombre': 'Falda plisada', 'precio': Decimal('40.00')},
            {'nombre': 'Blusa elegante', 'precio': Decimal('50.00')},
            {'nombre': 'Sweater gris', 'precio': Decimal('45.00')},
        ]

        # Crear productos
        colores = ['Negro', 'Blanco', 'Azul', 'Rojo', 'Verde', 'Rosa', 'Gris', 'Beige']
        categorias = ['nina', 'joven', 'adulto_mujer']
        
        for i, prod_data in enumerate(productos_data):
            Producto.objects.create(
                tipo_prenda=random.choice(tipo_objects),
                nombre=prod_data['nombre'],
                precio=prod_data['precio'],
                color=random.choice(colores),
                categoria_grupo=random.choice(categorias),
                rango_edad='M',  # Medium genérico
                estado='disponible',
                descripcion=f'Producto de demostración {i+1}',
                sincronizado_sheets=False
            )

        # Crear clientes de prueba
        clientes_nombres = [
            'María García',
            'Sofia López',
            'Julieta Martínez',
            'Ana Pérez',
            'Laura Rodríguez',
            'Claudia Fernández',
            'Martina González',
            'Valentina Díaz',
        ]

        clientes_objs = []
        for nombre in clientes_nombres:
            cliente, _ = Cliente.objects.get_or_create(
                nombre=nombre,
                defaults={
                    'telefono': f'11{random.randint(20000000, 99999999)}',
                    'email': f'{nombre.lower().replace(" ", ".")}@email.com'
                }
            )
            clientes_objs.append(cliente)

        # Marcar algunos productos como separados
        productos = list(Producto.objects.filter(sincronizado_sheets=False))
        for _ in range(min(3, len(productos))):
            prod = random.choice(productos)
            prod.estado = 'separado'
            prod.save()
            productos.remove(prod)

        # Actualizar perfil del usuario
        user.profile.usa_demo_data = True
        user.profile.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'✨ Demo data cargada exitosamente:\n'
                f'  • {len(productos_data)} productos creados\n'
                f'  • {len(clientes_objs)} clientes creados\n'
            )
        )
