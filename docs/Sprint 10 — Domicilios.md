# Sprint 10 — Domicilios

Versión 12.x.x · Rama sugerida `feat/sprint-10-domicilios` · Depende de: Sprint 1 (`tipo_entrega`, estados del pedido y envío sin IVA) y Sprint 2 (avisos por WhatsApp) · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto.**

## 1. Qué cambia en una línea

El negocio puede **definir zonas de entrega con su costo de envío**, marcar el pedido "en camino" y avisar al cliente, en lugar de acordar el envío a mano.

## 2. Historias de usuario

**H1. Zonas y costo de envío**
Como dueño quiero definir mis zonas de entrega y su costo, para que el cliente vea cuánto paga de envío.
- *Dado* un pedido a domicilio, *cuando* el cliente indica su zona, *entonces* el envío se calcula en el servidor con el costo de esa zona y se suma al total sin IVA.
- *Dado* una dirección fuera de las zonas, *cuando* el cliente intenta pedir, *entonces* se le informa que no hay entrega ahí.

**H2. Pedido en camino**
Como dueño quiero marcar un pedido como "en camino", para que el cliente sepa que ya salió.
- *Dado* un pedido en `listo` con entrega a domicilio, *cuando* el dueño lo marca en camino, *entonces* el estado cambia y el cliente recibe un aviso.

**H3. Seguimiento del cliente**
Como cliente quiero saber en qué estado está mi domicilio, sin preguntar.
- *Dado* un pedido en camino, *cuando* el cliente abre el enlace de su pedido, *entonces* ve el estado actualizado.

## 3. Mejoras

| Antes | Con el Sprint 10 |
| --- | --- |
| El envío se escribe a mano al vender | El costo sale de la zona elegida |
| El cliente pregunta si ya salió su pedido | Estado "en camino" y aviso al cliente |
| Domicilio solo con pago por transferencia (Sprint 1) | Reglas de cobro a domicilio por decidir |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Zonas de entrega | Modelo por empresa con nombre y costo; campos exactos por definir |
| Estado `en_camino` | Nuevo estado en la máquina de pedidos del Sprint 1, con migración |
| Costo de envío | Se guarda en el campo de envío de la venta, que no lleva IVA |
| Aviso al cliente | Por WhatsApp con el adaptador del Sprint 2; fuera de la ventana de 24 horas requiere plantilla aprobada por Meta |
| Tienda y asistente | Tienda pública (Sprint 1) y `crear_pedido` (Sprint 4) usan la misma lógica de cálculo de envío |

## 5. Reglas que no se negocian

- **El envío no lleva IVA** y lo calcula el servidor, nunca el navegador ni la IA.
- **Dinero:** `Decimal` con `ROUND_HALF_UP` a 0,01.
- **Aislamiento (RS-01):** las zonas y los pedidos son por empresa; prueba con dos empresas en cada pantalla y acción.
- **Rutas públicas limitadas** por IP, igual que en el Sprint 1.
- **LOPDP:** la dirección del cliente es un dato personal; se pide solo lo necesario y se borra a pedido.
- **Estados existentes** (`completada`, `anulada`) se conservan para que los reportes no cambien.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 12.1.0 | Zonas de entrega y costo por empresa (migración) | Datos |
| 12.2.0 | Selección de zona y cálculo del envío en la tienda | — |
| 12.3.0 | Estado `en_camino` y panel del dueño (migración) | Datos |
| 12.4.0 | Aviso al cliente por WhatsApp | Entrega |
| 12.5.0 | Envío por zona en pedidos del asistente | — |

## 7. Cómo se prueba

1. Pruebas de cálculo de envío por zona, fuera de zona y transiciones de estado válidas e inválidas.
2. Prueba de aislamiento con dos empresas.
3. En staging (`https://danstore-staging.onrender.com`), alguien que no lo programó hace un domicilio completo en un celular de 400 px.
4. CI en verde.

## 8. Decisiones pendientes del dueño

- **Cómo se definen las zonas** (por barrio, sector u otro criterio).
- **Costo:** fijo por zona o variable.
- **Cobro:** si el domicilio acepta efectivo a la entrega (hoy está fuera de alcance).
- **Quién entrega** y si se registra al repartidor.
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Mapas y rutas, seguimiento en tiempo real, cobro en efectivo a domicilio (salvo decisión del dueño) y app para repartidores.
