from django.urls import path
from . import views

urlpatterns = [
    # Gestión
    path('roles/', views.lista_roles, name='lista_roles'),
    path('empleados/', views.lista_empleados, name='lista_empleados'),
    path('suspendida/', views.cuenta_suspendida, name='cuenta_suspendida'),
    path('configuracion/', views.configuracion_empresa, name='configuracion_empresa'),
    path('soporte/crear/', views.crear_ticket, name='crear_ticket'),
    path('pagar/<str:metodo>/<int:plan_id>/<str:tipo_plan>/', views.procesar_pago_saas, name='procesar_pago_saas'),
    path('pago-exitoso/<int:plan_id>/<str:tipo_plan>/', views.pago_exitoso, name='pago_exitoso'),
]