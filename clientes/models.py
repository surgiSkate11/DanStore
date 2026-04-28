from django.db import models
from empresas.models import Empresa

class Cliente(models.Model):
    """
    Modelo de Cliente con soporte multitenant.
    Un cliente puede pertenecer a varias empresas (relación muchos a muchos).
    """
    nombre = models.CharField(max_length=200, verbose_name='Nombres completos')
    ruc_cedula = models.CharField(max_length=20, unique=True, verbose_name='Cédula o RUC')
    
    email = models.EmailField(blank=True, null=True, verbose_name='Correo electrónico')
    telefono = models.CharField(max_length=50, blank=True, null=True, verbose_name='Teléfono')
    direccion = models.TextField(blank=True, null=True, verbose_name='Dirección')
    
    # Soporte multitenant: un cliente puede realizar compras en múltiples negocios
    empresas = models.ManyToManyField(Empresa, related_name='clientes', blank=True)
    
    notas = models.TextField(blank=True, null=True, verbose_name='Notas')
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']

    def __str__(self):
        return f"{self.nombre} - {self.ruc_cedula}"

    def cantidad_ventas(self):
        """Retorna la cantidad de ventas asociadas a este cliente."""
        from ventas.models import Venta
        return Venta.objects.filter(cliente=self).count()

    def total_compras(self):
        """Suma de todas las compras del cliente, requerida para reportes y sorteos."""
        from ventas.models import Venta
        from django.db.models import Sum
        return Venta.objects.filter(cliente=self).aggregate(total=Sum('total'))['total'] or 0