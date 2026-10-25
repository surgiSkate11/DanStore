# Sprint 6 — Asistente del dueño

Versión 8.x.x · Rama sugerida `feat/sprint-6-asistente-dueno` · Depende de: Sprints 2 (canal y plantillas), 3 (Celery, orquestador) y 5 · Calendario original: semanas 12–13

## 1. Qué cambia en una línea

El dueño **administra su negocio escribiendo por WhatsApp**: cambia precios y stock, confirma pagos, y recibe un resumen diario a las 20:00, uno semanal los lunes y alertas de stock bajo. Toda acción que cambia datos pide confirmación. Al cerrar este sprint empieza el piloto pagado con 3 a 5 negocios.

## 2. Historias de usuario

**H1. Cambiar precios y stock**
Como dueño quiero cambiar precios y stock escribiendo por WhatsApp, para no abrir el sistema.
- *Dado* el mensaje "Sube el pan de yuca a 30 centavos", *cuando* el asistente identifica al dueño por su número, *entonces* pregunta "¿Cambio el pan de yuca de $0,25 a $0,30? Responde SÍ".
- *Dado* la respuesta SÍ, *cuando* se confirma, *entonces* `cambiar_precio` actualiza el producto de su empresa y el cambio queda registrado.
- *Dado* un cliente que pide lo mismo, *cuando* escribe, *entonces* no ocurre nada: esa herramienta no existe para su rol.

**H2. Resúmenes**
Como dueño quiero un resumen diario a las 20:00 y uno semanal los lunes.
- *Dado* ventas del día, *cuando* llegan las 20:00, *entonces* recibe un mensaje con las ventas y el número de pedidos.

**H3. Alerta de stock**
Como dueño quiero una alerta cuando un producto esté por acabarse.
- *Dado* un producto bajo el umbral, *cuando* corre `alerta_stock_bajo`, *entonces* el dueño recibe el aviso una vez.

## 3. Mejoras para el dueño

| Antes | Con el Sprint 6 |
| --- | --- |
| Entra al sistema para cambiar un precio | Lo escribe en WhatsApp y confirma con SÍ |
| Cuenta lo vendido al final del día | Recibe el resumen a las 20:00 y el semanal los lunes |
| Se entera de que un producto se agotó al venderlo | Recibe una alerta antes |
| Revisa pagos en el panel | `confirmar_pago` desde el chat, con confirmación |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Herramientas del rol dueño | `cambiar_precio`, `cambiar_stock`, `resumen_ventas`, `confirmar_pago` (más `importar_menu_desde_foto` del Sprint 5 y las del cliente) |
| `dominio/permisos.py` | Reconoce al dueño o empleado por el número guardado en su `UserProfile`; el orquestador decide el rol antes de llamar a la IA |
| Confirmación | Estado pendiente por conversación; solo un SÍ del mismo número ejecuta la acción |
| Celery Beat | `resumen_diario`, `resumen_semanal`, `alerta_stock_bajo` como tareas del sistema |
| Plantillas de Meta | Los resúmenes y alertas los inicia el negocio fuera de la ventana de 24 horas: requieren plantillas aprobadas |
| Reutilización | Mismas funciones de dominio que usan las pantallas web (ventas, stock, confirmación de pago del Sprint 1) |

## 5. Reglas que no se negocian

- **Confirmación del dueño** antes de acciones que mueven dinero o cambian datos (`cambiar_precio`, `cambiar_stock`, `confirmar_pago`).
- **Registro de seguridad (RS-14):** los cambios de precio y de permisos quedan registrados.
- **Aislamiento (RS-01):** cada herramienta opera solo sobre la empresa del canal; prueba con dos empresas.
- **La IA decide, el código ejecuta:** el precio nuevo lo valida el código (no negativo, `Decimal`, redondeo `ROUND_HALF_UP` a 0,01). Los precios se guardan sin IVA.
- **RS-11:** un cliente no puede obtener herramientas del dueño ni haciéndose pasar por él.
- **Resúmenes calculados por el código**, no por la IA: la IA solo redacta.
- **LOPDP:** los resúmenes contienen datos del negocio; a la IA se envían solo agregados.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 8.1.0 | Reconocer al dueño por teléfono y permisos por rol | Seguridad |
| 8.2.0 | Confirmación por SÍ con estado pendiente | Seguridad |
| 8.3.0 | `cambiar_precio` y `cambiar_stock` con registro (RS-14) | Datos |
| 8.4.0 | `resumen_ventas` y `confirmar_pago` | Datos |
| 8.5.0 | Celery Beat: `resumen_diario` y `resumen_semanal` | Entrega |
| 8.6.0 | `alerta_stock_bajo` | Entrega |
| 8.7.0 | Plantillas aprobadas por Meta y casos nuevos en el set | — |

## 7. Cómo se prueba

1. Pruebas con adaptadores falsos: SÍ confirma, otra respuesta cancela, cliente sin acceso a las herramientas del dueño.
2. Pruebas de aislamiento con dos empresas y de las tareas programadas.
3. Set de conversaciones guionadas ampliado con casos del dueño; sigue en 0 precios inventados.
4. CI en verde; staging (`https://danstore-staging.onrender.com`) probado por alguien que no lo programó, en celular de 400 px.
5. Antes del piloto, revisar la lista "Listo para vender" de la guía (sección 8) y RS-15 (Cloudflare).

## 8. Decisiones pendientes del dueño

- **Empleados:** la guía da las mismas herramientas a "dueño o empleado"; definir si un empleado puede cambiar precios y confirmar pagos.
- **Umbral de stock bajo** y horario exacto de la alerta.
- **Vencimiento de una confirmación pendiente.**
- **Campo de teléfono:** verificar que `UserProfile` ya lo tenga o si requiere migración.
- **Condiciones del piloto:** precio y descuento (se mide con costes reales).

## 9. Fuera de alcance

Predicción de producción y promociones (Sprint 11), límites de costo por plan (Sprint 7) y facturación electrónica (Sprint 9).
