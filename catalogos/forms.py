from django import forms
from productos.models import Producto, TipoProducto


class CatalogoFilterForm(forms.Form):
    """
    Formulario de filtros/organización para el generador de catálogos.

    IMPORTANTE: todos los campos están mapeados 1:1 contra los campos reales
    de productos.models.Producto. No se asume ningún campo que no exista
    (ej. no existe 'proveedor' separado de 'marca', no existe 'sku' ni
    'codigo' como campos del modelo — esos, si se usan, vienen del JSONField
    'atributos' y se documentan como tal).
    """

    # ── Organización (agrupar) ──────────────────────────────────────────
    group_by = forms.ChoiceField(
        choices=[
            ('', 'No agrupar'),
            ('categoria', 'Agrupar por Categoría'),
            ('marca', 'Agrupar por Marca / Proveedor'),
            ('tipo_producto', 'Agrupar por Tipo de producto'),
            ('subcategoria', 'Agrupar por Variante / Subcategoría'),
        ],
        required=False,
        label="Agrupar productos por",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    # ── Filtros: precio ──────────────────────────────────────────────────
    precio_min = forms.DecimalField(
        required=False,
        label="Precio mínimo",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'})
    )
    precio_max = forms.DecimalField(
        required=False,
        label="Precio máximo",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '9999.99'})
    )

    # ── Filtros: categoría / marca-proveedor / tipo ────────────────────
    categorias = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Categorías",
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'})
    )

    marcas = forms.MultipleChoiceField(
        choices=[],
        required=False,
        label="Marcas / Proveedores",
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'})
    )

    tipos_producto = forms.ModelMultipleChoiceField(
        queryset=TipoProducto.objects.none(),
        required=False,
        label="Tipo de producto",
        widget=forms.SelectMultiple(attrs={'class': 'form-control', 'size': '5'})
    )

    # ── Filtros: estado / disponibilidad ────────────────────────────────
    activos = forms.BooleanField(
        required=False,
        label="Solo productos activos (disponibles)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        initial=True
    )

    con_stock = forms.BooleanField(
        required=False,
        label="Solo productos con stock",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    sin_stock = forms.BooleanField(
        required=False,
        label="Solo productos sin stock",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    destacados = forms.BooleanField(
        required=False,
        label="Solo productos destacados",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    nuevos = forms.BooleanField(
        required=False,
        label="Solo productos nuevos (últimos 30 días)",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    en_oferta = forms.BooleanField(
        required=False,
        label="Solo productos en oferta",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    mas_vendidos = forms.BooleanField(
        required=False,
        label="Solo productos más vendidos",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    mayor_rentabilidad = forms.BooleanField(
        required=False,
        label="Solo productos con mayor rentabilidad",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # ── Ordenamiento ─────────────────────────────────────────────────────
    sort_by = forms.ChoiceField(
        choices=[
            ('categoria', 'Categoría'),
            ('nombre', 'Nombre (A-Z)'),
            ('-nombre', 'Nombre (Z-A)'),
            ('precio', 'Precio (menor a mayor)'),
            ('-precio', 'Precio (mayor a menor)'),
            ('marca', 'Marca / Proveedor'),
            ('-creado_en', 'Fecha (más recientes)'),
            ('creado_en', 'Fecha (más antiguos)'),
            ('mas_vendidos', 'Más vendidos primero'),
            ('rentabilidad', 'Mayor rentabilidad primero'),
        ],
        required=False,
        initial='categoria',
        label="Ordenar por",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    # ── Búsqueda general (antes "Búsqueda en Descripción") ──────────────
    # Renombrada: el nombre anterior era confuso porque en realidad busca en
    # nombre, descripción, marca, categoría y variante — no solo en la
    # descripción. Ver informe para el detalle de esta decisión.
    busqueda = forms.CharField(
        max_length=200,
        required=False,
        label="Búsqueda general",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por nombre, descripción, marca, categoría o variante...'
        })
    )

    # ── Selección manual ─────────────────────────────────────────────────
    seleccion = forms.CharField(
        required=False,
        label="IDs seleccionados manualmente",
        help_text="Lista de IDs separados por coma. Se usa cuando el usuario elige productos a mano en la interfaz.",
        widget=forms.HiddenInput()
    )

    excluir = forms.CharField(
        required=False,
        label="IDs a excluir",
        help_text="Lista de IDs separados por coma a excluir del catálogo, aunque cumplan los demás filtros.",
        widget=forms.HiddenInput()
    )

    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        if empresa:
            productos = Producto.objects.filter(empresa=empresa)

            categorias_qs = (
                productos.exclude(categoria__exact='')
                .values_list('categoria', 'categoria')
                .distinct()
                .order_by('categoria')
            )
            self.fields['categorias'].choices = list(categorias_qs)

            marcas_qs = (
                productos.exclude(marca__exact='')
                .values_list('marca', 'marca')
                .distinct()
                .order_by('marca')
            )
            self.fields['marcas'].choices = list(marcas_qs)

            self.fields['tipos_producto'].queryset = TipoProducto.objects.filter(
                empresa=empresa
            ).order_by('nombre')