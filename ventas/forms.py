from django import forms

from .models import ConfiguracionFactura

MENSAJE_IVA_MAXIMO = 'El porcentaje de IVA no puede ser mayor a 30.'


class PorcentajeIvaForm(forms.ModelForm):
    """Valida el % de IVA de la configuración de facturas: 0–30 con hasta 2 decimales."""

    porcentaje_iva = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0,
        max_value=30,
        error_messages={
            'required': 'El porcentaje de IVA es obligatorio.',
            'invalid': 'El porcentaje de IVA debe ser un número válido.',
            'min_value': 'El porcentaje de IVA no puede ser negativo.',
            'max_value': MENSAJE_IVA_MAXIMO,
            'max_digits': MENSAJE_IVA_MAXIMO,
            'max_whole_digits': MENSAJE_IVA_MAXIMO,
            'max_decimal_places': 'El porcentaje de IVA admite como máximo 2 decimales.',
        },
    )

    class Meta:
        model = ConfiguracionFactura
        fields = ['porcentaje_iva']
