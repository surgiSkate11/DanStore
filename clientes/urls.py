from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_clientes, name='lista_clientes'),
    path('crear/', views.crear_cliente, name='crear_cliente'),
    path('exportar/csv/', views.exportar_clientes_csv, name='exportar_clientes_csv'),
    path('<int:cliente_id>/', views.detalle_cliente, name='detalle_cliente'),
    path('<int:cliente_id>/editar/', views.editar_cliente, name='editar_cliente'),
]
