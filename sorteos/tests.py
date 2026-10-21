import json
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from empresas.testing import crear_empresa_con_dueno
from sorteos.models import Premio, Sorteo, SorteoPremio
from ventas.models import Venta


class AislamientoSorteosTests(TestCase):
    """El ranking de un sorteo solo cuenta compras hechas en la propia empresa."""

    def setUp(self):
        self.empresa_a, self.dueno_a = crear_empresa_con_dueno('panaderia')
        self.empresa_b, _ = crear_empresa_con_dueno('cafeteria')

        # Cliente compartido: compró $10 en A y $100 en B.
        self.cliente = Cliente.objects.create(nombre='Cliente Compartido', ruc_cedula='3333333333')
        self.cliente.empresas.add(self.empresa_a, self.empresa_b)
        venta_a = Venta.objects.create(empresa=self.empresa_a, cliente=self.cliente)
        venta_b = Venta.objects.create(empresa=self.empresa_b, cliente=self.cliente)
        Venta.objects.filter(pk=venta_a.pk).update(total=Decimal('10.00'))
        Venta.objects.filter(pk=venta_b.pk).update(total=Decimal('100.00'))

        # Consumidor final: una sola fila compartida por todas las empresas.
        self.consumidor_final = Cliente.objects.create(
            nombre='Consumidor Final Cafeteria Beto', ruc_cedula='9999999999',
        )
        self.consumidor_final.empresas.add(self.empresa_a, self.empresa_b)

        self.sorteo = Sorteo.objects.create(
            empresa=self.empresa_a, nombre='Ranking del viernes', tipo='ranking', criterio='todos',
        )
        premio = Premio.objects.create(empresa=self.empresa_a, nombre='Pan gratis', tipo='producto_gratis')
        SorteoPremio.objects.create(sorteo=self.sorteo, premio=premio)
        self.client.force_login(self.dueno_a)

    def participantes_del_ranking(self):
        respuesta = self.client.get(reverse('ejecutar_sorteo', args=[self.sorteo.pk]))
        self.assertEqual(respuesta.status_code, 200)
        return json.loads(respuesta.context['participantes_json'])

    def test_ranking_no_suma_compras_de_otra_empresa(self):
        participantes = {p['id']: p for p in self.participantes_del_ranking()}
        # $10 en A = 6 puntos (cada $5 = 3 puntos). Con las compras de B serían 66.
        self.assertEqual(participantes[self.cliente.pk]['puntos'], 6)

    def test_consumidor_final_compartido_no_participa(self):
        ids = {p['id'] for p in self.participantes_del_ranking()}
        self.assertNotIn(self.consumidor_final.pk, ids)
        self.assertNotIn(self.consumidor_final.pk, self.sorteo.obtener_participantes().values_list('pk', flat=True))

    def test_sorteo_de_otra_empresa_da_404(self):
        sorteo_b = Sorteo.objects.create(
            empresa=self.empresa_b, nombre='Sorteo de B', tipo='ruleta', criterio='todos',
        )
        for nombre_url in ['detalle_sorteo', 'ejecutar_sorteo', 'gestionar_participantes', 'gestionar_premios']:
            with self.subTest(nombre_url):
                respuesta = self.client.get(reverse(nombre_url, args=[sorteo_b.pk]))
                self.assertEqual(respuesta.status_code, 404)

    def test_lista_no_muestra_sorteos_de_otra_empresa(self):
        Sorteo.objects.create(empresa=self.empresa_b, nombre='Sorteo secreto de B', tipo='ruleta', criterio='todos')
        respuesta = self.client.get(reverse('lista_sorteos'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'Sorteo secreto de B')
