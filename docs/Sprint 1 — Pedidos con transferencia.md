# Sprint 1 — Pedidos con pago por transferencia

Versión 3.x · Rama `feat/sprint-1-pedidos` · Plan técnico: `odd/tasks/sprint-1-pedidos-transferencia.md`

## 1. Qué cambia en una línea

Hoy el carrito de la tienda pública solo arma un mensaje de WhatsApp y no guarda nada. Con el Sprint 1, **el pedido queda registrado en el sistema**, el cliente paga por transferencia (o en efectivo al retirar) y el dueño lo confirma con un toque.

## 2. Mejoras de la nueva versión

### Para el cliente final

| Antes | Con el Sprint 1 |
| --- | --- |
| Arma el carrito y escribe por WhatsApp | Envía el pedido desde la tienda y queda guardado |
| No elige cómo recibirlo | Elige **retiro** o **domicilio** y la **hora** |
| Pide las cuentas por chat | Ve las cuentas bancarias del negocio en la página de su pedido |
| Manda la foto de la transferencia por chat | Sube el comprobante en la página de su pedido |
| No sabe en qué va su pedido | Consulta el estado con un enlace privado (UUID, no un número que se pueda adivinar) |
| Solo transferencia | También **efectivo al retirar** |

### Para el dueño del negocio

| Antes | Con el Sprint 1 |
| --- | --- |
| Copia el pedido del chat a una venta | La venta se crea sola, con canal `tienda` |
| Revisa el banco y responde a mano | Panel de pedidos por estado, con la imagen del comprobante |
| — | **Confirma o rechaza** el pago con un toque |
| Ajusta el stock a mano | El stock se descuenta al confirmar y vuelve si el pedido se anula |
| — | Administra sus cuentas bancarias desde la configuración de la tienda |

### Estados de un pedido

```
pendiente_pago → pagado → en_preparacion → listo → completada (entregado)
        ↘ anulada (cancelado), en cualquier momento antes de completada
```

Efectivo al retirar: `pendiente_pago` → el dueño lo acepta → `en_preparacion` → `listo` → `completada` al cobrar.

Se reutilizan `completada` y `anulada`, que ya existen, para que los reportes actuales no cambien.

## 3. Reglas que no se negocian

- **El precio lo calcula el servidor**, nunca el navegador. Los precios publicados ya incluyen IVA: un pedido de $5,00 se cobra $5,00 y el IVA se desglosa hacia atrás.
- **Una empresa nunca ve ni toca pedidos, cuentas o comprobantes de otra** (prueba de aislamiento en cada pantalla y acción).
- **Comprobantes seguros (RS-08):** solo imágenes reales verificadas con Pillow, máximo 5 MB y nombre aleatorio. Un `.html` renombrado a `.jpg` se rechaza.
- **Rutas públicas limitadas:** 10 pedidos y 10 subidas por minuto por IP, con el mismo límite del Sprint 0.
- **Datos de clientes existentes protegidos:** si alguien escribe una cédula que ya existe, el pedido se vincula sin modificar ni mostrar los datos guardados de esa persona.

## 4. Tareas y versiones

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 3.1.0 | Campos nuevos en `Venta` y estados del pedido (migración) | Datos |
| 3.2.0 | Cuentas bancarias por empresa | — |
| 3.3.0 | Ruta pública para crear el pedido | Seguridad |
| 3.4.0 | Página del pedido y subida del comprobante | Seguridad |
| 3.5.0 | Panel del dueño: confirmar, rechazar, avanzar y anular (stock con bloqueo) | Datos y concurrencia |
| 3.6.0 | Cabeceras de seguridad RS-07 (`django-csp`) | Dependencia nueva |
| 3.7.0 | Aviso por WhatsApp con el enlace del pedido | — |
| 3.8.0 | README, guía y demo en staging | — |

Orden: 3.1 → 3.2 → 3.3 → 3.4 → 3.5. Las tareas 3.6 y 3.7 pueden ir en cualquier momento después de 3.3.

## 5. Cómo se prueba antes de producción

1. Cada tarea se fusiona a `main` con el CI en verde.
2. Staging (`https://danstore-staging.onrender.com`) se despliega solo desde `main`.
3. Alguien que no lo programó hace el recorrido en un celular de 400 px de ancho: pedido, comprobante, confirmación y anulación.
4. Recién entonces se hace **Manual Deploy** en producción.

**Criterio de aceptación de la guía:** dado un pedido de $5,00, cuando el cliente sube su comprobante, el pedido queda en `pendiente_pago` y el dueño lo ve en su panel con la imagen. Con un toque pasa a `pagado`.

## 6. Decisiones pendientes del dueño

- **`django-csp` (tarea 3.6):** es una dependencia nueva y necesita tu aprobación.
- **IVA en ventas de mostrador:** `Venta.calcular_total()` suma el IVA encima del precio. Si los precios de mostrador también lo incluyen, se estaría cobrando dos veces ($5,00 → $5,75). Revisá una venta real; si está mal, se abre una tarea aparte.

## 7. Fuera de alcance

Facturación electrónica del SRI, cobro en efectivo a domicilio, avisos automáticos por WhatsApp Cloud API (Sprint 2) y el asistente de IA (Sprints 3 y 4).
