from django.apps import AppConfig


class EmpresasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'empresas'

    def ready(self):
        import empresas.signals  # noqa: F401 — registra la señal post_save de Empresa