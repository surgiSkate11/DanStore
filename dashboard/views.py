from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from productos.models import Producto
# Create your views here.

@login_required
def home(request):
    """Vista principal - Dashboard"""
    # OPTIMIZACIÓN: Usar count() directo es rápido con índices
    
    # Verificamos si es superusuario sin empresa asignada para evitar errores
    empresa_actual = getattr(request, 'empresa', None)
    
    context = {
        'total_productos': Producto.objects.filter(empresa=empresa_actual).count() if empresa_actual else Producto.objects.all().count(),
        'disponibles': Producto.objects.filter(empresa=empresa_actual, estado='disponible').count() if empresa_actual else Producto.objects.filter(estado='disponible').count(),
        'separados': Producto.objects.filter(empresa=empresa_actual, estado='separado').count() if empresa_actual else Producto.objects.filter(estado='separado').count(),
        'vendidos': Producto.objects.filter(empresa=empresa_actual, estado='vendido').count() if empresa_actual else Producto.objects.filter(estado='vendido').count(),
    }
    return render(request, 'dashboard/home.html', context)
