from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User


class Plan(models.Model):
    """
    Planes de suscripción SaaS y los módulos que incluyen.
    """
    nombre = models.CharField(max_length=50, verbose_name="Nombre del Plan")
    descripcion = models.TextField(blank=True)
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    precio_anual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # Usamos string 'usuarios.ModuloSaaS' para evitar importación circular
    modulos = models.ManyToManyField('usuarios.ModuloSaaS', blank=True, related_name="planes")

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def __str__(self):
        return self.nombre


class Empresa(models.Model):
    nombre = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, help_text="URL amigable para la empresa (ej: mi-tienda)")
    activa = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    # --- PERSONALIZACIÓN DE LA EMPRESA ---
    # Contacto y Redes
    telefono_whatsapp = models.CharField(max_length=20, blank=True, help_text="Incluir código de país, ej: 593991234567")
    instagram_url = models.URLField(blank=True, verbose_name="URL de Instagram")
    facebook_url = models.URLField(blank=True, verbose_name="URL de Facebook")
    youtube_url = models.URLField(blank=True, verbose_name="URL de YouTube")
    
    # Landing Page del Cliente Final (Catálogo)
    landing_titulo = models.CharField(max_length=200, blank=True, default="Bienvenido a nuestra tienda")
    landing_descripcion = models.TextField(blank=True, default="Descubre nuestros mejores productos al mejor precio.")
    mensaje_promocional = models.CharField(max_length=150, blank=True, help_text="Banner superior. Ej: ¡Envío gratis en compras mayores a $50!")
    color_primario = models.CharField(max_length=7, default="#0d6efd", help_text="Color Hexadecimal (Ej: #0d6efd)")
    
    # Plantillas de Mensajes del Sistema
    mensaje_planes = models.TextField(blank=True, default="Hola, soy de la empresa {empresa}. Me interesa renovar/adquirir el plan {plan}.")
    # -------------------------------------
    
    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

    def __str__(self):
        return self.nombre


class SuscripcionEmpresa(models.Model):
    """Gestión de la suscripción SaaS activa para la empresa"""
    TIPO_PLAN_CHOICES = [
        ('mensual', 'Mensual'),
        ('anual', 'Anual'),
    ]
    
    empresa = models.OneToOneField(Empresa, on_delete=models.CASCADE, related_name='suscripcion')
    plan = models.ForeignKey(Plan, on_delete=models.RESTRICT, related_name='suscripciones', null=True, blank=True)
    tipo_plan = models.CharField(max_length=20, choices=TIPO_PLAN_CHOICES, default='mensual')
    fecha_inicio = models.DateTimeField(default=timezone.now)
    fecha_vencimiento = models.DateTimeField()
    
    def dias_restantes(self):
        delta = self.fecha_vencimiento - timezone.now()
        return max(0, delta.days)
        
    def porcentaje_consumido(self):
        total_dias = (self.fecha_vencimiento - self.fecha_inicio).days
        if total_dias <= 0: return 100
        
        dias_consumidos = (timezone.now() - self.fecha_inicio).days
        porcentaje = (dias_consumidos / total_dias) * 100
        return min(100, max(0, int(porcentaje)))

    def estado_color(self):
        pct = self.porcentaje_consumido()
        if pct < 75: 
            return 'success'  # Verde
        elif pct < 90: 
            return 'warning'  # Naranja
        return 'danger'       # Rojo
        
    def __str__(self):
        nombre_plan = self.plan.nombre if self.plan else "Sin Plan"
        return f"Suscripción {nombre_plan} ({self.get_tipo_plan_display()}) - {self.empresa.nombre}"


class Ticket(models.Model):
    """Modelo para gestionar los tickets de soporte técnico del SaaS"""
    ESTADOS = [
        ('abierto', 'Abierto'),
        ('en_progreso', 'En Progreso'),
        ('resuelto', 'Resuelto'),
        ('cerrado', 'Cerrado'),
    ]
    
    CATEGORIAS = [
        ('suspension', 'Suspensión de Cuenta'),
        ('facturacion', 'Problema de Facturación'),
        ('tecnico', 'Problema Técnico'),
        ('otro', 'Otro'),
    ]
    
    PRIORIDADES = [
        ('baja', 'Baja'),
        ('media', 'Media'),
        ('alta', 'Alta'),
        ('critica', 'Crítica'),
    ]

    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name='tickets')
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='tickets_creados')
    asunto = models.CharField(max_length=200)
    categoria = models.CharField(max_length=20, choices=CATEGORIAS, default='otro')
    prioridad = models.CharField(max_length=15, choices=PRIORIDADES, default='media')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='abierto')
    
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ticket de Soporte"
        verbose_name_plural = "Tickets de Soporte"
        ordering = ['-actualizado_en']

    def __str__(self):
        return f"Ticket #{self.id} - {self.asunto} ({self.empresa.nombre})"


class MensajeTicket(models.Model):
    """Historial de mensajes o chat dentro de un ticket de soporte"""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='mensajes')
    remitente = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    mensaje = models.TextField()
    adjunto = models.FileField(upload_to='tickets/adjuntos/', null=True, blank=True)
    es_staff = models.BooleanField(default=False, help_text="Indica si el mensaje fue enviado por el equipo de soporte (SaaS)")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['creado_en']

    def __str__(self):
        return f"Mensaje en Ticket #{self.ticket.id} por {self.remitente.username if self.remitente else 'Desconocido'}"

class ConfiguracionSaaS(models.Model):
    """Configuración global del sistema SaaS (Pasarelas de pago, APIs)"""
    stripe_secret_key = models.CharField(max_length=255, blank=True, verbose_name="Stripe Secret Key")
    paypal_client_id = models.CharField(max_length=255, blank=True, verbose_name="PayPal Client ID")
    paypal_secret_key = models.CharField(max_length=255, blank=True, verbose_name="PayPal Secret Key")
    payphone_token = models.CharField(max_length=255, blank=True, verbose_name="PayPhone Bearer Token")
    support_email = models.EmailField(blank=True, null=True, verbose_name="Email de Soporte", help_text="Correo para recibir y enviar notificaciones de tickets")
    nombre_plataforma = models.CharField(max_length=100, default="Tiendita SaaS", verbose_name="Nombre de la Plataforma")
    
    class Meta:
        verbose_name = "Configuración SaaS"
        verbose_name_plural = "Configuración SaaS"
        
    def __str__(self):
        return "Credenciales de Pago Globales"
