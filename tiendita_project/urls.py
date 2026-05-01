"""
URL configuration for tiendita_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from usuarios import views as usuarios_views

urlpatterns = [
    path('', include('dashboard.urls')),  # Ruta para el dashboard
    path('admin/', admin.site.urls),
    path('login/', usuarios_views.CustomLoginView.as_view(template_name='security/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Flujo Profesional de Recuperación de Contraseña SaaS
    path('recuperar-password/', usuarios_views.password_reset_request_view, name='password_reset'),
    path('recuperar-password/confirmar/', usuarios_views.password_reset_masked_view, name='password_reset_masked'),
    path('recuperar-password/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='security/password_reset_done.html'), name='password_reset_done'),
    path('recuperar-password/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='security/password_reset_confirm.html'), name='password_reset_confirm'),
    path('recuperar-password/completado/', auth_views.PasswordResetCompleteView.as_view(template_name='security/password_reset_complete.html'), name='password_reset_complete'),
    
    # Flujo de Recuperación de Usuario
    path('recuperar-usuario/', usuarios_views.username_reset_request_view, name='username_reset'),
    path('recuperar-usuario/confirmar/', usuarios_views.username_reset_masked_view, name='username_reset_masked'),
    path('recuperar-usuario/enviado/', usuarios_views.recuperar_usuario_done, name='username_reset_done'),
    
    path('usuarios/', include('usuarios.urls')),
    path('productos/', include('productos.urls')),
    path('catalogos/', include('catalogos.urls')),
    path('clientes/', include('clientes.urls')),
    path('ventas/', include('ventas.urls')),
    path('sorteos/', include('sorteos.urls')),
    path('empresa/', include('empresas.urls')),
]

# Servir archivos media en desarrollo
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
