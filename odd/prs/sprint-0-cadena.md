# Sprint 0: cadena de PRs

Estrategia: **Stacked PRs a `main`**. El historial de `chore/sprint-0-cimientos` es lineal, así que cada rama `pr/sprint-0-NN-*` apunta a un commit de corte, sin reescribir commits. El PR 1 va contra `main`; cada PR siguiente va contra la rama del anterior. Se fusionan en orden (1 → 9); al fusionar uno, el siguiente se reapunta a `main`.

Revisión nativa: rama completa hasta 2.13.0 aprobada (`review-6f5d702ec8a001e5`) y el resto hasta 2.16.1 aprobado (`review-ab129af9b39a038c`). GGA aprobó cada commit. Suite: 133/133.

```
main
 └─ PR 1  01-guia-y-plan
     └─ PR 2  02-configuracion-segura
         └─ PR 3  03-aislamiento-ventas
             └─ PR 4  04-aislamiento-clientes-catalogos
                 └─ PR 5  05-admin-oculto-y-errores
                     └─ PR 6  06-sorteos-sheets-ci-readme
                         └─ PR 7  07-migraciones-productos
                             └─ PR 8  08-limite-ip-y-bloqueo
                                 └─ PR 9  09-2fa-panel
```

En el cuerpo de cada PR, copia el diagrama y marca el actual con 📍.

| PR | Rama | Base | Commits | Líneas (+/-) | Contenido |
| --- | --- | --- | --- | --- | --- |
| 1 | `pr/sprint-0-01-guia-y-plan` | `main` | 2.0.0 | 795 | Guía de la Fase 0, plan del sprint, `AGENTS.md`, `.gga`. `size:exception`: es documentación. |
| 2 | `pr/sprint-0-02-configuracion-segura` | PR 1 | 2.1.0 – 2.6.0 | 391 | C1 credenciales fuera del repo, C2 `SECRET_KEY`, C3 middleware, C4 HTTPS, C5 zona horaria, aislamiento de productos. |
| 3 | `pr/sprint-0-03-aislamiento-ventas` | PR 2 | 2.6.1 | 529 | Aislamiento de ventas, `Venta.nombre_cliente` con migración y copia de datos. `size:exception`: pruebas y migración son una sola unidad. |
| 4 | `pr/sprint-0-04-aislamiento-clientes-catalogos` | PR 3 | 2.6.2 – 2.6.4 | 273 | Aislamiento de clientes (consumidor final oculto) y catálogos. |
| 5 | `pr/sprint-0-05-admin-oculto-y-errores` | PR 4 | 2.7.0 – 2.8.0 | 305 | C10 panel en `ADMIN_URL` y trampa en `/admin/`, C11 páginas 403/404/500. |
| 6 | `pr/sprint-0-06-sorteos-sheets-ci-readme` | PR 5 | 2.12.0 – 2.9.2 | 335 | Ranking de sorteos por empresa, Google Sheets por empresa, CI, README. |
| 7 | `pr/sprint-0-07-migraciones-productos` | PR 6 | 2.13.0 – 2.15.0 (`.gitignore`) | 207 | Migraciones pendientes de productos, stock 0 editable, gitleaks. |
| 8 | `pr/sprint-0-08-limite-ip-y-bloqueo` | PR 7 | 2.15.0 – 2.15.1 | 319 | RS-06 límite por IP (`django-ratelimit`), bloqueo por cuenta sin bypass. |
| 9 | `pr/sprint-0-09-2fa-panel` | PR 8 | 2.16.0 – 2.16.3 | ≈ 330 | RS-02 2FA del panel (`django-otp`, `crear_2fa`), este documento. |

## Verificación por PR

El CI (pruebas, `check --deploy`, `pip-audit`, gitleaks) recién existe desde el PR 6, que agrega `.github/workflows/ci.yml`: los PRs 6 a 9 lo corren, y los PRs 1 a 5 no tienen chequeos propios. Antes de fusionar el PR 1, el CI del PR 6 tiene que estar en verde, porque prueba todo lo acumulado hasta ahí. Para revisar uno en local:

```powershell
git switch pr/sprint-0-03-aislamiento-ventas
env\Scripts\python.exe manage.py test
git diff pr/sprint-0-02-configuracion-segura --stat
```

## Fuera de alcance (siguientes sprints)

- El panel de Django no tiene límite por IP propio (solo bloqueo por cuenta y 2FA).
- El límite por IP confía en `CF-Connecting-IP` (Cloudflare delante de Render). Si la app se expusiera sin Cloudflare, ese header se podría falsear.
- Si la tabla `ratelimit_cache` no existe, el login falla. Desde 2.16.3 Railway corre `migrate` antes de cada despliegue (`preDeployCommand`).
- Consumidor final compartido entre empresas: un cliente por empresa en el Sprint 1.
- Pasos 2 de recuperación de contraseña y usuario sin límite por IP.
