# Sprint 1 — pedidos con pago por transferencia

Objetivo: que un cliente haga un pedido desde la tienda pública, pague por transferencia subiendo su comprobante y el dueño lo confirme con un toque. Fuente: `docs/Guía de desarrollo DanStore — Fase 0.md`, sección 6 (Sprint 1) y sección 9 (RS-07, RS-08).
Rama: `feat/sprint-1-pedidos` desde `main` con el Sprint 0 fusionado. Entrega: `ask-on-risk`, una PR por tarea con Risk. Pruebas: `env\Scripts\python.exe manage.py test`.

## Specs

- **S1 (formato de commit):** se mantiene el formato del Sprint 0, "los commits llevaran el 2.x.x - Description" con "Minor por corrección, patch por commit". Confirmado por el usuario (L9): "Sí, el Sprint 1 usa 3.x.x: minor por tarea, patch por commit." 3.1.0 para T1, 3.2.0 para T2…, y 3.1.1 si una tarea lleva varios commits.
- **S2 (historia 1, pedido):** "Como cliente quiero hacer un pedido desde la tienda online, elegir retiro o entrega y la hora, para no tener que llamar."
  - El carrito de `templates/dashboard/tienda_publica.html` hoy arma un mensaje `wa.me` y no guarda nada en el servidor. Ahora envía el pedido por POST a una ruta pública nueva (`tienda/<slug>/pedido/`) que crea la `Venta`.
  - Precios, IVA y total se calculan en el servidor desde `Producto`. Nunca se acepta un precio enviado por el navegador.
  - Respuesta del usuario (L6): "Sí, los precios que ve el cliente ya incluyen IVA." El total del pedido es la suma de los precios publicados (más envío, menos descuento), y el IVA se desglosa hacia atrás: `subtotal = suma / (1 + porcentaje_iva / 100)`, `iva = suma - subtotal`, ambos redondeados a 0,01. Un pedido de $5,00 se cobra $5,00. Se implementa en un método nuevo de `Venta` para pedidos de la tienda; `calcular_total()` no se modifica (ver L7).
  - Se valida stock al crear el pedido. Un producto agotado o inexistente devuelve un error claro y no crea nada.
  - `DetalleVenta` guarda una fila por unidad (convención actual del proyecto, ver L3): 3 panes son 3 filas.
  - Campos nuevos en `Venta`: `tipo_entrega` (retiro, domicilio), `hora_entrega`, `canal` (mostrador, tienda, whatsapp; las ventas existentes quedan en `mostrador`), `telefono_contacto`, `direccion_entrega` (solo domicilio) y `token` (UUID, para la página del pedido).
- **S3 (estados del pedido):** "`estado` (pendiente_pago, pagado, en_preparacion, listo, entregado, cancelado)". Decisión para no romper reportes (ver L4): se agregan `pendiente_pago`, `pagado`, `en_preparacion` y `listo` a `ESTADO_CHOICES`, y se reutilizan los existentes, `completada` como "entregado" y `anulada` como "cancelado". Los reportes que hoy cuentan `completada` siguen contando solo ventas cerradas. Las ventas de mostrador siguen naciendo en `completada`.
- **S4 (datos del cliente y privacidad):** el formulario público pide nombre y teléfono; la cédula es opcional.
  - Sin cédula: la venta usa el cliente "consumidor final" (`ConfiguracionFactura.id_consumidor_final`).
  - Con cédula de un `Cliente` que ya existe: se vincula a esta empresa (`empresas.add`) **sin modificar** su nombre, teléfono, correo ni dirección, y la respuesta no muestra ningún dato guardado de esa persona.
  - Con cédula nueva: se crea el `Cliente` y se vincula a la empresa.
  - Nombre y teléfono del pedido quedan en la `Venta` (`nombre_cliente`, `telefono_contacto`).
- **S5 (historia 2, pago):** "Como cliente quiero ver las cuentas del negocio y subir la foto de mi transferencia, para pagar como siempre pago."
  - Modelo nuevo `CuentaBancaria`: "`empresa`, `banco`, `tipo`, `numero`, `titular`, `activa`. Es la cuenta de cada negocio, distinta de la de `ConfiguracionSaaS`, que es la tuya". El dueño la administra desde la configuración de su tienda.
  - Página del pedido `tienda/<slug>/pedido/<token>/`: muestra estado, detalle, total, las cuentas activas y el formulario para subir el comprobante. Se entra por el `token` UUID, nunca por el id numérico.
  - Modelo nuevo `ComprobantePago`: "`venta`, `imagen` (Cloudinary), `monto_declarado`, `estado` (pendiente, aprobado, rechazado), `revisado_por`, `revisado_en`".
- **S14 (efectivo al retirar):** respuesta del usuario (L8): "Sí, también acepta efectivo al retirar."
  - Al hacer el pedido, el cliente elige el pago: transferencia o efectivo al retirar. Se guarda en el `metodo_pago` que ya existe (`transferencia` o `efectivo`).
  - Efectivo solo se ofrece con `tipo_entrega = retiro`. Con domicilio, el pago es por transferencia.
  - Un pedido en efectivo nace en `pendiente_pago`, sin comprobante. En la página del pedido no aparecen las cuentas ni el formulario de subida, sino "Pagas al retirar".
  - El dueño lo acepta con un toque y pasa directo a `en_preparacion` (en ese momento se descuenta el stock, como en S7). Cuando el cliente retira y paga, el dueño lo marca `completada`.
- **S6 (RS-08, archivos subidos):** "solo imágenes reales verificadas con Pillow, máximo 5 MB, nombre aleatorio". Verificación: "Subir un .html renombrado a .jpg es rechazado".
- **S7 (historia 3, confirmación):** "Como dueño quiero confirmar o rechazar un pago con un toque, para no revisar pedidos a mano."
  - Panel de pedidos para el dueño con los pedidos de su empresa por estado y la imagen del comprobante.
  - Confirmar: el comprobante pasa a `aprobado`, la venta a `pagado`, y se descuenta el stock en ese momento, dentro de `transaction.atomic()` con `select_for_update()` sobre los productos. Si ya no alcanza el stock, no se confirma y se avisa al dueño.
  - Rechazar: el comprobante pasa a `rechazado` y la venta sigue en `pendiente_pago`, para que el cliente suba otro.
  - El dueño avanza el pedido: `pagado` → `en_preparacion` → `listo` → `completada`. Puede cancelarlo (`anulada`) mientras no esté `completada`.
  - Si se anula un pedido al que ya se le descontó el stock (transferencia confirmada o efectivo aceptado), el stock se devuelve en la misma transacción. Así un cliente que no vino a retirar no deja productos "fantasma" agotados.
- **S8 (criterio de aceptación):** "dado un pedido de $5,00, cuando el cliente sube su comprobante, entonces el pedido queda en `pendiente_pago` y el dueño lo ve en su panel con la imagen. Con un toque pasa a `pagado`."
- **S9 (aislamiento):** "Hay una prueba que confirma que otra empresa no ve esos datos". Aplica a `CuentaBancaria`, `ComprobantePago`, el panel de pedidos y las acciones de confirmar, rechazar y avanzar (una empresa que intenta confirmar el pedido de otra recibe 404).
- **S10 (límite en rutas públicas):** crear pedido y subir comprobante usan el mismo `django_ratelimit` y la misma caché `ratelimit` del Sprint 0. Supuesto: 10 pedidos y 10 subidas por minuto por IP.
- **S11 (RS-07, cabeceras):** "Content-Security-Policy, Referrer-Policy, Permissions-Policy, `X-Frame-Options: DENY`". Verificación: "Revisar con securityheaders.com sobre staging". `django-csp` es una dependencia nueva: se agrega con versión fija solo después de que el usuario lo apruebe.
- **S12 (WhatsApp como aviso opcional):** después de crear el pedido, la tienda puede seguir mostrando el botón `wa.me` existente, ahora con el número de pedido y el enlace a la página del pedido. El pedido ya está guardado aunque el cliente no lo toque.
- **S13 (definición de terminado, de la guía):**
  - "Sus criterios de aceptación pasan como pruebas automáticas"
  - "Hay una prueba que confirma que otra empresa no ve esos datos"
  - "`manage.py test` y `manage.py check --deploy` pasan en GitHub Actions"
  - "Funciona en un celular de 400 px de ancho"
  - "Los textos de la interfaz están en español"
  - "Está en staging y alguien que no la programó la probó"

## Tasks

| ID | Specs | Versión | Ruta | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| T1 | S2, S3, S4 | 3.1.0 | inline, TDD, Risk 1 (migración de `Venta`) | pendiente | |
| T2 | S5, S9 | 3.2.0 | inline, TDD | pendiente | |
| T3 | S2, S4, S10, S14 | 3.3.0 | inline, TDD, Risk 2 (ruta pública nueva) | pendiente | |
| T4 | S5, S6, S9, S10 | 3.4.0 | inline, TDD, Risk 2 (subida de archivos) | pendiente | |
| T5 | S7, S8, S9, S14 | 3.5.0 | inline, TDD, Risk 1 y 4 (stock con bloqueo) | pendiente | |
| T6 | S11 | 3.6.0 | inline, Risk 5 (dependencia nueva, requiere aprobación) | pendiente | |
| T7 | S12 | 3.7.0 | inline | pendiente | |
| T8 | S13 | 3.8.0 | inline: README, guía y demo en staging | pendiente | |

Orden: T1 → T2 → T3 → T4 → T5 (cada una necesita la anterior). T6 y T7 son independientes y pueden ir en cualquier momento después de T3.

## Log

- **L1 (pedido original, 2026-10-23):** "dame el md del sprint 1"
- **L2 (fuente):** las historias, modelos y el criterio de aceptación salen de la sección 6 de la guía; los requisitos RS-07 y RS-08, de la sección 9. Ambos se citan textuales en las specs.
- **L3 (hallazgos del código, 2026-10-23):**
  - `Venta` ya tiene `estado` con `completada` y `anulada`, `metodo_pago` con `transferencia` y `origen` (`sistema`, `sheets`). La guía proponía `estado` como campo nuevo; en realidad hay que ampliarlo (S3).
  - `DetalleVenta` no tiene `cantidad`: guarda una fila por unidad y `calcular_total()` suma `precio_unitario`. Se respeta esa convención (S2).
  - `Cliente` es global (`ruc_cedula` único en todo el sistema) y se vincula a empresas por `empresas` (ManyToMany). Por eso un formulario público no puede editar clientes existentes (S4).
  - El carrito de `tienda_publica.html` termina en un enlace `wa.me` y no crea nada en el servidor (S2, S12).
  - El despliegue está en Render, no en Railway. El staging del Sprint 0 (T21) sigue pendiente y S13 lo necesita.
- **L4 (decisión de diseño):** reutilizar `completada` y `anulada` en vez de agregar `entregado` y `cancelado`. Así no cambia lo que ya cuentan los reportes y el panel. Si el usuario prefiere los nombres de la guía, se reabre T1 y se revisan los reportes que filtran por estado.
- **L5 (preguntas abiertas para el usuario, antes de T3):**
  - ~~¿Los precios que ve el cliente en la tienda ya incluyen IVA?~~ Respondida en L6.
  - ~~¿Se acepta también "efectivo al retirar", además de transferencia?~~ Respondida en L8.
  - ~~¿El Sprint 1 usa la serie de versiones `3.x.x` (S1)?~~ Respondida en L9. No quedan preguntas abiertas.
- **L6 (respuesta del usuario, 2026-10-23):** "Sí, los precios que ve el cliente ya incluyen IVA." Se reescribe S2: el IVA se desglosa del precio, no se suma.
- **L7 (hallazgo, fuera del alcance del sprint):** `Venta.calcular_total()` (`ventas/models.py:113`) suma el IVA encima de la suma de precios: `total = subtotal + subtotal × porcentaje_iva`. Si los precios del mostrador también incluyen IVA, las ventas de mostrador estarían cobrando IVA dos veces (un producto de $5,00 sale en $5,75). No se cambia en este sprint porque lo usan todas las ventas y los reportes (Risk 3). Decide el usuario: revisar una venta real de mostrador y, si está mal, abrir una tarea propia con pruebas.
- **L8 (respuesta del usuario, 2026-10-23):** "Sí, también acepta efectivo al retirar." Se agrega S14 y se amplía S7 con la devolución de stock al anular. Decisiones: efectivo solo con retiro (cobrar a domicilio necesita un repartidor que maneje dinero, y nadie lo pidió); el stock se descuenta cuando el dueño acepta el pedido, no cuando el cliente lo crea, para que un pedido que nadie va a retirar no bloquee productos; al anular, el stock vuelve.
- **L9 (respuesta del usuario, 2026-10-23):** "Sí, el Sprint 1 usa 3.x.x: minor por tarea, patch por commit." Se confirma S1. Siguiente paso: crear la rama `feat/sprint-1-pedidos` desde `main` con el Sprint 0 fusionado y empezar T1.
