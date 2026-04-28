from django.db import models
from django.utils import timezone
from ventas.models import Cliente, Venta
from decimal import Decimal
from empresas.models import Empresa


class Sorteo(models.Model):
    """Modelo principal de sorteos para en vivos"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='sorteos')
    
    TIPO_SORTEO = [
        ('ruleta', '🎡 Ruleta de Ganadores'),
        ('cofre', '🎁 Cofre Sorpresa'),
        ('caja', '😱 Caja Misteriosa'),
        ('semaforo', '🚦 Semáforo de Premios'),
        ('ranking', '🏆 Ranking del Día'),
    ]
    
    CRITERIO_PARTICIPACION = [
        ('todos', 'Todos los clientes'),
        ('compras_hoy', 'Compraron hoy'),
        ('monto_minimo', 'Monto mínimo de compra'),
        ('cantidad_productos', 'Cantidad mínima de productos'),
        ('top_compradores', 'Top compradores'),
        ('manual', 'Selección manual'),
    ]
    
    nombre = models.CharField(max_length=200, verbose_name="Nombre del sorteo")
    tipo = models.CharField(max_length=20, choices=TIPO_SORTEO, verbose_name="Tipo de sorteo")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    
    # Criterios de participación
    criterio = models.CharField(
        max_length=30, 
        choices=CRITERIO_PARTICIPACION, 
        default='compras_hoy',
        verbose_name="Criterio de participación"
    )
    monto_minimo = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        verbose_name="Monto mínimo ($)"
    )
    cantidad_minima = models.IntegerField(
        null=True, 
        blank=True,
        verbose_name="Cantidad mínima de productos"
    )
    top_cantidad = models.IntegerField(
        default=10,
        verbose_name="Cantidad de top compradores"
    )
    
    # Configuración específica por tipo
    cantidad_cofres = models.IntegerField(
        default=3,
        verbose_name="Cantidad de Cajas/Cofres",
        help_text="Para 'Cofre Sorpresa' y 'Caja Misteriosa'"
    )
    
    # Estado y fechas
    activo = models.BooleanField(default=True, verbose_name="Activo")
    fecha_creacion = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    fecha_sorteo = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de realización")
    completado = models.BooleanField(default=False, verbose_name="Completado")
    
    class Meta:
        verbose_name = "Sorteo"
        verbose_name_plural = "Sorteos"
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"{self.get_tipo_display()} - {self.nombre}"
    
    def obtener_participantes(self):
        """Obtiene la lista de clientes que cumplen el criterio"""
        from django.db.models import Sum, Count
        from datetime import date
        
        if self.criterio == 'todos':
            return Cliente.objects.filter(empresas=self.empresa)
        
        elif self.criterio == 'compras_hoy':
            return Cliente.objects.filter(
                empresas=self.empresa,
                ventas__empresa=self.empresa,
                ventas__fecha__date=date.today()
            ).distinct()
        
        elif self.criterio == 'monto_minimo' and self.monto_minimo:
            clientes_ids = Venta.objects.filter(empresa=self.empresa).values('cliente').annotate(
                total_comprado=Sum('total')
            ).filter(
                total_comprado__gte=self.monto_minimo
            ).values_list('cliente', flat=True)
            return Cliente.objects.filter(id__in=clientes_ids, empresas=self.empresa)
        
        elif self.criterio == 'cantidad_productos' and self.cantidad_minima:
            clientes_ids = Venta.objects.filter(empresa=self.empresa).values('cliente').annotate(
                total_productos=Count('detalles')
            ).filter(
                total_productos__gte=self.cantidad_minima
            ).values_list('cliente', flat=True)
            return Cliente.objects.filter(id__in=clientes_ids, empresas=self.empresa)
        
        elif self.criterio == 'top_compradores':
            clientes_ids = Venta.objects.filter(empresa=self.empresa).values('cliente').annotate(
                total_comprado=Sum('total')
            ).order_by('-total_comprado')[:self.top_cantidad].values_list('cliente', flat=True)
            return Cliente.objects.filter(id__in=clientes_ids, empresas=self.empresa)
        
        else:
            # Participantes agregados manualmente
            return Cliente.objects.filter(
                empresas=self.empresa,
                id__in=self.participantes.values_list('cliente_id', flat=True)
            )
    
    def cantidad_participantes(self):
        """Retorna la cantidad de participantes elegibles"""
        return self.obtener_participantes().count()
    
    @property
    def premios(self):
        """Retorna los premios asociados a este sorteo a través de SorteoPremio"""
        return self.sorteo_premios.select_related('premio').all()


class Participante(models.Model):
    """Participantes en un sorteo"""
    sorteo = models.ForeignKey(
        Sorteo, 
        on_delete=models.CASCADE, 
        related_name='participantes',
        verbose_name="Sorteo"
    )
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.CASCADE,
        verbose_name="Cliente"
    )
    agregado_en = models.DateTimeField(auto_now_add=True, verbose_name="Agregado en")
    
    class Meta:
        verbose_name = "Participante"
        verbose_name_plural = "Participantes"
        unique_together = ['sorteo', 'cliente']
        ordering = ['agregado_en']
    
    def __str__(self):
        return f"{self.cliente.nombre} - {self.sorteo.nombre}"


class Premio(models.Model):
    """Premios reutilizables para sorteos"""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='premios')
    
    TIPO_PREMIO = [
        ('descuento_porcentaje', '% Descuento'),
        ('descuento_fijo', '$ Descuento Fijo'),
        ('producto_gratis', 'Producto Gratis'),
        ('envio_gratis', 'Envío Gratis'),
        ('cupon', 'Cupón'),
        ('combo', 'Combo/Pack'),
        ('gracias', 'Gracias por Participar'),
    ]
    
    nombre = models.CharField(max_length=200, verbose_name="Nombre del premio")
    tipo = models.CharField(max_length=30, choices=TIPO_PREMIO, verbose_name="Tipo de premio")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")
    
    # Valores del premio
    valor_descuento = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        help_text="Porcentaje o monto fijo según el tipo"
    )
    minimo_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Mínimo de compra ($)",
        help_text="Monto mínimo requerido para usar el premio"
    )
    dias_validez = models.IntegerField(
        default=2,
        verbose_name="Días de validez",
        help_text="Cuántos días es válido el premio"
    )
    
    creado_en = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Premio"
        verbose_name_plural = "Premios"
        ordering = ['nombre']
    
    def __str__(self):
        return f"{self.nombre} - {self.get_tipo_display()}"


class SorteoPremio(models.Model):
    """Relación entre sorteos y premios con configuración específica"""
    sorteo = models.ForeignKey(
        Sorteo,
        on_delete=models.CASCADE,
        related_name='sorteo_premios',
        verbose_name="Sorteo"
    )
    premio = models.ForeignKey(
        Premio,
        on_delete=models.CASCADE,
        related_name='sorteos_asociados',
        verbose_name="Premio"
    )
    
    # Configuración específica del premio en este sorteo
    color = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Para semáforo: rojo, amarillo, verde"
    )
    numero_cofre = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Para cofre: número del 1 al 8"
    )
    cantidad_disponible = models.IntegerField(
        default=1,
        verbose_name="Cantidad disponible"
    )
    asignado = models.BooleanField(default=False, verbose_name="Ya asignado")
    orden = models.IntegerField(default=0, verbose_name="Orden de entrega")
    agregado_en = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Premio de Sorteo"
        verbose_name_plural = "Premios de Sorteos"
        ordering = ['sorteo', 'orden', 'agregado_en']
    
    def __str__(self):
        return f"{self.premio.nombre} en {self.sorteo.nombre}"


class ResultadoSorteo(models.Model):
    """Resultados de los sorteos realizados"""
    sorteo = models.ForeignKey(
        Sorteo, 
        on_delete=models.CASCADE, 
        related_name='resultados',
        verbose_name="Sorteo"
    )
    cliente = models.ForeignKey(
        Cliente, 
        on_delete=models.CASCADE,
        verbose_name="Ganador"
    )
    premio = models.ForeignKey(
        Premio, 
        on_delete=models.SET_NULL, 
        null=True,
        verbose_name="Premio ganado"
    )
    posicion = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Para ranking: 1ro, 2do, 3ro"
    )
    
    fecha_resultado = models.DateTimeField(default=timezone.now, verbose_name="Fecha del resultado")
    premio_canjeado = models.BooleanField(default=False, verbose_name="Premio canjeado")
    fecha_canje = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de canje")
    notas = models.TextField(blank=True, verbose_name="Notas")
    
    class Meta:
        verbose_name = "Resultado de Sorteo"
        verbose_name_plural = "Resultados de Sorteos"
        ordering = ['-fecha_resultado', 'posicion']
    
    def __str__(self):
        return f"{self.cliente.nombre} ganó en {self.sorteo.nombre}"


class Cupon(models.Model):
    """Cupones generados por sorteos"""
    codigo = models.CharField(max_length=20, unique=True, verbose_name="Código del cupón")
    resultado = models.OneToOneField(
        ResultadoSorteo, 
        on_delete=models.CASCADE,
        related_name='cupon',
        verbose_name="Resultado asociado"
    )
    tipo_descuento = models.CharField(
        max_length=20,
        choices=[('porcentaje', 'Porcentaje'), ('fijo', 'Monto Fijo')],
        default='porcentaje'
    )
    valor = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Valor")
    
    usado = models.BooleanField(default=False, verbose_name="Usado")
    fecha_uso = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de uso")
    venta_asociada = models.ForeignKey(
        Venta, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Venta donde se usó"
    )
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField(null=True, blank=True, verbose_name="Fecha de expiración")
    
    class Meta:
        verbose_name = "Cupón"
        verbose_name_plural = "Cupones"
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"{self.codigo} - {self.resultado.cliente.nombre}"
    
    def esta_vigente(self):
        """Verifica si el cupón está vigente"""
        if self.usado:
            return False
        if self.fecha_expiracion and timezone.now() > self.fecha_expiracion:
            return False
        return True
