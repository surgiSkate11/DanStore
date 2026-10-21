# Sprint 0 — cimientos

Cierra los riesgos C1–C7, C9–C11 de `docs/Guía de desarrollo DanStore — Fase 0.md` (secciones 5 y 9) sin agregar funciones.
Rama: `chore/sprint-0-cimientos`. Commits: `2.<corrección>.<commit> - Descripción` en español.

## Specs

- **S1 (formato de commit):** "los commits llevaran el 2.x.x - Description". Decisión del usuario: "Minor por corrección, patch por commit" (2.1.0 para C1, 2.2.0 para C2… y 2.1.1 si una corrección lleva varios commits).
- **S2 (C1):** "`credentials.json` y `client_secrets.json` están en el repo" → "Corregir la línea rota del `.gitignore`, `git rm --cached`, regenerar las credenciales en Google Cloud". No leer su contenido. No borrarlos del disco.
- **S3 (C2):** "`SECRET_KEY` tiene un valor por defecto escrito en el código" → "Quitar el `default`: si falta la variable, que no arranque".
- **S4 (C3):** "El middleware atrapa cualquier error con `except Exception` y sigue" → "Si falla, la cuenta suspendida entra igual. Atrapar solo lo esperado y registrar el error". Prueba: "una empresa con suscripción vencida que pide `/productos/` debe ser redirigida a `cuenta_suspendida`".
- **S5 (C4):** "`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, HSTS cuando `DEBUG=False`", con `SECURE_PROXY_SSL_HEADER` ("Sin `SECURE_PROXY_SSL_HEADER`, Railway entra en un bucle de redirecciones"). Verificación: "`manage.py check --deploy` sin advertencias".
- **S6 (C5):** "`TIME_ZONE = 'America/Guayaquil'`, `LANGUAGE_CODE = 'es-ec'`", con `USE_TZ = True`.
- **S7 (C6/RS-01):** "la empresa A nunca ve datos de la empresa B". Pruebas de aislamiento en "productos, ventas, clientes y catálogos". "Si una prueba de aislamiento falla, encontraste una fuga de datos real: se corrige antes de seguir."
- **S8 (C10/RS-02):** "`GET /admin/` devuelve 404 y deja una línea en el log `seguridad`; `GET /<ADMIN_URL>` muestra el login". `ADMIN_URL = config('ADMIN_URL')`, sin valor por defecto. Trampas también para `wp-admin|wp-login\.php|\.env|phpmyadmin`. `empresas/middleware.py` usa `settings.ADMIN_URL` en vez de `'/admin/'`.
- **S9 (C11/RS-05):** "`handler403` está en `settings.py`, donde Django no lo lee" → "Moverlo a `tiendita_project/urls.py`, junto con `handler404` y `handler500`".
- **S10 (C7/RS-13):** "GitHub Actions con `manage.py test` y `check --deploy`", más `pip-audit` y gitleaks.
- **S11 (C9):** "README con: qué es DanStore, cómo instalarlo, variables de entorno necesarias (solo los nombres, nunca los valores), cómo correr las pruebas y cómo desplegar."
- **S12 (RS-06):** "11 intentos seguidos desde una IP reciben 429". Requiere `django-ratelimit` (dependencia nueva: decide el usuario).
- **S13 (RS-02 2FA):** "Solo los superusuarios entran al panel, con segundo factor (2FA)". Requiere `django-otp` (dependencia nueva: decide el usuario).

## Tasks

| ID | Specs | Versión | Ruta | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| T0 | S1 | 2.0.0 | inline | hecha | 91938ec |
| T1 | S2 | 2.1.0 | inline | hecha | 5085828 |
| T2 | S3 | 2.2.0 | inline | hecha | e560b17 |
| T3 | S4 | 2.3.0 | inline, TDD, Risk 2 | hecha (verify PASS) | ecd9592 |
| T4 | S5 | 2.4.0 | inline, Risk 2 | hecha (verify PASS) | 1c0d79a |
| T5 | S6 | 2.5.0 | inline | hecha | 83ca4bf |
| T6 | S7 | 2.6.0–2.6.4 | inline, TDD (productos, ventas, clientes, catálogos) | hecha | da4545a (productos), d1d3bc1 (ventas, verify PASS), 9b81458 + 4779d76 (clientes), 2.6.4 (catálogos) |
| T7 | S8 | 2.7.0 | inline, TDD, Risk 2 | pendiente | |
| T8 | S9 | 2.8.0 | inline, TDD | pendiente | |
| T9 | S10 | 2.9.0 | inline, Risk 5 | pendiente | |
| T10 | S11 | 2.10.0 | inline | pendiente | |
| T11 | S12 | — | bloqueada: aprobar `django-ratelimit` | bloqueada | |
| T12 | S13 | — | bloqueada: aprobar `django-otp` | bloqueada | |
| T13 | L11 | 2.11.0 | inline, Risk 2 | pendiente | |
| T14 | L12 | 2.12.0 | inline, TDD, Risk 2 | pendiente | |

Fuera del código (lo hace el usuario): regenerar credenciales de Google Cloud y moverlas a `GOOGLE_CREDENTIALS_JSON`, ambiente `staging` en Railway, variable `ADMIN_URL` en Railway, secretos del repo en GitHub.

## Log

- **L1 (pedido original):** "lee el md de docs para q  hagamos el sprint 0, los commits llevaran el 2.x.x - Description"
- **L2:** Formato de versión elegido: "Minor por corrección, patch por commit".
- **L3 (evidencia):** `.gitignore` termina en `credentials.json: client_secrets.jsonclient_secrets.json` y ambos archivos están versionados (`git ls-files`). `SECRET_KEY` con default en `settings.py:30`; `except Exception` en `empresas/middleware.py:73` y `:87`; `'/admin/'` en `:83`; `handler403` en `settings.py:492`; zona horaria `America/Mexico_City` en `settings.py:381`. `productos`, `catalogos` y `dashboard` tienen 0 pruebas.
- **L4:** `es-ec` con punto decimal (decisión del usuario): `FORMAT_MODULE_PATH` reutiliza los formatos de es_MX porque 50 plantillas imprimen números sin `unlocalize`.
- **L5 (evidencia):** el verificador de T4 detectó que el healthcheck de Railway (`railway.toml` healthcheckPath "/") recibiría 301; se añadió `SECURE_REDIRECT_EXEMPT = [r'^$']`. HSTS preload (W021) silenciado a propósito.
- **L6 (fuga real):** `ProductoForm` no filtraba `tipo_producto` por empresa (mostraba y aceptaba tipos de otras empresas). Corregido en da4545a.
- **L7 (sospecha):** `ventas/views.py` `crear_venta` con `factura_sin_datos` hace `Cliente.objects.get_or_create(ruc_cedula=<POST ruc_cliente>)` sin filtrar por empresa, renombra y asocia el cliente a la empresa actual.
- **L8:** Pruebas locales con `DATABASE_URL=sqlite:///db_pruebas.sqlite3` (Neon tarda >15 min).
- **L9 (GGA bloquea 2.6.1):** "If an empresa has no client with RUC `9999999999` yet, the code reuses the global "consumidor final" client [...] empresa A keeps whatever name empresa B gave that client." Decisión del usuario: "Guardar el nombre en la venta (recomendado)": campo nuevo `nombre_cliente` en `Venta` con migración (copia del nombre al vender, como `ruc_cliente`), y el consumidor final deja de aparecer en la lista de clientes de cada empresa. El rediseño "un cliente por empresa" queda como historia del Sprint 1.
- **L10 (hallazgo previo):** `makemigrations --check` propone `productos/0007_alter_producto_precio...`: un cambio de modelo de `productos` anterior al sprint (commit "Validaciones precios") quedó sin migración. No se toca en T6; decide el usuario.
- **L11 (GGA, deuda previa):** `Venta.empresa` y `ConfiguracionFactura.empresa` tenían `default=1` (asignaban datos a la empresa 1 en silencio): se quita en 2.6.1 con migración 0008. Fuera de T6 quedan, como T13: `productos/sheets_sync.py` guarda la URL de la hoja en la caché global `'last_sheet_url'` (compartida entre empresas) y activa `OAUTHLIB_INSECURE_TRANSPORT=1` también en producción.
- **L12 (fuga en sorteos, fuera de S7):** `sorteos/views.py:191` usa `cliente.total_compras()`, que suma ventas de todas las empresas (`clientes/models.py:31,36` no filtran por empresa): el ranking de sorteos de A cuenta compras hechas en B. Queda como T14.
- **L13 (GGA en 2.6.3):** `api_crear_cliente` con `request.empresa=None` filtraría `empresas=None`. No es explotable: la vista no tiene ruta en ningún `urls.py` (código muerto). Se deja anotado; borrarla decide el usuario.
- **L14 (tamaño):** a 2.6.3 la rama `chore/sprint-0-cimientos` suma ~1.890 líneas en 10 commits. Corte de revisión sugerido: PR 1 = 2.0.0–2.6.x (T0–T6); PR 2 = T7 en adelante. Push y PR los decide el usuario.
- **L15 (catálogos):** sin fuga. 7 pruebas de aislamiento en verde desde el inicio (no hubo RED posible); prueba de mutación: quitar `empresa=request.empresa` en `apply_catalog_filters` hace fallar 6 de 7.
