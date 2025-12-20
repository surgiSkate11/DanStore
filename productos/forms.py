from django import forms
from .models import Producto, TipoPrenda

class ProductoForm(forms.ModelForm):
    """Formulario para crear y editar productos"""
    
    class Meta:
        model = Producto
        fields = ['imagen', 'descripcion', 'categoria_grupo', 'rango_edad', 
                  'tipo_prenda', 'estado', 'precio']
        widgets = {
            'imagen': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción del producto'
            }),
            'categoria_grupo': forms.Select(attrs={
                'class': 'form-control',
                'id': 'id_categoria_grupo'
            }),
            'rango_edad': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'id_rango_edad',
                'placeholder': 'Ej: M, 5, 0-3, etc.'
            }),
            'tipo_prenda': forms.Select(attrs={
                'class': 'form-control'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-control'
            }),
            'precio': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'placeholder': '0.00'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # tipo_prenda es requerido - solo se usan los tipos del Sheets
        self.fields['tipo_prenda'].required = True
        
        # Los campos categoria_grupo y rango_edad siempre son editables
        # La categoría usa las opciones del modelo (que vienen de Sheets)
        # El rango_edad es texto libre para flexibilidad
    
    def get_rango_edad_choices(self, categoria):
        """Retorna las opciones de rango de edad según la categoría"""
        choices = [('', '-- Seleccionar --')]
        if categoria == 'bebe':
            choices.extend(Producto.EDAD_BEBE)
        elif categoria in ['nino', 'nina']:
            choices.extend(Producto.EDAD_NINO)
        elif categoria == 'joven':
            choices.extend(Producto.EDAD_JOVEN)
        elif categoria in ['adulto_hombre', 'adulto_mujer']:
            choices.extend(Producto.TALLA_ADULTO)
        return choices
    
    def clean(self):
        cleaned_data = super().clean()
        tipo_prenda = cleaned_data.get('tipo_prenda')
        
        # tipo_prenda es requerido - debe estar en las opciones del Sheets
        if not tipo_prenda:
            raise forms.ValidationError('Debe seleccionar un tipo de prenda')
        
        return cleaned_data


class ProductoFiltroForm(forms.Form):
    """Formulario para filtrar productos"""
    
    categoria_grupo = forms.ChoiceField(
        choices=[('', 'Todas las categorías')] + Producto.CATEGORIA_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    tipo_prenda = forms.ModelChoiceField(
        queryset=TipoPrenda.objects.all(),
        required=False,
        empty_label='Todos los tipos',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    estado = forms.ChoiceField(
        choices=[('', 'Todos los estados')] + Producto.ESTADO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    busqueda = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar en descripción...'
        })
    )
