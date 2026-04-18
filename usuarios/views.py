from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.management import call_command
from django.db import connection
from .models import UserProfile
from productos.models import Producto
from ventas.models import Cliente


@login_required
def onboarding(request):
    """Vista de onboarding para seleccionar tipo de negocio"""
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    
    if request.method == 'POST':
        negocio_tipo = request.POST.get('negocio_tipo')
        nombre_negocio = request.POST.get('nombre_negocio', '')
        
        if negocio_tipo in dict(UserProfile.TIPO_NEGOCIO_CHOICES):
            profile.negocio_tipo = negocio_tipo
            profile.nombre_negocio = nombre_negocio
            profile.onboarding_completado = True
            profile.save()
            messages.success(request, f"¡Bienvenido! Tu negocio '{nombre_negocio}' ha sido creado.")
            return redirect('home')
    
    context = {
        'profile': profile,
        'tipos_negocio': UserProfile.TIPO_NEGOCIO_CHOICES
    }
    return render(request, 'usuarios/onboarding.html', context)


@login_required
@require_http_methods(['POST'])
def cambiar_tipo_negocio(request):
    """Permite cambiar el tipo de negocio después del onboarding"""
    profile = request.user.profile
    negocio_tipo = request.POST.get('negocio_tipo')
    
    if negocio_tipo in dict(UserProfile.TIPO_NEGOCIO_CHOICES):
        profile.negocio_tipo = negocio_tipo
        profile.save()
        messages.success(request, f"Tipo de negocio actualizado a {negocio_tipo}")
    
    return redirect(request.POST.get('next', 'home'))


@login_required
@require_http_methods(['POST'])
def cargar_demo_data(request):
    """Carga datos de demostración"""
    try:
        call_command('cargar_demo_data', request.user.id)
        messages.success(
            request, 
            "✨ Datos de demostración cargados. Ahora puedes ver cómo funciona la app."
        )
    except Exception as e:
        messages.error(request, f"Error al cargar demo data: {str(e)}")
    
    return redirect('home')


@login_required
@require_http_methods(['POST'])
def limpiar_demo_data(request):
    """Elimina los datos de demostración"""
    try:
        # Eliminar productos ficticios
        Producto.objects.filter(sincronizado_sheets=False).delete()
        # Eliminar clientes
        Cliente.objects.all().delete()
        
        # Actualizar perfil
        profile = request.user.profile
        profile.usa_demo_data = False
        profile.save()
        
        messages.success(request, "Datos de demostración eliminados.")
    except Exception as e:
        messages.error(request, f"Error al limpiar demo data: {str(e)}")
    
    return redirect('home')

