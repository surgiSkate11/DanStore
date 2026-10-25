# Documentación de DanStore

Índice de los documentos de planificación. Cada sprint tiene su propio archivo con historias de usuario, diseño técnico, tareas, pruebas y decisiones pendientes.

## Documentos generales

| Documento | Para qué sirve |
| --- | --- |
| [Guía de desarrollo DanStore — Fase 0](Guía%20de%20desarrollo%20DanStore%20—%20Fase%200.md) | Visión, diagnóstico, proceso de trabajo, arquitectura del asistente, Sprint 0 paso a paso, requisitos de seguridad (RS-01 a RS-16) |
| [Hoja de ruta DanStore — Producto y sprints](Hoja%20de%20ruta%20DanStore%20—%20Producto%20y%20sprints.md) | Metas del piloto, uso de la IA, elección del modelo, LOPDP y los 13 sprints |

## Sprints

El orden de los Sprints 7 a 12 lo deciden los clientes del piloto. Las versiones continúan la serie: Sprint 0 = 2.x, Sprint 1 = 3.x, y así sucesivamente.

| Sprint | Documento | Objetivo | Estado |
| --- | --- | --- | --- |
| 0 | Resumen en `odd/tasks/sprint-0-cimientos.md` (pasos en la sección 5 de la guía) | Cerrar los riesgos C1 a C7: seguro y con pruebas | Terminado |
| 1 | [Sprint 1 — Pedidos con transferencia](Sprint%201%20—%20Pedidos%20con%20transferencia.md) | Facturación rápida en mostrador y pedidos con pago por transferencia | En curso |
| 2 | [Sprint 2 — Avisos al dueño y panel del día](Sprint%202%20—%20Avisos%20al%20dueño%20y%20panel%20del%20día.md) | Avisos de pedidos por WhatsApp y panel del día | Pendiente |
| 3 | [Sprint 3 — Asistente, consultas por WhatsApp](Sprint%203%20—%20Asistente,%20consultas%20por%20WhatsApp.md) | El asistente responde consultas del cliente | Pendiente |
| 4 | [Sprint 4 — Asistente, pedidos por WhatsApp](Sprint%204%20—%20Asistente,%20pedidos%20por%20WhatsApp.md) | El asistente toma pedidos y comprobantes; privacidad y límites | Pendiente |
| 5 | [Sprint 5 — Menú y comprobantes con IA](Sprint%205%20—%20Menú%20y%20comprobantes%20con%20IA.md) | Leer el menú y los comprobantes con IA | Pendiente |
| 6 | [Sprint 6 — Asistente del dueño](Sprint%206%20—%20Asistente%20del%20dueño.md) | El dueño administra por WhatsApp; resúmenes y alertas | Pendiente |
| 7 | [Sprint 7 — Costos de IA](Sprint%207%20—%20Costos%20de%20IA.md) | Elección de modelo, límites por plan y costo por empresa | Pendiente |
| 8 | [Sprint 8 — Alta autónoma y cobro de suscripción](Sprint%208%20—%20Alta%20autónoma%20y%20cobro%20de%20suscripción.md) | Registro, conexión de WhatsApp y cobro automático | Pendiente |
| 9 | [Sprint 9 — Facturación electrónica SRI](Sprint%209%20—%20Facturación%20electrónica%20SRI.md) | Factura electrónica mediante un proveedor | Pendiente |
| 10 | [Sprint 10 — Domicilios](Sprint%2010%20—%20Domicilios.md) | Zonas, costo de envío, estado "en camino" y aviso | Pendiente |
| 11 | [Sprint 11 — Inteligencia del negocio](Sprint%2011%20—%20Inteligencia%20del%20negocio.md) | Cuánto producir, clientes frecuentes y promociones | Pendiente |
| 12 | [Sprint 12 — Escalar](Sprint%2012%20—%20Escalar.md) | Rendimiento, monitoreo, prueba de seguridad y PWA | Pendiente |

## Reglas comunes a todos los sprints

- Los precios se guardan sin IVA; el IVA se suma al facturar sobre (subtotal − descuento). El envío y otros gastos no llevan IVA.
- La IA decide y el código ejecuta: la IA nunca toca la base de datos y la empresa siempre la pone el sistema.
- Definición de terminado: criterios de aceptación como pruebas, prueba de aislamiento entre empresas, CI en verde, funciona en 400 px, textos en español y probado en staging (`https://danstore-staging.onrender.com`) por alguien que no lo programó.
- Infraestructura: Render, base de datos Neon PostgreSQL y Cloudflare delante.
- Toda dependencia nueva requiere aprobación del dueño y versión fija.
