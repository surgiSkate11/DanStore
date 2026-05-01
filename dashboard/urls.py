
# Dashboard Principal (HOME)

from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('router/', views.dashboard_router, name='dashboard_router'),
    path('saas/dashboard/', views.dashboard_saas, name='dashboard_saas'),
    path('saas/empresas/', views.saas_empresas, name='saas_empresas'),
    path('saas/empresas/exportar/', views.exportar_empresas_csv, name='exportar_empresas_csv'),
    path('saas/empresas/<int:empresa_id>/toggle/', views.toggle_estado_empresa, name='toggle_estado_empresa'),
    path('saas/tickets/', views.saas_tickets, name='saas_tickets'),
    path('saas/configuracion/', views.saas_configuracion, name='saas_configuracion'),
    path('saas/control-panel/', views.saas_control_panel, name='saas_control_panel'),
    path('saas/control-panel/crear/<str:app_label>/<str:model_name>/', views.saas_crear_registro, name='saas_crear_registro'),
    path('app/dashboard/', views.dashboard_tenant, name='dashboard_tenant'),
    path('tienda/<slug:slug>/', views.tienda_publica, name='tienda_publica'),
]