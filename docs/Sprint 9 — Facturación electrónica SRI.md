# Sprint 9 — Facturación electrónica SRI

Versión 11.x.x · Rama sugerida `feat/sprint-9-facturacion-sri` · Depende de: Sprint 1 (IVA validado, % guardado por venta y ventas sin duplicados) · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto:** si tres panaderías piden factura electrónica, este sprint pasa a ser el 7.

## 1. Qué cambia en una línea

Las ventas pueden emitirse como **factura electrónica autorizada por el SRI** mediante un proveedor externo: se integra un proveedor, no se construye desde cero.

## 2. Historias de usuario

**H1. Emitir factura**
Como dueño quiero emitir la factura electrónica de una venta, para cumplir con el SRI.
- *Dado* una venta guardada, *cuando* el dueño emite la factura, *entonces* se envía al proveedor y la venta queda con el estado de autorización.
- *Dado* una venta ya emitida, *cuando* se repite la acción, *entonces* no se genera una segunda factura.

**H2. Entregar al cliente**
Como cliente quiero recibir mi factura, para tener el comprobante tributario.
- *Dado* una factura autorizada, *cuando* se confirma, *entonces* se puede imprimir, descargar o compartir desde el flujo del mostrador.

**H3. Ver el estado**
Como dueño quiero ver si cada factura fue autorizada o rechazada, para corregirla.
- *Dado* una factura rechazada, *cuando* el dueño abre la venta, *entonces* ve el motivo y puede reintentar.

## 3. Mejoras para el dueño

| Antes | Con el Sprint 9 |
| --- | --- |
| La factura del sistema no es electrónica autorizada | Factura autorizada por el SRI vía proveedor |
| Emite en otro sistema contable | Emite desde la misma venta |
| Sin seguimiento | Estado de autorización por venta |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Adaptador del proveedor | Mismo patrón que los adaptadores de WhatsApp e IA: la lógica de dominio no conoce al proveedor, y las pruebas usan un falso |
| Datos de la venta | Reutiliza lo del Sprint 1: precios sin IVA, IVA sobre (subtotal − descuento) con el % guardado en la venta, envío y otros gastos sin IVA |
| Estado de la factura | Campos por definir en `Venta` o en un modelo propio, con su migración |
| Tarea asíncrona | Envío y consulta de autorización fuera de la petición (Celery, ya aprobado en el Sprint 3) |
| Datos del emisor | Por empresa; por definir |

Los detalles técnicos de la integración dependen del proveedor elegido y se definen con él.

## 5. Reglas que no se negocian

- **No se altera el histórico:** las facturas y ventas existentes no se recalculan.
- **Dinero:** `Decimal` y `ROUND_HALF_UP` a 0,01; los totales enviados al proveedor deben coincidir con los de la venta.
- **Sin duplicados:** una venta, una factura (misma idea que el guardado sin duplicados del Sprint 1).
- **Aislamiento (RS-01):** credenciales y facturas de una empresa nunca son visibles para otra; credenciales cifradas (RS-03).
- **RS-10:** firma verificada en las notificaciones del proveedor, si las hay.
- **LOPDP:** los datos del comprador viajan al proveedor; exige contrato con cláusulas de protección de datos y enviar solo los datos necesarios.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 11.1.0 | Elección del proveedor y adaptador con falso para pruebas | Entrega |
| 11.2.0 | Datos del emisor por empresa y estado de la factura (migración) | Datos |
| 11.3.0 | Emisión desde la venta, sin duplicados | Concurrencia |
| 11.4.0 | Consulta de autorización y reintentos | Entrega |
| 11.5.0 | Impresión y compartir de la factura autorizada | — |

## 7. Cómo se prueba

1. Pruebas con el adaptador falso: emisión, repetición (sin duplicado), rechazo y reintento; totales idénticos a los de la venta.
2. Prueba de aislamiento con dos empresas.
3. Ambiente de pruebas del proveedor desde staging (`https://danstore-staging.onrender.com`), por alguien que no lo programó, en celular de 400 px.
4. CI en verde.

## 8. Decisiones pendientes del dueño

- **Proveedor** de facturación electrónica y su costo por documento.
- **Qué negocios deben emitir** y desde qué plan.
- **Qué pasa si el proveedor no responde** (la venta no debe perderse).
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Construir la facturación electrónica desde cero, contabilidad completa y cualquier documento tributario distinto de la factura (no definido en las fuentes).
