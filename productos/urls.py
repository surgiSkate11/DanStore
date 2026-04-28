from django.urls import path
from . import views
from .sheets_sync import sincronizar_sheets

urlpatterns = [
    path('', views.lista_productos, name='lista_productos'),
    path('crear_productos/', views.crear_producto, name='crear_producto'),
    path('editar_productos/<int:pk>/editar/', views.editar_producto, name='editar_producto'),
    path('eliminar_productos/<int:pk>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    path('cambiar-estado/<int:pk>/cambiar-estado/', views.cambiar_estado_producto, name='cambiar_estado_producto'),
    path('cambiar-categoria/<int:pk>/cambiar-categoria/', views.cambiar_categoria_producto, name='cambiar_categoria_producto'),
    path('cambiar-variante/<int:pk>/cambiar-variante/', views.cambiar_variante_producto, name='cambiar_variante_producto'),
    path('subir-foto/<int:pk>/subir-foto/', views.subir_foto_producto, name='subir_foto_producto'),
    
    # AJAX para TipoProducto
    path('api/crear-tipo-producto/', views.api_crear_tipo_producto, name='api_crear_tipo_producto'),
    
    # CAMBIO 2: Importación Excel/CSV
    path('importar/', views.importar_excel, name='importar_excel'),
    path('plantilla/', views.descargar_plantilla, name='descargar_plantilla'),
    
    # Google Sheets
    path('sheets/sincronizar/', sincronizar_sheets, name='sincronizar_sheets'),
]
