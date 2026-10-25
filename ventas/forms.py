import re
from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError

from .models import MONTO_MAXIMO, ConfiguracionFactura

_FORMATO_MONTO = re.compile(r'\d+(\.\d*)?|\.\d+', re.ASCII)
ETIQUETAS_GASTOS = {'descuento': 'descuento', 'envio': 'envío', 'otros_gastos': 'otros gastos'}

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


def leer_monto(valor, etiqueta):
    """Convierte un monto del formulario a Decimal; vacío cuenta como 0.

    Rechaza texto, NaN/Infinity, notación científica, negativos, más de 2 decimales
    y montos que no caben en el campo del modelo.
    """
    texto = (valor or '').strip()
    if not texto:
        return Decimal('0')
    mensaje_texto = f'Ingresa un valor numérico válido para {etiqueta}.'
    try:
        monto = Decimal(texto)
    except InvalidOperation:
        raise ValidationError(mensaje_texto)
    if not monto.is_finite():
        raise ValidationError(mensaje_texto)
    if monto < 0:
        raise ValidationError(f'El valor de {etiqueta} no puede ser negativo.')
    if not _FORMATO_MONTO.fullmatch(texto):
        raise ValidationError(mensaje_texto)
    if monto.as_tuple().exponent < -2:
        raise ValidationError(f'El valor de {etiqueta} admite como máximo 2 decimales.')
    if monto > MONTO_MAXIMO:
        raise ValidationError(f'El valor de {etiqueta} no puede superar {MONTO_MAXIMO}.')
    return monto


def leer_gastos(datos, subtotal):
    """Valida descuento, envío y otros gastos de una venta.

    `subtotal` es la suma de precios de los productos, sin IVA. Lanza ValidationError
    con un mensaje en español para el usuario; si todo es válido devuelve los tres montos.
    """
    gastos = {campo: leer_monto(datos.get(campo), etiqueta) for campo, etiqueta in ETIQUETAS_GASTOS.items()}
    subtotal = Decimal(subtotal or 0)
    if gastos['descuento'] > subtotal:
        raise ValidationError(f'El descuento no puede ser mayor al subtotal (${subtotal:.2f}).')
    return gastos
