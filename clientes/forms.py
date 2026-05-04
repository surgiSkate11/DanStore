import re

from django import forms
from .models import Cliente

class ClienteForm(forms.ModelForm):
    tipo_identificacion = forms.ChoiceField(
        choices=[('cedula', 'Cédula'), ('ruc', 'RUC')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'onchange': 'actualizarValidacionDocumento()'}),
        initial='cedula',
        required=False
    )

    class Meta:
        model = Cliente
        fields = ['nombre', 'tipo_identificacion', 'ruc_cedula', 'email', 'telefono', 'direccion', 'notas']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Juan Pérez',
                # Previene que se escriban números y la mayoría de símbolos
                'oninput': "this.value = this.value.replace(/[^a-zA-ZáéíóúÁÉÍÓÚñÑ .]/g, '')",
                'title': "Solo se permiten letras y espacios."
            }),
            'ruc_cedula': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: 0999999999',
                'type': 'tel', # Muestra teclado numérico en móviles
                'inputmode': 'numeric',
                'pattern': '[0-9]*', # Patrón para validación de navegador
                # Previene que se escriban caracteres no numéricos
                'oninput': "this.value = this.value.replace(/[^0-9]/g, '')",
                'maxlength': '13',
                'title': "Solo se permiten números. 10 para cédula, 13 para RUC."
            }),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Ej: juan@correo.com'}),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: 0991234567',
                'type': 'tel',
                'inputmode': 'numeric',
                'pattern': '[0-9+ ]*',
                # Previene que se escriban letras o símbolos no permitidos
                'oninput': "this.value = this.value.replace(/[^0-9+ ]/g, '')",
                'maxlength': '15',
                'title': "Solo se permiten números, espacios y el signo '+'."
            }),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Ej: Av. Principal 123...'}),
            'notas': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Información adicional sobre el cliente...'}),
        }
        labels = {
            'nombre': 'Nombres Completos',
            'ruc_cedula': 'Cédula / RUC',
            'email': 'Correo Electrónico',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.ruc_cedula:
            doc = re.sub(r'[\s-]', '', self.instance.ruc_cedula)
            if len(doc) == 13:
                self.fields['tipo_identificacion'].initial = 'ruc'
            else:
                self.fields['tipo_identificacion'].initial = 'cedula'

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre', '').strip()
        if not nombre:
            raise forms.ValidationError("Este campo es obligatorio.")
        
        # Validar que no contenga números ni símbolos especiales raros.
        # Permite letras (incluyendo acentos y eñes), espacios y puntos (ej: "Sr. Juan")
        if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s\.]+$', nombre):
            raise forms.ValidationError("El nombre solo debe contener letras y espacios.")
        
        return nombre

    def clean_ruc_cedula(self):
        ruc_cedula = self.cleaned_data.get('ruc_cedula', '').strip()
        if not ruc_cedula:
            raise forms.ValidationError("Este campo es obligatorio.")
            
        # Permitir Cédulas Temporales generadas por el sistema (desde Google Sheets)
        if ruc_cedula.startswith('SYS-'):
            return ruc_cedula

        # Eliminar espacios y guiones para la validación estricta
        ruc_limpio = re.sub(r'[\s-]', '', ruc_cedula)
        
        # Validar que solo contenga números
        if not ruc_limpio.isdigit():
            raise forms.ValidationError("El documento debe contener únicamente números.")
        
        tipo_id = self.cleaned_data.get('tipo_identificacion') or self.data.get('tipo_identificacion')
        
        if tipo_id == 'cedula' and len(ruc_limpio) != 10:
            raise forms.ValidationError("La Cédula debe tener exactamente 10 dígitos.")
        elif tipo_id == 'ruc' and len(ruc_limpio) != 13:
            raise forms.ValidationError("El RUC debe tener exactamente 13 dígitos.")
        elif not tipo_id and len(ruc_limpio) not in [10, 13]:
            raise forms.ValidationError("El documento debe tener 10 o 13 dígitos.")
        
        # --- VALIDACIÓN DE UNICIDAD ---
        # Comprueba si ya existe otro cliente con esta Cédula/RUC.
        query = Cliente.objects.filter(ruc_cedula=ruc_limpio)
        
        # Si estamos editando (self.instance.pk existe), excluimos el propio cliente de la búsqueda.
        if self.instance and self.instance.pk:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise forms.ValidationError("Ya existe otro cliente registrado con esta Cédula/RUC.")
            
        return ruc_limpio

    def clean_telefono(self):
        # Usar 'or' para asegurar que si el valor es None, se convierta a un string vacío antes de usar .strip()
        telefono = (self.cleaned_data.get('telefono') or '').strip()
        if not telefono:
            return '' # Devolver siempre un string vacío para campos opcionales
            
        # Validar que opcionalmente inicie con un '+' seguido de solo números y espacios
        if not re.match(r'^\+?[0-9\s]+$', telefono):
            raise forms.ValidationError("El teléfono solo debe contener números.")
            
        # Limpiar espacios para el guardado en base de datos
        telefono_limpio = telefono.replace(' ', '')
        
        if len(telefono_limpio) < 7 or len(telefono_limpio) > 15:
            raise forms.ValidationError("El teléfono debe tener entre 7 y 15 dígitos.")
            
        return telefono_limpio