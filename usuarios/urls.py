from django.urls import path
from . import views

urlpatterns = [
    path('onboarding/', views.onboarding, name='onboarding'),
    path('cambiar-negocio/', views.cambiar_tipo_negocio, name='cambiar_negocio'),
    path('cargar-demo/', views.cargar_demo_data, name='cargar_demo'),
    path('limpiar-demo/', views.limpiar_demo_data, name='limpiar_demo'),
]
