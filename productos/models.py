from django.db import models
from django.utils import timezone

class TipoPrenda(models.Model):
    """Catálogo de tipos de prendas"""
    nombre = models.CharField(max_length=100, unique=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Tipo de Prenda"
        verbose_name_plural = "Tipos de Prendas"
        ordering = ['nombre']
    
    def __str__(self):
        return self.nombre


class Producto(models.Model):
    """Modelo principal de productos"""
    
    # Categorías de grupo
    CATEGORIA_CHOICES = [
        ('bebe', 'Bebé'),
        ('nina', 'Niña'),
        ('nino', 'Niño'),
        ('joven', 'Joven/Adolescente'),
        ('adulto_hombre', 'Adulto Hombre'),
        ('adulto_mujer', 'Adulto Mujer'),
    ]
    
    # Rangos de edad para bebés
    EDAD_BEBE = [
        ('0-3', '0-3 meses'),
        ('3-6', '3-6 meses'),
        ('6-9', '6-9 meses'),
        ('9-12', '9-12 meses'),
    ]
    
    # Rangos de edad para niños (1-11 años)
    EDAD_NINO = [(str(i), f'{i} año{"s" if i > 1 else ""}') for i in range(1, 12)]
    
    # Rangos de edad para jóvenes (12-17 años)
    EDAD_JOVEN = [(str(i), f'{i} años') for i in range(12, 18)]
    
    # Tallas para adultos
    TALLA_ADULTO = [
        ('XS', 'Extra Small'),
        ('S', 'Small'),
        ('M', 'Medium'),
        ('L', 'Large'),
        ('XL', 'Extra Large'),
        ('XXL', 'XXL'),
        ('XXXL', 'XXXL'),
    ]
    
    # Estados del producto
    ESTADO_CHOICES = [
        ('disponible', 'Disponible'),
        ('separado', 'Separado'),
        ('vendido', 'Vendido'),
    ]
    
    # Campos del producto
    imagen = models.ImageField(
        upload_to='productos/%Y/%m/',
        verbose_name='Imagen',
        null=True,
        blank=True,
        help_text='Sube la foto del producto (opcional si viene de Google Sheets)'
    )
    descripcion = models.TextField(verbose_name='Descripción', blank=True)
    categoria_grupo = models.CharField(
        max_length=20,
        choices=CATEGORIA_CHOICES,
        verbose_name='Categoría de Grupo',
        db_index=True  # Índice para filtrado rápido por categoría
    )
    
    # Campos de Google Sheets
    marca = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Marca'
    )
    color = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Color'
    )
    vendido_a = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Vendido a',
        db_index=True  # Índice para búsqueda rápida de productos por cliente
    )
    precio_real = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio Real'
    )
    google_sheets_row = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Fila de Google Sheets',
        help_text='Número de fila en Google Sheets',
        db_index=True  # Índice para sincronización rápida
    )
    sincronizado_sheets = models.BooleanField(
        default=False,
        verbose_name='Sincronizado desde Sheets',
        db_index=True  # Índice para filtrado de productos sincronizados
    )
    rango_edad = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Rango de Edad/Talla'
    )
    tipo_prenda = models.ForeignKey(
        TipoPrenda,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name='Tipo de Prenda'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='disponible',
        verbose_name='Estado',
        db_index=True  # Índice para filtrado rápido por estado
    )
    precio = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Precio',
        db_index=True  # Índice para ordenamiento y filtrado por precio
    )
    
    # Campos de auditoría
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ['-creado_en']
    
    def __str__(self):
        marca_str = f"{self.marca} - " if self.marca else ""
        return f"{marca_str}{self.get_categoria_grupo_display()} - {self.tipo_prenda} ({self.get_estado_display()})"
    
    def tiene_imagen(self):
        """Verifica si el producto tiene imagen"""
        return bool(self.imagen)
    
    def generar_descripcion_auto(self):
        """Genera descripción automática desde campos de Google Sheets"""
        partes = []
        if self.marca:
            partes.append(f"Marca: {self.marca}")
        if self.color:
            partes.append(f"Color: {self.color}")
        if self.rango_edad:
            partes.append(f"Talla/Edad: {self.get_rango_edad_display_custom()}")
        return " | ".join(partes) if partes else self.descripcion
    
    def esta_disponible(self):
        """Verifica si el producto está disponible para mostrar en catálogo"""
        return self.estado != 'vendido'
    
    def get_rango_edad_display_custom(self):
        """Obtiene la representación del rango de edad tal cual viene de Google Sheets"""
        # Simplemente retorna el valor tal cual está (puede ser 3-4M, 5, XL, etc.)
        return self.rango_edad if self.rango_edad else ''
