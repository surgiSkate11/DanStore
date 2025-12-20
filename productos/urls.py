from django.urls import path
from . import views
from .sheets_sync import sincronizar_sheets

urlpatterns = [
    path('', views.home, name='home'),
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/<int:pk>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:pk>/eliminar/', views.eliminar_producto, name='eliminar_producto'),
    path('productos/<int:pk>/cambiar-estado/', views.cambiar_estado_producto, name='cambiar_estado_producto'),
    path('productos/<int:pk>/cambiar-categoria/', views.cambiar_categoria_producto, name='cambiar_categoria_producto'),
    path('productos/<int:pk>/cambiar-talla/', views.cambiar_talla_producto, name='cambiar_talla_producto'),
    path('productos/<int:pk>/subir-foto/', views.subir_foto_producto, name='subir_foto_producto'),
    path('api/rangos-edad/', views.get_rangos_edad, name='get_rangos_edad'),
    
    # Google Sheets
    path('sheets/sincronizar/', sincronizar_sheets, name='sincronizar_sheets'),
]
