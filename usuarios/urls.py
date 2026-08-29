from django.urls import path
from . import views

urlpatterns = [
    path('perfil/', views.perfil, name='perfil'),
    path('forzar-cambio-password/', views.forzar_cambio_password, name='forzar_cambio_password'),
    path('onboarding/', views.onboarding, name='onboarding'),
    path('verificar-email/<str:token>/', views.verificar_cambio_email, name='verificar_cambio_email'),
]