from django.db import models


class Modulo(models.Model):
    """
    Define las partes del sistema. Ej: Sorteos, Catálogo, Importación.
    """
    nombre = models.CharField(max_length=50, verbose_name="Nombre del Módulo")
    icono = models.CharField(max_length=50, help_text="Ej: bi-trophy, bi-box")
    url_name = models.CharField(max_length=100, help_text="Nombre de la URL en Django. Ej: lista_sorteos")
    activo = models.BooleanField(default=True)
    orden = models.IntegerField(default=0, help_text="Para ordenar el menú")

    class Meta:
        verbose_name = "Módulo"
        verbose_name_plural = "Módulos"
        ordering = ['orden']

    def __str__(self):
        return self.nombre


class Plan(models.Model):
    """
    Define los planes de suscripción (Ej: Básico, Premium) y a qué módulos tienen acceso.
    """
    nombre = models.CharField(max_length=50, verbose_name="Nombre del Plan")
    modulos = models.ManyToManyField(Modulo, blank=True, related_name="planes")
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

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
    plan = models.ForeignKey(Plan, on_delete=models.SET_NULL, null=True, blank=True, related_name='empresas')
    
    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'

    def __str__(self):
        return self.nombre
