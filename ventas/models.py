from django.db import models
from django.utils import timezone
from productos.models import Producto
from empresas.models import Empresa
from clientes.models import Cliente


class Venta(models.Model):
    """Modelo de ventas/facturas - Solo se crean cuando hay pago"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, default=1, related_name='ventas')
    
    # CAMBIO 3.1: Numeración oficial
    numero_factura = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Número de factura"
    )
    
    # CAMBIO 3.1: Método de pago
    METODO_PAGO = [
        ('efectivo', 'Efectivo'),
        ('transferencia', 'Transferencia'),
        ('tarjeta', 'Tarjeta'),
        ('otro', 'Otro'),
    ]
    metodo_pago = models.CharField(
        max_length=20,
        choices=METODO_PAGO,
        default='efectivo',
        verbose_name="Método de pago"
    )
    
    # CAMBIO 3.1: RUC/cédula fiscal
    ruc_cliente = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="RUC / Cédula del cliente"
    )
    
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
        return f"Factura {self.numero_factura} - {self.cliente.nombre} - ${self.total}"
    
    def save(self, *args, **kwargs):
        """Generar número de factura antes de guardar"""
        if not self.numero_factura:
            self.numero_factura = self._generar_numero()
        super().save(*args, **kwargs)
    
# ventas/models.py — reemplaza _generar_numero():
    def _generar_numero(self):
        from django.db import transaction
        with transaction.atomic():
            # Ordenar por numero_factura es más confiable que por fecha
            ultima = (
                Venta.objects.filter(empresa=self.empresa)
                .select_for_update()
                .exclude(numero_factura='')
                .order_by('-id')  # id es siempre único y creciente
                .first()
            )
            if ultima and ultima.numero_factura:
                try:
                    ultimo_num = int(ultima.numero_factura.split('-')[-1])
                except ValueError:
                    ultimo_num = 0
            else:
                ultimo_num = 0
            return f"FAC-{str(ultimo_num + 1).zfill(6)}"
    
    def calcular_total(self):
        """Calcula el total de la venta"""
        self.subtotal = sum(detalle.precio_unitario for detalle in self.detalles.all())
        self.total = self.subtotal - self.descuento + self.envio + self.otros_gastos
        self.save()
    
    
    def cantidad_productos(self):
        """Cuenta la cantidad de productos en la venta"""
        return self.detalles.count()

    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        unique_together = ('empresa', 'numero_factura')


class DetalleVenta(models.Model):
    """Detalle de productos en cada venta"""
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles', verbose_name="Venta")
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, verbose_name="Producto")
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio")
    
    class Meta:
        verbose_name = "Detalle de Venta"
        verbose_name_plural = "Detalles de Venta"
    
    def __str__(self):
        return f"{self.producto.tipo_producto} - ${self.precio_unitario}"


class ConfiguracionFactura(models.Model):
    """Configuración personalizable para facturas"""
    empresa = models.OneToOneField(Empresa, on_delete=models.CASCADE, default=1, related_name='configuracion_factura')
    nombre_empresa = models.CharField(max_length=200, default="Tiendita", verbose_name="Nombre de la empresa")
    nombre_personalizado = models.BooleanField(default=False, verbose_name="Nombre personalizado manualmente")
    ruc_empresa = models.CharField(max_length=20, blank=True, verbose_name="RUC de la empresa")
    direccion_empresa = models.TextField(blank=True, verbose_name="Dirección")
    telefono_empresa = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    email_empresa = models.EmailField(blank=True, verbose_name="Email")
    logo = models.ImageField(upload_to='facturas/logos/', blank=True, null=True, verbose_name="Logo de la empresa")
    
    # Configuración de Impuestos y Cliente por defecto
    porcentaje_iva = models.DecimalField(max_digits=5, decimal_places=2, default=15.00, verbose_name="Porcentaje de IVA")
    texto_consumidor_final = models.CharField(max_length=100, default="CONSUMIDOR FINAL", verbose_name="Texto Consumidor Final")
    id_consumidor_final = models.CharField(max_length=20, default="9999999999", verbose_name="ID Consumidor Final")
    
    # Información adicional
    mensaje_factura = models.TextField(blank=True, verbose_name="Mensaje en factura", 
                                       help_text="Mensaje que aparece al pie de la factura")
    mensaje_deuda = models.TextField(blank=True, verbose_name="Mensaje para deudas", 
                                       help_text="Mensaje predeterminado al compartir comprobantes de deuda por WhatsApp")
    
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Configuración de Factura"
        verbose_name_plural = "Configuración de Facturas"
    
    def __str__(self):
        return f"Configuración de {self.nombre_empresa}"
    
    @classmethod
    def obtener_configuracion(cls, empresa_id):
        """Obtiene o crea la configuración para la empresa"""
        config, created = cls.objects.get_or_create(empresa_id=empresa_id)
        
        # Sincronizar automáticamente si NO ha sido personalizado y es distinto al de la BD principal
        if config.empresa and not config.nombre_personalizado and config.nombre_empresa != config.empresa.nombre:
            config.nombre_empresa = config.empresa.nombre
            config.save(update_fields=['nombre_empresa'])
            
        return config
