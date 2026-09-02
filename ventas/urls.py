from django.urls import path
from . import views

urlpatterns = [
    # Lista de ventas
    path('', views.lista_ventas, name='lista_ventas'),
    
    # Lista de deudas
    path('deudas/', views.lista_deudas, name='lista_deudas'),
    
    # Crear venta
    path('crear/', views.crear_venta, name='crear_venta'),
    
    # Editar venta
    path('<int:venta_id>/editar/', views.editar_venta, name='editar_venta'),
    
    # Detalle de venta
    path('<int:venta_id>/', views.detalle_venta, name='detalle_venta'),
    
    # Generar PDF
    path('<int:venta_id>/factura/', views.factura_pdf, name='factura_pdf'),
    path('<int:venta_id>/factura/', views.factura_pdf, name='generar_factura_pdf'),
    
    # Generar PDF de deuda por cliente
    path('deudas/<str:cliente_nombre>/comprobante/', views.generar_comprobante_deuda_pdf, name='generar_comprobante_deuda_pdf'),
    
    # Configuración
    path('configuracion/', views.configuracion_facturas, name='configuracion_facturas'),
]
