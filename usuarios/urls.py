from django.urls import path
from . import views

urlpatterns = [
    path('perfil/', views.perfil, name='perfil'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('limpiar-demo/', views.limpiar_demo, name='limpiar_demo'),
    path('cargar-demo/', views.cargar_demo, name='cargar_demo'),
    
    # Flujo de Recuperación de Usuario
    path('recuperar-usuario/', views.username_reset_request_view, name='username_reset'),
    path('recuperar-usuario/confirmar/', views.username_reset_masked_view, name='username_reset_masked'),
    path('recuperar-usuario/enviado/', views.recuperar_usuario_done, name='username_reset_done'),
]