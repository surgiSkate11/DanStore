from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

from .fields import EncryptedTextField


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

    # Límite de empleados que una empresa puede crear bajo este plan.
    # Deja en null/blank para no aplicar límite (empleados ilimitados).
    limite_empleados = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Límite de empleados",
        help_text="Deja vacío para permitir empleados ilimitados en este plan."
    )

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
    sitio_web = models.URLField(blank=True, verbose_name="Sitio Web")
    tiktok_url = models.URLField(blank=True, verbose_name="URL de TikTok")
    x_url = models.URLField(blank=True, verbose_name="URL de X (Twitter)")

    # Landing Page del Cliente Final (Catálogo)
    landing_titulo = models.CharField(max_length=200, blank=True, default="Bienvenido a nuestra tienda")
    landing_descripcion = models.TextField(blank=True, default="Descubre nuestros mejores productos al mejor precio.")
    mensaje_promocional = models.CharField(max_length=150, blank=True, help_text="Banner superior. Ej: ¡Envío gratis en compras mayores a $50!")
    color_primario = models.CharField(max_length=7, default="#0d6efd", help_text="Color Hexadecimal (Ej: #0d6efd)")
    color_fondo = models.CharField(max_length=7, default="#faf9f7", help_text="Color de fondo de la tienda")
    color_cabecera = models.CharField(max_length=7, default="#faf9f7", help_text="Color de la barra de navegación")
    color_texto = models.CharField(max_length=7, default="#1a1611", help_text="Color principal de los textos")

    logo = models.ImageField(upload_to='empresas/logos/', null=True, blank=True, verbose_name="Logotipo de la Tienda")
    hero_image = models.ImageField(upload_to='empresas/hero/', null=True, blank=True, verbose_name="Imagen de Portada (Hero)")

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
    stripe_secret_key = EncryptedTextField(blank=True, verbose_name="Stripe Secret Key")
    paypal_client_id = models.CharField(max_length=255, blank=True, verbose_name="PayPal Client ID")
    paypal_secret_key = EncryptedTextField(blank=True, verbose_name="PayPal Secret Key")
    payphone_token = EncryptedTextField(blank=True, verbose_name="PayPhone Bearer Token")
    support_email = models.EmailField(blank=True, null=True, verbose_name="Email de Soporte", help_text="Correo para recibir y enviar notificaciones de tickets")
    nombre_plataforma = models.CharField(max_length=100, default="Tiendita SaaS", verbose_name="Nombre de la Plataforma")

    SMTP_ENCRYPTION_CHOICES = [
        ('none', 'Sin cifrado'),
        ('starttls', 'STARTTLS'),
        ('ssl', 'SSL implícito'),
    ]

    smtp_host = models.CharField(max_length=255, blank=True, verbose_name="Servidor SMTP")
    smtp_port = models.PositiveIntegerField(default=587, verbose_name="Puerto SMTP")
    smtp_user = models.CharField(max_length=255, blank=True, verbose_name="Usuario SMTP")
    smtp_password = EncryptedTextField(blank=True, verbose_name="Contraseña SMTP")
    smtp_encryption = models.CharField(max_length=20, choices=SMTP_ENCRYPTION_CHOICES, default='starttls', verbose_name="Cifrado SMTP")
    smtp_from_name = models.CharField(max_length=120, blank=True, default='Tiendita SaaS', verbose_name="Nombre del remitente")
    smtp_from_email = models.EmailField(blank=True, default='', verbose_name="Correo remitente")
    smtp_test_mode = models.BooleanField(default=False, verbose_name="Modo prueba", help_text="Redirige los correos a una sola casilla mientras pruebas la integración")
    smtp_test_recipient = models.EmailField(blank=True, default='', verbose_name="Correo de prueba")
    smtp_last_test_status = models.CharField(max_length=20, blank=True, default='', verbose_name="Estado último test")
    smtp_last_test_message = models.TextField(blank=True, default='', verbose_name="Detalle último test")
    smtp_last_test_at = models.DateTimeField(null=True, blank=True, verbose_name="Último test SMTP")
    smtp_max_attachment_mb = models.PositiveIntegerField(default=25, verbose_name="Límite adjunto (MB)")
    smtp_daily_limit = models.PositiveIntegerField(default=500, verbose_name="Límite diario de correos")
    smtp_retry_attempts = models.PositiveIntegerField(default=3, verbose_name="Reintentos SMTP")
    smtp_retry_delay_seconds = models.PositiveIntegerField(default=2, verbose_name="Espera entre reintentos (s)")

    # --- REDES Y CONTACTO DEL SAAS ---
    telefono_whatsapp = models.CharField(max_length=20, blank=True, verbose_name="WhatsApp de Soporte", help_text="Incluir código de país, ej: 593991234567")
    instagram_url = models.URLField(blank=True, verbose_name="Instagram del SaaS")
    facebook_url = models.URLField(blank=True, verbose_name="Facebook del SaaS")
    sitio_web = models.URLField(blank=True, verbose_name="Sitio Web del SaaS")
    tiktok_url = models.URLField(blank=True, verbose_name="TikTok del SaaS")
    x_url = models.URLField(blank=True, verbose_name="X (Twitter) del SaaS")

    # --- TRANSFERENCIAS BANCARIAS LOCALES ---
    transferencia_active = models.BooleanField(default=False, verbose_name="Activar Pago por Transferencia")
    banco_pichincha = models.TextField(blank=True, help_text="Ej: Cta. Ahorros #123456789 - Juan Pérez - CI: 0999999999")
    banco_pichincha_2 = models.TextField(blank=True, verbose_name="Banco Pichincha (Cuenta 2)", help_text="Ej: Cta. Corriente #987654321 - Mi Empresa S.A.")
    banco_guayaquil = models.TextField(blank=True, help_text="Ej: Cta. Corriente #987654321 - Juan Pérez")
    banco_jep = models.TextField(blank=True, help_text="Ej: Cta. Ahorros #456123 - Juan Pérez")
    # -----------------------------------------

    # --- PASARELAS DE PAGO ADICIONALES ---
    mercadopago_active = models.BooleanField(default=False, verbose_name="Activar MercadoPago")
    mercadopago_token = EncryptedTextField(blank=True, verbose_name="MercadoPago Access Token")

    coinbase_active = models.BooleanField(default=False, verbose_name="Activar Coinbase Commerce")
    coinbase_api_key = EncryptedTextField(blank=True, verbose_name="Coinbase API Key")

    razorpay_active = models.BooleanField(default=False, verbose_name="Activar Razorpay")
    razorpay_key_id = models.CharField(max_length=255, blank=True, verbose_name="Razorpay Key ID")
    razorpay_key_secret = EncryptedTextField(blank=True, verbose_name="Razorpay Key Secret")
    # -----------------------------------------

    class Meta:
        verbose_name = "Configuración SaaS"
        verbose_name_plural = "Configuración SaaS"

    def __str__(self):
        return "Credenciales de Pago Globales"


class StorefrontConfig(models.Model):
    """
    Configuración individual y desacoplada de la tienda pública.
    Reemplaza los campos que antes ensuciaban el modelo Empresa.
    """
    empresa = models.OneToOneField('empresas.Empresa', on_delete=models.CASCADE, related_name='storefront_config')

    # Textos
    landing_titulo = models.CharField(max_length=150, blank=True)
    landing_descripcion = models.TextField(blank=True)
    mensaje_promocional = models.CharField(max_length=200, blank=True)

    # Recursos visuales
    logo = models.ImageField(upload_to='tienda/logos/', null=True, blank=True)
    hero_image = models.ImageField(upload_to='tienda/banners/', null=True, blank=True)
    color_primario = models.CharField(max_length=20, default='#0d6efd')

    # Layout Builder (Para guardar el orden arrastrable en formato JSON)
    layout_blocks = models.JSONField(default=list, blank=True, help_text="Configuración dinámica de bloques visuales")

    # Redes Sociales (Desacopladas)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Storefront de {self.empresa.nombre}"