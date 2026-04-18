from django import forms
from .models import Producto, TipoPrenda

class ProductoForm(forms.ModelForm):
    """Formulario dinámico para crear y editar productos según tipo de negocio"""
    
    # Campos dinámicos para atributos (se generan según negocio_tipo)
    atributos_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput()
    )
    
    class Meta:
        model = Producto
        fields = ['imagen', 'descripcion', 'categoria_grupo', 'rango_edad', 
                  'tipo_prenda', 'estado', 'precio', 'atributos']
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
            'atributos': forms.HiddenInput(),
        }
    
    def __init__(self, *args, negocio_tipo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.negocio_tipo = negocio_tipo or 'ropa'
        
        # tipo_prenda es requerido
        self.fields['tipo_prenda'].required = True
        
        # Campos dinámicos según negocio_tipo
        self._agregar_campos_dinamicos()
    
    def _agregar_campos_dinamicos(self):
        """Agrega campos dinámicos según el tipo de negocio"""
        
        # Definir atributos esperados por negocio_tipo
        atributos_por_tipo = {
            'ropa': {
                'talla': forms.CharField(
                    max_length=50, required=False, 
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: M, L, XL'})
                ),
                'color': forms.CharField(
                    max_length=50, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Negro, Azul'})
                ),
            },
            'tecnologia': {
                'marca': forms.CharField(
                    max_length=100, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Marca'})
                ),
                'modelo': forms.CharField(
                    max_length=100, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Modelo'})
                ),
                'especificaciones': forms.CharField(
                    required=False,
                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Especificaciones'})
                ),
            },
            'alimentos': {
                'vencimiento': forms.DateField(
                    required=False,
                    widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
                ),
                'peso': forms.CharField(
                    max_length=100, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 500g, 1kg'})
                ),
                'lote': forms.CharField(
                    max_length=100, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de lote'})
                ),
            },
            'servicios': {
                'fecha_servicio': forms.DateField(
                    required=False,
                    widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
                ),
                'ubicacion': forms.CharField(
                    max_length=200, required=False,
                    widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ubicación'})
                ),
            },
        }
        
        # Agregar campos dinámicos al formulario
        campos_dinamicos = atributos_por_tipo.get(self.negocio_tipo, {})
        for nombre, campo in campos_dinamicos.items():
            self.fields[f'atributo_{nombre}'] = campo
    
    def clean(self):
        cleaned_data = super().clean()
        tipo_prenda = cleaned_data.get('tipo_prenda')
        
        if not tipo_prenda:
            raise forms.ValidationError('Debe seleccionar un tipo de prenda')
        
        return cleaned_data
    
    def save(self, commit=True):
        """Guarda el producto y compila los atributos dinámicos"""
        instance = super().save(commit=False)
        
        # Compilar atributos dinámicos en el JSONField
        atributos = {}
        for campo, valor in self.cleaned_data.items():
            if campo.startswith('atributo_'):
                nombre_atributo = campo.replace('atributo_', '')
                if valor:  # Solo guardar si tiene valor
                    atributos[nombre_atributo] = str(valor)
        
        instance.atributos = atributos
        
        if commit:
            instance.save()
        
        return instance



class ProductoFiltroForm(forms.Form):
    """Formulario para filtrar productos"""
    
    categoria_grupo = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Categorías estándar (siempre presentes y en orden)
        categorias_estandar = [
            ('Bebé', 'Bebé'),
            ('Niño', 'Niño'),
            ('Niña', 'Niña'),
            ('Joven/Adolescente', 'Joven/Adolescente'),
            ('Adulto Hombre', 'Adulto Hombre'),
            ('Adulto Mujer', 'Adulto Mujer'),
        ]
        # Obtener categorías adicionales de la base de datos (no estándar)
        from .models import Producto
        categorias_db = set(Producto.objects.values_list('categoria_grupo', flat=True).distinct())
        categorias_db = {c for c in categorias_db if c and c not in dict(categorias_estandar)}
        # Unir todas, primero las estándar, luego las adicionales ordenadas alfabéticamente
        choices = [('', 'Todas las categorías')] + categorias_estandar + sorted((c, c) for c in categorias_db)
        self.fields['categoria_grupo'].choices = choices
    
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
