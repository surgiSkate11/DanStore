from django.urls import path
from . import views

urlpatterns = [
    # Lista de sorteos
    path('', views.lista_sorteos, name='lista_sorteos'),
    
    # Crear sorteo
    path('crear-sorteo/', views.crear_sorteo, name='crear_sorteo'),
    
    # Detalle de sorteo
    path('detalle-sorteo/<int:sorteo_id>/', views.detalle_sorteo, name='detalle_sorteo'),
    
    # Ejecutar sorteo
    path('ejecutar-sorteo/<int:sorteo_id>/', views.ejecutar_sorteo, name='ejecutar_sorteo'),
    
    # API endpoints
    path('sortear/<int:sorteo_id>/', views.sortear_ganador, name='sortear_ganador'),
    path('registrar-resultados/<int:sorteo_id>/', views.registrar_resultado, name='registrar_resultado'),
    path('finalizar-sorteo/<int:sorteo_id>/', views.finalizar_sorteo, name='finalizar_sorteo'),
    
    # Gestión de participantes manuales
    path('gestionar-participantes/<int:sorteo_id>/', views.gestionar_participantes, name='gestionar_participantes'),
    path('agregar-participantes/<int:sorteo_id>/', views.agregar_participante, name='agregar_participante'),
    path('eliminar-participantes/<int:sorteo_id>/', views.eliminar_participante, name='eliminar_participante'),
    
    # Gestión de premios
    path('premios/<int:sorteo_id>/', views.gestionar_premios, name='gestionar_premios'),
    path('agregar-premios/<int:sorteo_id>/', views.agregar_premio, name='agregar_premio'),
    path('eliminar-premios/<int:sorteo_id>/', views.eliminar_premio, name='eliminar_premio'),
]
