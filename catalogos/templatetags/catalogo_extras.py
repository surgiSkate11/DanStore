from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """
    Permite hacer {{ mi_dict|get_item:variable_clave }} en el template.
    Django's dict access ({{ mi_dict.clave }}) solo funciona con claves
    literales, no con variables — por eso se necesita este filtro para
    recorrer listas de (campo, etiqueta) y leer config[campo] dinámicamente.
    """
    if dictionary is None:
        return ''
    try:
        return dictionary.get(key, '')
    except AttributeError:
        return ''