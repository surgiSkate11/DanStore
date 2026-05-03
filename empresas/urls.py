from django.urls import path
from . import views

urlpatterns = [
    # Gestión
    path('roles/', views.lista_roles, name='lista_roles'),
    path('empleados/', views.lista_empleados, name='lista_empleados'),
    path('suspendida/', views.cuenta_suspendida, name='cuenta_suspendida'),
    path('configuracion-tienda/', views.configuracion_tienda, name='configuracion_tienda'),
    path('soporte/crear/', views.crear_ticket, name='crear_ticket'),
    path('pagar/<str:metodo>/<int:plan_id>/<str:tipo_plan>/', views.procesar_pago_saas, name='procesar_pago_saas'),
    path('pago-exitoso/<int:plan_id>/<str:tipo_plan>/', views.pago_exitoso, name='pago_exitoso'),
    path('reportar-transferencia/', views.reportar_pago_transferencia, name='reportar_transferencia'),
]