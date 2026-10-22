# DanStore (Tiendita)

Tienda multiempresa en Django 4.2 con catálogos, ventas, clientes, sorteos y pagos (Stripe, PayPal). Se despliega en Render.

## Comandos (PowerShell, desde la raíz)
- Python del proyecto: `env\Scripts\python.exe` (Python 3.11)
- Servidor local: `env\Scripts\python.exe manage.py runserver`
- Pruebas: `env\Scripts\python.exe manage.py test`
- Una app: `env\Scripts\python.exe manage.py test ventas`
- Chequeo: `env\Scripts\python.exe manage.py check`
- Migraciones: `env\Scripts\python.exe manage.py makemigrations` y luego `migrate`

## Estructura
- `tiendita_project/`: settings, urls y wsgi. La configuración se lee de `.env` con python-decouple.
- Apps: `dashboard`, `usuarios`, `productos`, `catalogos`, `clientes`, `ventas`, `sorteos`, `empresas`.
- Plantillas en `templates/<app>/`, estáticos en `static/`. Imágenes en Cloudinary.
- Producción: Render (gunicorn + whitenoise, detrás de Cloudflare). La IP del cliente sale de `tiendita_project.utils.obtener_ip_cliente`: no leas `X-Forwarded-For` ni `CF-Connecting-IP` a mano.

## Reglas
- No leas ni muestres `.env`, `client_secrets.json` ni `credentials.json`: tienen secretos.
- No agregues dependencias sin preguntar. Si agregas una, fija su versión en `requirements.txt`.
- Todo cambio de modelo lleva su migración en el mismo commit.
- Los datos de una empresa nunca deben ser visibles para otra: filtra siempre por empresa.
- Antes de decir "listo", corre las pruebas de la app que tocaste y muestra el resultado.
- Textos de la interfaz en español.
