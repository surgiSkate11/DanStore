from django.urls import path
from . import views

urlpatterns = [
    # Clientes (from Google Sheets vendido_a dropdown)
    path('', views.top_clientes, name='top_clientes'),
    path('<str:cliente_nombre>/', views.detalle_cliente, name='detalle_cliente'),
    path('<str:cliente_nombre>/editar/', views.editar_info_cliente, name='editar_info_cliente'),
]
