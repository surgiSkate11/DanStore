# DanStore

Tienda multiempresa hecha en Django 4.2. Cada empresa maneja sus propios productos, catálogos en PDF, clientes, ventas y sorteos, y cobra con Stripe o PayPal. Los datos de una empresa nunca son visibles para otra. Las imágenes se guardan en Cloudinary y la aplicación se despliega en Render.

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

## Panel de administración con 2FA

El panel de Django (`/<ADMIN_URL>`) es solo para superusuarios y pide, además de la contraseña, un código de 6 dígitos de una app autenticadora. Quien no tenga dispositivo 2FA no entra, aunque sepa la contraseña.

Para activarlo, crea el dispositivo de un superusuario existente (PowerShell):

```powershell
env\Scripts\python.exe manage.py crear_2fa <usuario>
```

El comando imprime la clave en base32 y la URL `otpauth://`. Escribe la clave a mano en Google Authenticator o Authy (cuenta basada en tiempo) y guárdala en un lugar seguro. Para cambiar de teléfono o regenerarla, repite el comando con `--reemplazar`.

En Render, ejecútalo una sola vez desde la pestaña **Shell** del servicio: `python manage.py crear_2fa <usuario>`. El 2FA aplica solo al panel de Django: el login normal (`/login/`) no lo pide.

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

## Despliegue en Render

Render arranca la aplicación con gunicorn detrás de Cloudflare y de su propio proxy, que termina HTTPS. Whitenoise sirve los archivos estáticos.

1. Crea un Web Service con este repositorio y una base de datos PostgreSQL.
2. En **Environment**, define las variables obligatorias, más `DEBUG=False`, `ALLOWED_HOSTS` (incluye tu dominio `*.onrender.com`), `CSRF_TRUSTED_ORIGINS`, Cloudinary y correo.
3. En **Settings → Start Command**, usa `python manage.py migrate --noinput && gunicorn tiendita_project.wsgi:application`. Así cada despliegue migra antes de recibir tráfico; si la migración falla, la app no arranca. (El *Pre-Deploy Command* de Render hace lo mismo, pero solo existe en los planes pagos.)

El límite de intentos por IP mira el último valor de `X-Forwarded-For`, que agrega el proxy de Render: si es un borde de Cloudflare, usa `CF-Connecting-IP` (o `True-Client-IP`); si no, alguien entró directo a Render y se usa esa IP, porque los headers de Cloudflare los pudo inventar. `railway.toml` queda de una prueba anterior con Railway y Render no lo usa.
