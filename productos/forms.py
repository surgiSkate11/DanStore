from django import forms
from .models import Producto, TipoProducto


class ProductoForm(forms.ModelForm):
    """Formulario para crear y editar productos"""
    
    class Meta:
        model = Producto
        fields = ['nombre', 'descripcion', 'imagen', 'categoria', 'tipo_producto', 
                  'variante', 'precio', 'precio_costo', 'precio_oferta', 'stock', 'marca', 'color', 'estado']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre del producto'
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Descripción del producto'
            }),
            'imagen': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            }),
            'categoria': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: General, Mujer, Electrónica, Postres, Servicios'
            }),
            'tipo_producto': forms.Select(attrs={
                'class': 'form-control'
            }),
            'variante': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Talla, modelo, sabor, versión, etc.'
            }),
            'precio': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.01',
                'placeholder': '0.00'
            }),
            'precio_costo': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00',
                'placeholder': '0.00 (opcional)'
            }),
            'precio_oferta': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00',
                'placeholder': '0.00 (opcional)'
            }),
            'marca': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Marca o proveedor (opcional)'
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Color (opcional)'
            }),
            'stock': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        # Extraemos la empresa si se pasa en kwargs
        self.empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        
        # Configurar opciones de Categoría dinámicamente
        queryset_productos = Producto.objects.filter(empresa=self.empresa) if self.empresa else Producto.objects.all()
        categorias = list(queryset_productos.exclude(categoria='').values_list('categoria', flat=True).distinct().order_by('categoria'))
        
        if self.instance and self.instance.pk and self.instance.categoria and self.instance.categoria not in categorias:
            categorias.append(self.instance.categoria)
            
        choices = [('', '--------')] + [(c, c) for c in categorias]
        
        self.fields['categoria'].widget = forms.Select(attrs={'class': 'form-control'})
        self.fields['categoria'].widget.choices = choices
        
        # ── HACER CAMPOS IMPORTANTES OBLIGATORIOS ──
        self.fields['nombre'].required = True
        self.fields['nombre'].error_messages = {'required': 'El nombre del producto es obligatorio.'}
        self.fields['precio'].required = True
        self.fields['precio'].error_messages = {'required': 'El precio de venta es obligatorio.'}
        self.fields['stock'].required = True
        self.fields['stock'].error_messages = {'required': 'Debes indicar el stock.'}

    def clean(self):
        cleaned_data = super().clean()
        precio = cleaned_data.get('precio')
        precio_oferta = cleaned_data.get('precio_oferta')

        if precio_oferta is not None and precio is not None and precio_oferta >= precio:
            self.add_error(
                'precio_oferta',
                'El precio de oferta debe ser menor al precio normal, o el catálogo no lo mostrará como oferta.'
            )
        return cleaned_data



class ProductoFiltroForm(forms.Form):
    """Formulario para filtrar productos"""
    def __init__(self, *args, **kwargs):
        empresa = kwargs.pop('empresa', None)
        super().__init__(*args, **kwargs)
        if empresa:
            self.fields['tipo_producto'].queryset = TipoProducto.objects.filter(empresa=empresa)
    
    categoria = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: General, Mujer, Electrónica, Postres...'
        }),
        help_text='Valores válidos: general (recomendado), bebe, nina, nino, joven, adulto_hombre, adulto_mujer, o cualquier categoría personalizada'
    )
    
    tipo_producto = forms.ModelChoiceField(
        queryset=TipoProducto.objects.none(), # Se llena en el __init__
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
            'placeholder': 'Buscar en nombre o descripción...'
        })
    )