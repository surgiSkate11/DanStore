# DanStore

Tienda multiempresa hecha en Django 4.2. Cada empresa maneja sus propios productos, catálogos en PDF, clientes, ventas y sorteos, y cobra con Stripe o PayPal. Los datos de una empresa nunca son visibles para otra. Las imágenes se guardan en Cloudinary y la aplicación se despliega en Railway.

## Instalación local

Requisitos: Python 3.11 y Git. Los comandos son de PowerShell y se ejecutan desde la raíz del proyecto.

```powershell
git clone <url-del-repositorio> Tiendita
cd Tiendita
python -m venv env
env\Scripts\python.exe -m pip install -r requirements.txt
```

Crea un archivo `.env` en la raíz con las variables de la sección siguiente. Para generar las claves:

```powershell
# SECRET_KEY
env\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
# FERNET_KEY
env\Scripts\python.exe -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Después aplica las migraciones y arranca el servidor:

```powershell
env\Scripts\python.exe manage.py migrate
env\Scripts\python.exe manage.py createsuperuser
env\Scripts\python.exe manage.py runserver
```

El panel de Django queda en `/<ADMIN_URL>/`. La ruta `/admin/` responde 404 a propósito.

## Variables de entorno

Se leen del archivo `.env` o del entorno, con `python-decouple`. Nunca subas valores reales al repositorio.

| Variable | Obligatoria | Para qué sirve |
| --- | --- | --- |
| `SECRET_KEY` | Sí | Clave criptográfica de Django. |
| `FERNET_KEY` | Sí | Cifra los datos sensibles guardados en la base de datos. |
| `ADMIN_URL` | Sí | Ruta secreta del panel de Django. No puede ser `admin/`. |
| `DATABASE_URL` | Sí, con `DEBUG=False` | Conexión a PostgreSQL. |
| `DEBUG` | No (`False`) | Modo de desarrollo. Con `False` se fuerza HTTPS. |
| `ALLOWED_HOSTS` | Sí, con `DEBUG=False` | Dominios permitidos, separados por coma. |
| `CSRF_TRUSTED_ORIGINS` | No | Orígenes de confianza para formularios, separados por coma. |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | En producción | Almacenamiento de imágenes. |
| `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `EMAIL_TIMEOUT`, `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL` | En producción | Envío de correos. Con `DEBUG=True` los correos se muestran en la consola. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Solo para Google Sheets | Sincronización de productos con hojas de cálculo. |

Seguridad: el login, recuperar contraseña y recuperar usuario aceptan 10 intentos (POST) por minuto desde cada IP; el 11 recibe 429. Los contadores viven en la tabla `ratelimit_cache`, que crea `migrate` (sin variables de entorno nuevas).

## Pruebas

Las pruebas usan su propia base de datos. Para correrlas en local con SQLite (más rápido que una base remota):

```powershell
$env:DATABASE_URL = "sqlite:///db_pruebas.sqlite3"
env\Scripts\python.exe manage.py test           # todas
env\Scripts\python.exe manage.py test ventas    # una app
env\Scripts\python.exe manage.py check --deploy # revisión de seguridad para producción
```

GitHub Actions (`.github/workflows/ci.yml`) corre en cada push y pull request:

1. `check --deploy` con `DEBUG=False`, que falla ante cualquier advertencia.
2. Las pruebas, contra PostgreSQL 16.
3. `pip-audit`, que busca vulnerabilidades conocidas en `requirements.txt`.
4. gitleaks, que busca secretos en los commits.

## Despliegue en Railway

Railway construye la aplicación con Nixpacks y la arranca con gunicorn (`railway.toml` y `Procfile`). Whitenoise sirve los archivos estáticos.

1. Crea un servicio con este repositorio y una base de datos PostgreSQL.
2. Define las variables obligatorias, más `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, Cloudinary y correo.
3. Despliega. Railway no corre las migraciones solo: después de cada cambio de modelo, ejecuta `python manage.py migrate` en el servicio.

Railway revisa la salud de la aplicación en `/`, y esa ruta no se redirige a HTTPS. El resto del sitio sí.
