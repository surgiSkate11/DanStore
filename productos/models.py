from django.db import models
from django.utils import timezone
from empresas.models import Empresa


class TipoProducto(models.Model):
    """
    Catálogo de tipos de producto — genérico para cualquier negocio.
    Ejemplos: Vestido, Laptop, Torta, Servicio de diseño, etc.
    El usuario crea los tipos que necesite desde el admin o la interfaz.
    """
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='tipos_producto')
    nombre = models.CharField(max_length=100, verbose_name='Nombre del tipo')
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Tipo de Producto"
        verbose_name_plural = "Tipos de Producto"
        ordering = ['nombre']
        unique_together = ('empresa', 'nombre')

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    """
    Modelo principal de productos — adaptable a cualquier tipo de negocio.
    Los campos fijos cubren lo universal (precio, estado, imagen, descripción).
    Los campos específicos del negocio van en el JSONField 'atributos'.
    """
    
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='productos')

    # ── ESTADOS (universales para cualquier negocio) ───────────────────────
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('separado', 'Reservado'),     # "Separado" en ropa = "Reservado" en otros
        ('vendido', 'Vendido'),
    ]

    # ── ORIGEN ────────────────────────────────────────────────────────────────
    ORIGEN_CHOICES = [
        ('manual', 'Cargado manualmente'),
        ('excel', 'Importado desde Excel/CSV'),
        ('sheets', 'Sincronizado desde Google Sheets'),
    ]

    # ── IMAGEN ────────────────────────────────────────────────────────────────
    imagen = models.ImageField(
        upload_to='productos/%Y/%m/',
        verbose_name='Imagen',
        null=True,
        blank=True,
        help_text='Foto del producto (opcional)'
    )

    # ── IDENTIFICACIÓN BÁSICA ─────────────────────────────────────────────────
    nombre = models.CharField(
        max_length=200,
        verbose_name='Nombre del producto',
        blank=True,
        help_text='Nombre o título del producto. Ej: Vestido floral, iPhone 15, Torta de chocolate'
    )

    descripcion = models.TextField(
        verbose_name='Descripción',
        blank=True,
        help_text='Descripción adicional del producto'
    )

    # ── CATEGORÍA (libre, el usuario escribe la suya) ─────────────────────────
    categoria = models.CharField(
        max_length=100,
        blank=True,
        default='General',
        verbose_name='Categoría',
        db_index=True,
        help_text='Categoría libre. Ej: General, Mujer, Electrónica, Postres, Servicios, etc.'
    )

    # ── TIPO DE PRODUCTO (FK al catálogo configurable) ────────────────────────
    tipo_producto = models.ForeignKey(
        TipoProducto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Tipo de producto',
        help_text='Tipo específico. Ej: Vestido, Laptop, Torta.'
    )

    # ── VARIANTE (reemplaza rango_edad — sirve para talla, modelo, sabor, etc.) ──
    variante = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Variante',
        help_text='Talla, modelo, sabor, versión, etc. según el negocio. Ej: M, 128GB, Chocolate'
    )

    # ── PRECIO ────────────────────────────────────────────────────────────────
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio de venta',
        db_index=True
    )

    precio_costo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio de costo',
        help_text='Costo del producto (opcional, para calcular margen)'
    )

    # ── ESTADO ────────────────────────────────────────────────────────────────
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible',
        verbose_name='Estado',
        db_index=True
    )

    # ── CLIENTE ASIGNADO (para separados/reservados) ──────────────────────────
    vendido_a = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Asignado a',
        db_index=True,
        help_text='Nombre del cliente al que fue vendido o reservado'
    )

    # ── MARCA / PROVEEDOR (opcional) ──────────────────────────────────────────
    marca = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Marca / Proveedor'
    )

    # ── COLOR (opcional, útil para ropa, gadgets, decoración) ────────────────
    color = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Color'
    )

    # ── STOCK (opcional — para negocios que manejan cantidad) ─────────────────
    stock = models.PositiveIntegerField(
        default=1,
        verbose_name='Stock / Cantidad',
        help_text='Cantidad disponible. Para productos únicos déjalo en 1.'
    )

    # ── ATRIBUTOS DINÁMICOS (el comodín para cualquier campo extra) ───────────
    atributos = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Atributos adicionales',
        help_text=(
            'Campos extra según el negocio. Ejemplos: '
            '{"vencimiento": "2025-12", "peso": "500g"} para alimentos, '
            '{"ram": "16GB", "almacenamiento": "512GB"} para tecnología.'
        )
    )

    # ── GOOGLE SHEETS (mantenido como opción secundaria) ──────────────────────
    google_sheets_row = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Fila de Google Sheets',
        db_index=True
    )
    sincronizado_sheets = models.BooleanField(
        default=False,
        verbose_name='Sincronizado desde Sheets',
        db_index=True
    )
    precio_real = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio original en Sheets'
    )

    # ── ORIGEN ────────────────────────────────────────────────────────────────
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        default='manual',
        verbose_name='Origen del producto',
        db_index=True
    )
    fecha_importacion = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Fecha de importación'
    )

    # ── AUDITORÍA ─────────────────────────────────────────────────────────────
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['-creado_en']

    def __str__(self):
        partes = []
        if self.nombre:
            partes.append(self.nombre)
        if self.tipo_producto:
            partes.append(str(self.tipo_producto))
        if self.variante:
            partes.append(self.variante)
        base = " - ".join(partes) if partes else "Producto sin nombre"
        return f"{base} ({self.get_estado_display()})"

    # ── MÉTODOS DE UTILIDAD ───────────────────────────────────────────────────

    def tiene_imagen(self):
        """Verifica si el producto tiene imagen"""
        return bool(self.imagen)

    def esta_disponible(self):
        """Verifica si el producto está disponible"""
        return self.estado == 'disponible'

    def margen(self):
        """Calcula el margen de ganancia si hay precio de costo"""
        if self.precio and self.precio_costo and self.precio_costo > 0:
            return self.precio - self.precio_costo
        return None

    def porcentaje_margen(self):
        """Calcula el porcentaje de margen"""
        margen = self.margen()
        if margen is not None and self.precio_costo > 0:
            return round((margen / self.precio_costo) * 100, 1)
        return None

    def get_atributo(self, clave, default=''):
        """Obtiene un atributo dinámico de forma segura"""
        return self.atributos.get(clave, default)

    def set_atributo(self, clave, valor):
        """Guarda un atributo dinámico y persiste"""
        self.atributos[clave] = valor
        self.save(update_fields=['atributos', 'actualizado_en'])

    def generar_descripcion_auto(self):
        """Genera descripción automática desde los campos disponibles"""
        partes = []
        if self.marca:
            partes.append(f"Marca: {self.marca}")
        if self.color:
            partes.append(f"Color: {self.color}")
        if self.variante:
            partes.append(f"Variante: {self.variante}")
        # También incluir atributos dinámicos
        for clave, valor in self.atributos.items():
            partes.append(f"{clave.title()}: {valor}")
        return " | ".join(partes) if partes else self.descripcion