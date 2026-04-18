from django.urls import path
from . import views

urlpatterns = [
    path('generar/', views.generar_catalogo, name='generar_catalogo'),
    path('preview/', views.preview_catalogo, name='preview_catalogo'),
    path('descargar/', views.descargar_catalogo, name='descargar_catalogo'),
    path('personalizar/', views.personalizar_catalogo, name='personalizar_catalogo'),
]
