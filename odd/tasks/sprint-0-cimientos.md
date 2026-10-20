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
| T0 | S1 | 2.0.0 | inline | pendiente | Rama + guía y plan |
| T1 | S2 | 2.1.0 | inline | pendiente | |
| T2 | S3 | 2.2.0 | inline | pendiente | |
| T3 | S4 | 2.3.0 | inline, TDD, Risk 2 | pendiente | |
| T4 | S5 | 2.4.0 | inline, Risk 2 | pendiente | |
| T5 | S6 | 2.5.0 | inline | pendiente | |
| T6 | S7 | 2.6.0–2.6.3 | inline, TDD (productos, ventas, clientes, catálogos) | pendiente | |
| T7 | S8 | 2.7.0 | inline, TDD, Risk 2 | pendiente | |
| T8 | S9 | 2.8.0 | inline, TDD | pendiente | |
| T9 | S10 | 2.9.0 | inline, Risk 5 | pendiente | |
| T10 | S11 | 2.10.0 | inline | pendiente | |
| T11 | S12 | — | bloqueada: aprobar `django-ratelimit` | bloqueada | |
| T12 | S13 | — | bloqueada: aprobar `django-otp` | bloqueada | |

Fuera del código (lo hace el usuario): regenerar credenciales de Google Cloud y moverlas a `GOOGLE_CREDENTIALS_JSON`, ambiente `staging` en Railway, variable `ADMIN_URL` en Railway, secretos del repo en GitHub.

## Log

- **L1 (pedido original):** "lee el md de docs para q  hagamos el sprint 0, los commits llevaran el 2.x.x - Description"
- **L2:** Formato de versión elegido: "Minor por corrección, patch por commit".
- **L3 (evidencia):** `.gitignore` termina en `credentials.json: client_secrets.jsonclient_secrets.json` y ambos archivos están versionados (`git ls-files`). `SECRET_KEY` con default en `settings.py:30`; `except Exception` en `empresas/middleware.py:73` y `:87`; `'/admin/'` en `:83`; `handler403` en `settings.py:492`; zona horaria `America/Mexico_City` en `settings.py:381`. `productos`, `catalogos` y `dashboard` tienen 0 pruebas.
