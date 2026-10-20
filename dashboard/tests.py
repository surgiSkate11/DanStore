from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from empresas.models import Empresa


class XFrameOptionsTests(TestCase):
    def test_paginas_del_sitio_no_se_pueden_embeber(self):
        respuesta = self.client.get(reverse('login'))
        self.assertEqual(respuesta['X-Frame-Options'], 'DENY')

    def test_tienda_publica_se_puede_embeber_en_la_vista_previa_propia(self):
        empresa = Empresa.objects.create(nombre='Panaderia', slug='panaderia')
        respuesta = self.client.get(reverse('tienda_publica', args=[empresa.slug]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta['X-Frame-Options'], 'SAMEORIGIN')


@override_settings(
    SECURE_SSL_REDIRECT=True,
    SECURE_PROXY_SSL_HEADER=('HTTP_X_FORWARDED_PROTO', 'https'),
)
class RedireccionHttpsTests(TestCase):
    def test_http_redirige_a_https(self):
        respuesta = self.client.get('/login/')
        self.assertEqual(respuesta.status_code, 301)
        self.assertEqual(respuesta['Location'], 'https://testserver/login/')

    def test_peticion_https_del_proxy_no_redirige(self):
        respuesta = self.client.get('/login/', HTTP_X_FORWARDED_PROTO='https')
        self.assertEqual(respuesta.status_code, 200)

    def test_healthcheck_de_railway_en_la_raiz_no_redirige_a_https(self):
        with self.settings(SECURE_REDIRECT_EXEMPT=settings.SECURE_REDIRECT_EXEMPT):
            respuesta = self.client.get('/')
        self.assertNotEqual(respuesta.status_code, 301)
