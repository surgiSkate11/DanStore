from django.contrib import messages
from django.utils.html import strip_tags

def form_errors_to_messages(request, form):
    """
    Itera sobre los errores de un formulario (field y non_field) 
    y los agrega al sistema de mensajes de Django (toasts).
    """
    # Errores generales (Rojos)
    for error in form.non_field_errors():
        messages.error(request, strip_tags(error))
        
    # Errores específicos de un input (Amarillos - Advertencias)
    for field in form:
        for error in field.errors:
            messages.warning(request, f"{field.label}: {strip_tags(error)}")
