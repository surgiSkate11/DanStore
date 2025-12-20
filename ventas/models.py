from django.db import models
from django.utils import timezone
from productos.models import Producto


class Cliente(models.Model):
    """Modelo de clientes para gestión de ventas"""
    nombre = models.CharField(max_length=200, unique=True, verbose_name="Nombre completo")
    telefono = models.CharField(max_length=20, blank=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, verbose_name="Email")
    direccion = models.TextField(blank=True, verbose_name="Dirección")
    notas = models.TextField(blank=True, verbose_name="Notas adicionales")
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de registro")
    
    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre
    
    def total_compras(self):
        """Calcula el total de compras del cliente"""
        return self.ventas.aggregate(models.Sum('total'))['total__sum'] or 0
    
    def cantidad_ventas(self):
        """Cuenta las ventas del cliente"""
        return self.ventas.count()


class Venta(models.Model):
    """Modelo de ventas/facturas - Solo se crean cuando hay pago"""
    
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='ventas', verbose_name="Cliente")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de venta")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Descuento")
    envio = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Costo de envío")
    otros_gastos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Otros gastos")
    descripcion_otros = models.CharField(max_length=200, blank=True, verbose_name="Descripción otros gastos")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    notas = models.TextField(blank=True, verbose_name="Notas de la venta")
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Actualizado")
    
    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha', '-creado_en']
    
    def __str__(self):
        return f"Venta #{self.id} - {self.cliente.nombre} - ${self.total}"
    
    def calcular_total(self):
        """Calcula el total de la venta"""
        self.subtotal = sum(detalle.precio_unitario for detalle in self.detalles.all())
        self.total = self.subtotal - self.descuento + self.envio + self.otros_gastos
        self.save()
    
    def numero_factura(self):
        """Genera número de factura formateado"""
        return f"FAC-{self.id:06d}"
    
    def cantidad_productos(self):
        """Cuenta la cantidad de productos en la venta"""
        return self.detalles.count()


class DetalleVenta(models.Model):
    """Detalle de productos en cada venta"""
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles', verbose_name="Venta")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, verbose_name="Producto")
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio")
    
    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Venta"
    
    def __str__(self):
        return f"{self.producto.tipo_prenda} - ${self.precio_unitario}"


class ConfiguracionFactura(models.Model):
    """Configuración personalizable para facturas"""
    # Solo habrá un registro (singleton)
    nombre_empresa = models.CharField(max_length=200, default="Tiendita", verbose_name="Nombre de la empresa")
    direccion_empresa = models.TextField(blank=True, verbose_name="Dirección")
    telefono_empresa = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    email_empresa = models.EmailField(blank=True, verbose_name="Email")
    logo = models.ImageField(upload_to='facturas/logos/', blank=True, null=True, verbose_name="Logo de la empresa")
    
    # Colores personalizables
    color_borde = models.CharField(max_length=7, default="#667eea", verbose_name="Color del borde lateral")
    color_principal = models.CharField(max_length=7, default="#667eea", verbose_name="Color principal")
    color_texto = models.CharField(max_length=7, default="#333333", verbose_name="Color del texto")
    
    # Información adicional
    mensaje_factura = models.TextField(blank=True, verbose_name="Mensaje en factura", 
                                       help_text="Mensaje que aparece al pie de la factura")
    
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Configuración de Factura"
        verbose_name_plural = "Configuración de Facturas"
    
    def __str__(self):
        return f"Configuración de {self.nombre_empresa}"
    
    @classmethod
    def obtener_configuracion(cls):
        """Obtiene o crea la configuración única"""
        config, created = cls.objects.get_or_create(pk=1)
        return config
