
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
    path('saas/equipo/', views.saas_equipo, name='saas_equipo'),
    path('saas/configuracion/', views.saas_configuracion, name='saas_configuracion'),
    path('saas/configuracion/probar-smtp/', views.saas_configuracion_test_smtp, name='saas_configuracion_test_smtp'),
    path('saas/control-panel/', views.saas_control_panel, name='saas_control_panel'),
    path('saas/control-panel/crear/<str:app_label>/<str:model_name>/', views.saas_crear_registro, name='saas_crear_registro'),
    path('saas/control-panel/ver/<str:app_label>/<str:model_name>/', views.saas_listar_registros, name='saas_listar_registros'),
    path('saas/control-panel/editar/<str:app_label>/<str:model_name>/<int:object_id>/', views.saas_editar_registro, name='saas_editar_registro'),
    path('saas/control-panel/renovar-suscripcion/<int:subscription_id>/', views.saas_renovar_suscripcion, name='saas_renovar_suscripcion'),
    path('saas/control-panel/eliminar/<str:app_label>/<str:model_name>/<int:object_id>/', views.saas_eliminar_registro, name='saas_eliminar_registro'),
    path('app/dashboard/', views.dashboard_tenant, name='dashboard_tenant'),
    path('app/reportes/', views.tenant_reportes, name='tenant_reportes'),
    path('tienda/<slug:slug>/', views.tienda_publica, name='tienda_publica'),
]