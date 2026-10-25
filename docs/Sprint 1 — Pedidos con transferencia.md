# Sprint 1 — Facturación rápida y pedidos con pago por transferencia

Versión 3.x.x · Ramas `feat/facturacion-rapida` (3.1.0–3.7.0) y `feat/sprint-1-pedidos` (3.8.0 en adelante) · Planes técnicos: `odd/tasks/facturacion-rapida.md` y `odd/tasks/sprint-1-pedidos-transferencia.md`

## 1. Qué cambia en una línea

Hoy el carrito de la tienda pública solo arma un mensaje de WhatsApp y no guarda nada, y la venta de mostrador acepta datos inválidos y es lenta. Con el Sprint 1, **la venta de mostrador se registra e imprime en menos de 30 segundos con cálculos correctos**, y **el pedido de la tienda queda registrado** en el sistema: el cliente paga por transferencia (o en efectivo al retirar) y el dueño lo confirma con un toque.

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

## 3. Facturación rápida en mostrador

Prioridad del dueño del producto antes de los pedidos por transferencia. Versiones 3.1.0 a 3.7.0. Evoluciona la pantalla `crear_venta`; no crea una pantalla nueva y no agrega dependencias (Django y JavaScript simple).

### Qué cambia para el vendedor

| Antes | Con la facturación rápida |
| --- | --- |
| El IVA acepta `-5`, `150` o texto (error 500) | Rango 0–30 % con 2 decimales, validado en el servidor y en el formulario |
| Descuento, envío y otros gastos aceptan negativos y texto; el descuento puede superar el subtotal | Se rechazan con un mensaje en español y no se crea la venta |
| El IVA se calcula antes del descuento y con el % vigente al editar | IVA sobre (subtotal − descuento), con el % guardado en cada venta |
| Un doble clic o un reenvío puede crear dos ventas | Una sola transacción con bloqueo de stock; el reenvío no duplica |
| Lista cortada en 200 productos, sin campo de cantidad | Buscador por nombre o código, una fila por producto con cantidad |
| Hay que navegar para empezar otra venta | Tras guardar, la misma pantalla ofrece imprimir, descargar, compartir o nueva venta |
| La factura impresa y el detalle no muestran el IVA | Ambos muestran la línea de IVA |

### Flujo con teclado

`escribir` el nombre o código → `Enter` agrega el primer resultado → `F9` guarda → `Enter` imprime el ticket → `N` empieza una venta nueva.

Tras guardar aparece "Venta N° … guardada — $total" con: Imprimir ticket, Descargar PDF, Compartir, Nueva venta y Ver detalle. "Imprimir al guardar" es una preferencia por dispositivo, apagada por defecto, sin migración. Si hay un error, la pantalla conserva lo cargado.

### Regla de IVA y redondeo

- Los precios de `Producto` **se guardan sin IVA**. El IVA se suma al facturar sobre (subtotal − descuento).
- Se usa el % de IVA **guardado en la venta al crearla**; las ventas existentes reciben el % actual de su empresa, sin recalcular totales.
- **Envío y otros gastos no llevan IVA**: pueden corresponder, por ejemplo, a una florería con entrega a domicilio.
- Redondeo `ROUND_HALF_UP` a 0,01; el cálculo vive en el servidor y el JavaScript solo lo muestra.

## 4. Reglas que no se negocian

- **El precio lo calcula el servidor**, nunca el navegador. Los precios publicados **no incluyen IVA**: el IVA se suma al final, con la regla de la sección 3. En un pedido de la tienda con subtotal de $5,00, el total mostrado es $5,00 más el IVA de la empresa sobre ese subtotal, más el envío si lo hay.
- **Una empresa nunca ve ni toca pedidos, cuentas o comprobantes de otra** (prueba de aislamiento en cada pantalla y acción).
- **Comprobantes seguros (RS-08):** solo imágenes reales verificadas con Pillow, máximo 5 MB y nombre aleatorio. Un `.html` renombrado a `.jpg` se rechaza.
- **Rutas públicas limitadas:** 10 pedidos y 10 subidas por minuto por IP, con el mismo límite del Sprint 0 (IP desde `tiendita_project.utils.obtener_ip_cliente`).
- **Datos de clientes existentes protegidos:** si alguien escribe una cédula que ya existe, el pedido se vincula sin modificar ni mostrar los datos guardados de esa persona.
- **Datos históricos intactos:** la facturación rápida no altera ventas ya guardadas ni quita funciones existentes (`detalle_venta`, `factura_pdf`, `editar_venta`, `lista_ventas`, compartir).

## 5. Tareas y versiones

### Facturación rápida (rama `feat/facturacion-rapida`)

| Versión | Tarea | Riesgo | Estado |
| --- | --- | --- | --- |
| 3.1.0 | IVA validado en servidor y en el formulario (0–30 %) | — | Hecho |
| 3.2.0 | Descuento, envío y otros gastos validados | — | Hecho |
| 3.3.0 | Regla de precios sin IVA, IVA sobre (subtotal − descuento) y % guardado por venta (migración) | Datos | Pendiente |
| 3.4.0 | Guardado atómico, bloqueo de stock y sin duplicados | Concurrencia | Pendiente |
| 3.5.0 | Edición sin alterar el descuento; línea de IVA en factura impresa y detalle | — | Pendiente |
| 3.6.0 | Pantalla rápida: buscador, filas con cantidad, panel posterior al guardado | — | Pendiente |
| 3.7.0 | Atajos de teclado, autocompletado de clientes y conservar lo cargado ante un error | — | Pendiente |

### Pedidos con transferencia (rama `feat/sprint-1-pedidos`)

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 3.8.0 | Campos nuevos en `Venta` y estados del pedido (migración) | Datos |
| 3.9.0 | Cuentas bancarias por empresa | — |
| 3.10.0 | Ruta pública para crear el pedido | Seguridad |
| 3.11.0 | Página del pedido y subida del comprobante | Seguridad |
| 3.12.0 | Panel del dueño: confirmar, rechazar, avanzar y anular (stock con bloqueo) | Datos y concurrencia |
| 3.13.0 | Cabeceras de seguridad RS-07 (`django-csp`) | Dependencia nueva |
| 3.14.0 | Aviso por WhatsApp con el enlace del pedido | — |
| 3.15.0 | README, guía y demo en staging | — |

Orden de los pedidos: 3.8 → 3.9 → 3.10 → 3.11 → 3.12. Las tareas 3.13 y 3.14 pueden ir en cualquier momento después de 3.10.

## 6. Cómo se prueba antes de producción

1. Cada tarea se fusiona a `main` con el CI en verde.
2. Staging (`https://danstore-staging.onrender.com`) se despliega solo desde `main`.
3. Alguien que no lo programó hace el recorrido en un celular de 400 px de ancho: venta rápida de mostrador (con teclado), pedido, comprobante, confirmación y anulación.
4. Recién entonces se hace **Manual Deploy** en producción.

**Criterio de aceptación de la guía:** dado un pedido con subtotal de $5,00, cuando el cliente sube su comprobante, el pedido queda en `pendiente_pago` y el dueño lo ve en su panel con la imagen. Con un toque pasa a `pagado`.

## 7. Decisiones pendientes del dueño

- **`django-csp` (tarea 3.13.0):** es una dependencia nueva y necesita tu aprobación; se agrega con versión fija.

Resuelta: el envío y los otros gastos **no llevan IVA**, y los precios de mostrador y de la tienda se guardan sin IVA.

## 8. Fuera de alcance

Factura electrónica autorizada por el SRI (Sprint 9, con proveedor externo), cobro en efectivo a domicilio, avisos automáticos por WhatsApp Cloud API (Sprint 2) y el asistente de IA (Sprints 3 y 4).
