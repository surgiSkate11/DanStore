from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from productos.models import Producto
from ventas.models import Cliente
from clientes.models import Cliente
import random


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

        # Demo data genérico para cualquier negocio
        productos_demo = [
            {
                'nombre': 'Producto de ejemplo 1',
                'categoria': 'General',
                'precio': 25.00,
                'estado': 'disponible',
                'descripcion': 'Este es un producto de ejemplo',
                'variante': 'Talla M',
                'marca': 'Marca Demo',
                'stock': 5,
                'origen': 'manual',
            },
            {
                'nombre': 'Producto de ejemplo 2',
                'categoria': 'General',
                'precio': 45.00,
                'estado': 'disponible',
                'descripcion': 'Otro producto de ejemplo',
                'variante': 'L',
                'marca': 'Marca Demo',
                'stock': 3,
                'origen': 'manual',
            },
            {
                'nombre': 'Producto separado demo',
                'categoria': 'General',
                'precio': 30.00,
                'estado': 'separado',
                'descripcion': 'Producto reservado de ejemplo',
                'variante': 'S',
                'vendido_a': 'Cliente Demo',
                'stock': 1,
                'origen': 'manual',
            },
        ]
        for datos in productos_demo:
            Producto.objects.create(**datos)

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
                    'cedula': f'00000000{random.randint(10,99)}',
                    'telefono': f'11{random.randint(20000000, 99999999)}',
                    'email': f'{nombre.lower().replace(" ", ".")}@email.com'
                }
            )
            clientes_objs.append(cliente)
            if hasattr(user.profile, 'empresa') and user.profile.empresa:
                cliente.empresas.add(user.profile.empresa)

        # Actualizar perfil del usuario
        user.profile.usa_demo_data = True
        user.profile.save()

        self.stdout.write(
            self.style.SUCCESS(
                f'✨ Demo data cargada exitosamente:\n'
                f'  • {len(productos_demo)} productos creados\n'
                f'  • {len(clientes_objs)} clientes creados\n'
            )
        )
