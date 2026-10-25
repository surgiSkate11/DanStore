from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.db import transaction
from productos.models import Producto
from empresas.models import Empresa
from clientes.models import Cliente


CENTAVO = Decimal('0.01')


def redondear_dinero(valor):
    """Redondea a centavos con ROUND_HALF_UP (0.045 -> 0.05)."""
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


class Venta(models.Model):
    """Modelo de ventas/facturas - Solo se crean cuando hay pago"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='ventas')
    
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
    nombre_cliente = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='Nombre del cliente'
    )
    
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name='ventas', verbose_name="Cliente")
    fecha = models.DateTimeField(default=timezone.now, verbose_name="Fecha de venta")
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Subtotal")
    iva = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="IVA")
    porcentaje_iva = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Porcentaje de IVA aplicado",
        validators=[
            MinValueValidator(0, message="El porcentaje de IVA no puede ser negativo."),
            MaxValueValidator(30, message="El porcentaje de IVA no puede ser mayor a 30."),
        ],
        help_text="Se guarda al facturar. Vacío en ventas antiguas cuyo porcentaje no se conoce.",
    )
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Descuento")
    envio = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Costo de envío")
    otros_gastos = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Otros gastos")
    descripcion_otros = models.CharField(max_length=200, blank=True, verbose_name="Descripción otros gastos")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Total")
    notas = models.TextField(blank=True, verbose_name="Notas de la venta")
    
    ORIGEN_CHOICES = [
        ('sistema', 'Sistema / Manual'),
        ('sheets', 'Google Sheets'),
    ]
    origen = models.CharField(
        max_length=20, choices=ORIGEN_CHOICES, default='sistema', verbose_name="Origen"
    )
    
    ESTADO_CHOICES = [
        ('completada', 'Completada'),
        ('anulada', 'Anulada'),
    ]
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default='completada', verbose_name="Estado"
    )
    
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    actualizado_en = models.DateTimeField(auto_now=True, verbose_name="Actualizado")
    
    class Meta:
        verbose_name = "Venta"
        verbose_name_plural = "Ventas"
        ordering = ['-fecha', '-creado_en']
        unique_together = ('empresa', 'numero_factura')
    
    def __str__(self):
        return f"Factura {self.numero_factura} - {self.cliente.nombre} - ${self.total}"
    
    def save(self, *args, **kwargs):
        """Generar número de factura antes de guardar"""
        if not self.numero_factura:
            self.numero_factura = self._generar_numero()
        super().save(*args, **kwargs)
    
    def _generar_numero(self):
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
        """Única fuente del cálculo de la factura (los precios de producto no incluyen IVA).

        subtotal = suma de los precios de los detalles
        base     = subtotal - descuento (nunca menor que 0)
        iva      = base * porcentaje_iva / 100
        total    = base + iva + envío + otros gastos (estos dos sin IVA, ver L8)

        El porcentaje queda guardado en la venta la primera vez; después no se
        vuelve a leer la configuración, así editar una factura vieja no la recalcula.
        """
        resultado = self.detalles.aggregate(suma_total=models.Sum('precio_unitario'))
        subtotal = redondear_dinero(resultado['suma_total'] or 0)

        if self.porcentaje_iva is None:
            config = ConfiguracionFactura.obtener_configuracion(self.empresa_id)
            self.porcentaje_iva = Decimal(str(config.porcentaje_iva or '0'))

        base_imponible = max(subtotal - self.descuento, Decimal('0'))
        iva = redondear_dinero(base_imponible * self.porcentaje_iva / Decimal('100'))

        self.subtotal = subtotal
        self.iva = iva
        # El envío y los otros gastos se suman sin IVA (confirmado por el dueño, ver L8).
        self.total = redondear_dinero(base_imponible + iva + self.envio + self.otros_gastos)

        self.save(update_fields=[
            'subtotal', 'iva', 'total', 'porcentaje_iva',
            'descuento', 'envio', 'otros_gastos', 'actualizado_en',
        ])

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
        return f"{self.producto.tipo_producto} - ${self.precio_unitario}"


class ConfiguracionFactura(models.Model):
    """Configuración personalizable para facturas"""
    empresa = models.OneToOneField(Empresa, on_delete=models.CASCADE, related_name='configuracion_factura')
    nombre_empresa = models.CharField(max_length=200, default="Tiendita", verbose_name="Nombre de la empresa")
    nombre_personalizado = models.BooleanField(default=False, verbose_name="Nombre personalizado manualmente")
    ruc_empresa = models.CharField(max_length=20, blank=True, verbose_name="RUC de la empresa")
    direccion_empresa = models.TextField(blank=True, verbose_name="Dirección")
    telefono_empresa = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    email_empresa = models.EmailField(blank=True, verbose_name="Email")
    
    # Configuración de Impuestos y Cliente por defecto
    porcentaje_iva = models.DecimalField(
        max_digits=5, decimal_places=2, default=15.00, verbose_name="Porcentaje de IVA",
        validators=[
            MinValueValidator(0, message="El porcentaje de IVA no puede ser negativo."),
            MaxValueValidator(30, message="El porcentaje de IVA no puede ser mayor a 30."),
        ],
    )
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
        if not config.nombre_personalizado:
            # OPTIMIZACIÓN 3: Consultar solo el nombre de la empresa para evitar un objeto completo
            empresa_nombre = Empresa.objects.filter(id=empresa_id).values_list('nombre', flat=True).first()
            if empresa_nombre and config.nombre_empresa != empresa_nombre:
                config.nombre_empresa = empresa_nombre
                config.save(update_fields=['nombre_empresa', 'actualizado_en'])
            
        return config
