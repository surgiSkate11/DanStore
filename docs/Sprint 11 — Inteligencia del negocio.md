# Sprint 11 — Inteligencia del negocio

Versión 13.x.x · Rama sugerida `feat/sprint-11-inteligencia` · Depende de: Sprints 2 y 6 (panel, resúmenes por WhatsApp) y de varias semanas de ventas del piloto · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto.**

## 1. Qué cambia en una línea

El sistema deja de solo informar lo vendido y **recomienda qué hacer**: cuánto producir mañana, quiénes son los clientes frecuentes y qué promociones conviene lanzar.

## 2. Historias de usuario

**H1. Cuánto producir mañana**
Como dueño de panadería quiero saber cuánto producir mañana, para no quedarme sin producto ni desperdiciar.
- *Dado* el historial de ventas, *cuando* llega el resumen, *entonces* incluye una sugerencia por producto, por ejemplo "mañana conviene hacer más empanadas, se agotaron a las 11".

**H2. Clientes frecuentes**
Como dueño quiero ver quiénes son mis clientes frecuentes, para atenderlos mejor.
- *Dado* ventas de varias semanas, *cuando* el dueño abre el reporte, *entonces* ve los clientes ordenados por frecuencia, solo de su empresa.

**H3. Promociones automáticas**
Como dueño quiero que el sistema proponga promociones, para vender más en las horas flojas.
- *Dado* una promoción propuesta, *cuando* el dueño la aprueba, *entonces* se aplica o se envía; sin aprobación no sale nada.

## 3. Mejoras para el dueño

| Antes | Con el Sprint 11 |
| --- | --- |
| Decide cuánto producir por intuición | Sugerencia diaria basada en ventas reales |
| No sabe quiénes compran más | Reporte de clientes frecuentes |
| Las promociones son manuales | Propuestas que el dueño aprueba |
| Resumen que solo cuenta lo vendido | Resumen que además aconseja |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Cálculos | Los hace el código sobre `Venta` y sus detalles; la IA solo redacta la recomendación (regla "la IA decide, el código ejecuta") |
| Tareas programadas | Se suman a Celery Beat del Sprint 6; la entrega es por el canal de WhatsApp del dueño |
| Reportes | Pantallas por empresa en el panel |
| Promociones | Modelo y envío por definir |

El método de predicción (reglas simples o modelo) no está decidido en las fuentes.

## 5. Reglas que no se negocian

- **Aislamiento (RS-01):** todo reporte filtra por empresa; prueba con dos empresas.
- **Dinero:** `Decimal` con `ROUND_HALF_UP` a 0,01; precios sin IVA, IVA al facturar.
- **La IA no inventa cifras:** cada número del mensaje sale de una función probada.
- **Promociones por WhatsApp:** los mensajes que inicia el negocio fuera de la ventana de 24 horas requieren plantillas aprobadas por Meta.
- **LOPDP:** contactar a los clientes con promociones es un tratamiento de datos personales; revisar la base legal contra la LOPDP antes de construirlo. A la IA solo se envían agregados.
- **Confirmación del dueño** antes de cualquier acción hacia los clientes.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 13.1.0 | Consultas de ventas por producto y por hora | — |
| 13.2.0 | Sugerencia de producción en el resumen diario | — |
| 13.3.0 | Reporte de clientes frecuentes | — |
| 13.4.0 | Propuesta y aprobación de promociones | Datos |
| 13.5.0 | Envío de promociones aprobadas | Entrega |

## 7. Cómo se prueba

1. Pruebas con datos de ventas fijos y resultados esperados exactos.
2. Prueba de aislamiento con dos empresas.
3. Validar las sugerencias con ventas reales del piloto y con el dueño; en staging (`https://danstore-staging.onrender.com`), por alguien que no lo programó, en celular de 400 px.
4. CI en verde.

## 8. Decisiones pendientes del dueño

- **Método de predicción** y cuántas semanas de historial se necesitan.
- **Definición de "cliente frecuente".**
- **Base legal y consentimiento** para enviar promociones.
- **Qué tipo de promociones** se proponen (descuento, combo, horario).
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Contabilidad, campañas masivas sin aprobación del dueño y comparación entre negocios distintos.
