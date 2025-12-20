from django.urls import path
from . import views

urlpatterns = [
    # Lista de sorteos
    path('', views.lista_sorteos, name='lista_sorteos'),
    
    # Crear sorteo
    path('crear/', views.crear_sorteo, name='crear_sorteo'),
    
    # Detalle de sorteo
    path('<int:sorteo_id>/', views.detalle_sorteo, name='detalle_sorteo'),
    
    # Ejecutar sorteo
    path('<int:sorteo_id>/ejecutar/', views.ejecutar_sorteo, name='ejecutar_sorteo'),
    
    # API endpoints
    path('<int:sorteo_id>/sortear/', views.sortear_ganador, name='sortear_ganador'),
    path('<int:sorteo_id>/registrar/', views.registrar_resultado, name='registrar_resultado'),
    path('<int:sorteo_id>/finalizar/', views.finalizar_sorteo, name='finalizar_sorteo'),
    
    # Gestión de participantes manuales
    path('<int:sorteo_id>/participantes/', views.gestionar_participantes, name='gestionar_participantes'),
    path('<int:sorteo_id>/participantes/agregar/', views.agregar_participante, name='agregar_participante'),
    path('<int:sorteo_id>/participantes/<int:participante_id>/eliminar/', views.eliminar_participante, name='eliminar_participante'),
    
    # Gestión de premios
    path('<int:sorteo_id>/premios/', views.gestionar_premios, name='gestionar_premios'),
    path('<int:sorteo_id>/premios/agregar/', views.agregar_premio, name='agregar_premio'),
    path('premios/<int:premio_id>/eliminar/', views.eliminar_premio, name='eliminar_premio'),
]
