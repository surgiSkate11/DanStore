# Sprint 2 — Avisos al dueño y panel del día

Versión 4.x.x · Rama sugerida `feat/sprint-2-avisos-panel` · Depende de: Sprint 1 (pedidos con estados y pago confirmado) y de la verificación del negocio en Meta Business · Calendario original: semanas 4–5

## 1. Qué cambia en una línea

El dueño deja de enterarse de los pedidos al abrir el sistema: **recibe un aviso por WhatsApp de cada pedido pagado**, ve el día completo en un tablero y un negocio nuevo se configura en menos de 15 minutos. Nace la app `asistente` con el canal de WhatsApp de cada negocio.

## 2. Historias de usuario

**H1. Aviso de pedido pagado**
Como dueño quiero un aviso por WhatsApp de cada pedido pagado, para prepararlo a tiempo.
- *Dado* un pago confirmado, *cuando* el pedido pasa a `pagado`, *entonces* el dueño recibe el aviso en menos de 1 minuto con productos, total y hora de entrega.
- *Dado* un negocio sin canal de WhatsApp configurado, *cuando* se confirma un pago, *entonces* el pedido se confirma igual y el fallo del aviso queda registrado.

**H2. Panel del día**
Como dueño quiero ver en una pantalla los pedidos de hoy por estado, las ventas del día y los productos con poco stock.
- *Dado* pedidos en varios estados, *cuando* el dueño abre el panel, *entonces* ve las columnas Por pagar, Pagado, En preparación y Listo, solo con pedidos de su empresa.

**H3. Configuración guiada**
Como dueño nuevo quiero configurar mi tienda en menos de 15 minutos con un asistente paso a paso.
- *Dado* una empresa recién creada, *cuando* el dueño sigue los pasos, *entonces* queda con tienda y cuenta bancaria configuradas sin ayuda externa.

## 3. Mejoras para el dueño

| Antes | Con el Sprint 2 |
| --- | --- |
| Entra al sistema a ver si hay pedidos nuevos | Recibe el aviso en su WhatsApp con productos, total y hora |
| Cuenta al final del día lo que vendió | El panel muestra pedidos de hoy por estado y ventas del día |
| Revisa producto por producto cuál se acaba | El panel lista los productos con poco stock |
| Configura la tienda sin una guía | Asistente paso a paso, meta de 15 minutos |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Modelo `CanalWhatsApp` | `empresa`, `phone_number_id`, `token` (cifrado con el campo de `empresas/fields.py`), `numero_dueno` |
| `asistente/adaptadores/whatsapp.py` | Cliente de WhatsApp Cloud API para enviar mensajes |
| Plantilla de mensaje | Tipo *utilidad*, aprobada por Meta, para el aviso de pedido (fuera de la ventana de 24 horas solo se envían plantillas aprobadas) |
| Panel tipo tablero | Columnas Por pagar, Pagado, En preparación, Listo; reutiliza los estados del Sprint 1 |
| Registro de seguridad (RS-14) | Logins fallidos, rutas trampa y errores enviados a Sentry |
| Copia de la base (RS-16) | Copia diaria fuera del servidor y restauración probada en staging |
| Dependencia nueva | `sentry-sdk` — **requiere aprobación** y versión fija |

Alta del número de WhatsApp: con los primeros clientes se hace a mano, junto al dueño. El registro integrado (Tech Provider de Meta) queda para cuando haya más clientes (Sprint 8).

Las pruebas usan un adaptador falso de WhatsApp: no se envían mensajes reales ni se gasta cuota.

## 5. Reglas que no se negocian

- **Aislamiento (RS-01):** el panel, el canal y el aviso son por empresa; una empresa nunca ve el canal ni los pedidos de otra.
- **Secretos (RS-03):** el token de WhatsApp se guarda cifrado y nunca en el repositorio ni en los registros.
- **Registro (RS-14):** los intentos fallidos y los errores quedan registrados y avisados.
- **Continuidad (RS-16):** sin restauración probada no se cierra el sprint.
- **Dinero:** los totales del aviso usan la misma regla del Sprint 1 (precios sin IVA, IVA sobre subtotal menos descuento; envío y otros gastos sin IVA).
- **Datos personales (LOPDP):** el aviso al dueño lleva solo lo necesario del pedido (productos, total, hora).

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 4.1.0 | App `asistente` y modelo `CanalWhatsApp` con token cifrado (migración) | Datos |
| 4.2.0 | Adaptador de WhatsApp (envío) y plantilla de utilidad | Entrega |
| 4.3.0 | Aviso al dueño al confirmar el pago | Entrega |
| 4.4.0 | Panel del día (tablero, ventas del día, stock bajo) | — |
| 4.5.0 | Asistente de configuración paso a paso | — |
| 4.6.0 | Registro de seguridad y Sentry (RS-14) | Entrega |
| 4.7.0 | Copia diaria y restauración probada (RS-16) | Entrega |

## 7. Cómo se prueba

1. Pruebas automáticas con el adaptador falso, incluida una prueba de aislamiento entre dos empresas para el panel y el canal.
2. CI en verde (`manage.py test` y `check --deploy`).
3. En staging (`https://danstore-staging.onrender.com`), alguien que no lo programó confirma un pago y cronometra el aviso en un celular de 400 px (menos de 1 minuto).
4. Restaurar una copia de la base en staging.
5. Medir el tiempo de configuración de una tienda nueva (meta: 15 minutos).

## 8. Decisiones pendientes del dueño

- **`sentry-sdk`:** aprobar la dependencia y su versión fija.
- **Verificación de Meta Business:** debe estar completa; si no, el aviso real queda sin probar.
- **Envío del aviso:** Celery y Redis llegan en el Sprint 3. Decidir si el aviso se envía directo con reintento o si Celery se adelanta a este sprint.
- **Qué es "poco stock":** el umbral no está definido en las fuentes.
- **Copia diaria (RS-16):** dónde se guarda (la base es Neon PostgreSQL) y quién la restaura.

## 9. Fuera de alcance

Recibir mensajes de clientes (Sprint 3), alta autónoma del número con Tech Provider (Sprint 8), resumen diario, resumen semanal y alerta de stock por WhatsApp (Sprint 6), y Cloudflare (RS-15, antes del piloto).
