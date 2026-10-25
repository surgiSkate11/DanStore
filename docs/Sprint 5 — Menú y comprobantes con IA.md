# Sprint 5 — Menú y comprobantes con IA

Versión 7.x.x · Rama sugerida `feat/sprint-5-menu-comprobantes-ia` · Depende de: Sprint 4 (comprobantes por chat) y del adaptador de IA del Sprint 3 · Calendario original: semanas 10–11

## 1. Qué cambia en una línea

La IA **lee imágenes**: el dueño le saca una foto a su menú y los productos se cargan solos, y el sistema lee el comprobante y le dice al dueño si el monto coincide con el pedido. La IA solo pre-valida; el dueño sigue confirmando con su banco.

## 2. Historias de usuario

**H1. Cargar el menú desde una foto**
Como dueño quiero sacarle una foto a mi menú y que mis productos se carguen solos, para no escribirlos uno por uno.
- *Dado* una foto legible de un menú, *cuando* se ejecuta `importar_menu_desde_foto`, *entonces* el sistema propone una lista de productos y precios sin publicar nada.
- *Dado* una propuesta, *cuando* el dueño la revisa y confirma, *entonces* los productos se crean en su empresa; si no confirma, no se crea ninguno.

**H2. Comprobante pre-validado**
Como dueño quiero que el sistema lea el comprobante y me diga si el monto coincide con el pedido.
- *Dado* un comprobante recibido, *cuando* la IA lo lee, *entonces* se guardan monto, fecha, banco y número de transacción, y el dueño ve si el monto coincide.
- *Dado* un comprobante con monto distinto al pedido, *cuando* se compara, *entonces* se marca la diferencia y el pedido sigue en `pendiente_pago`.

## 3. Mejoras para el dueño

| Antes | Con el Sprint 5 |
| --- | --- |
| Carga los productos uno por uno | Foto del menú y revisión antes de publicar |
| Abre el comprobante y compara el monto a ojo | Ve monto, fecha, banco y transacción leídos, con aviso si no coincide |
| Confirma el pago sin ayuda | Confirma con la pre-validación como apoyo, no como sustituto del banco |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| `importar_menu_desde_foto` | Herramienta del rol dueño. Devuelve una propuesta de productos; la creación real la ejecuta el código tras la revisión del dueño |
| Lectura del comprobante | Extrae monto, fecha, banco y número de transacción; los guarda junto al `ComprobantePago` del Sprint 1 (campos exactos por definir) |
| `adaptadores/ia.py` | Uso de un modelo más capaz para leer imágenes; el modelo barato queda para preguntas simples |
| Reutilización | `Producto` y sus formularios existentes para crear los productos; validaciones RS-08 para las imágenes |

## 5. Reglas que no se negocian

- **Límite de la IA:** la IA lee la imagen pero no puede saber si el dinero llegó al banco; un comprobante falso se ve igual que uno real. Nunca pasa un pedido a `pagado` por sí sola.
- **La IA decide, el código ejecuta:** la propuesta de productos pasa por validación del servidor antes de guardarse; la empresa la pone el sistema.
- **Aislamiento (RS-01):** los productos importados y las lecturas pertenecen solo a la empresa del dueño.
- **RS-11:** texto escondido dentro de una imagen no puede cambiar el comportamiento del asistente.
- **RS-08:** imágenes verificadas con Pillow, máximo 5 MB, nombre aleatorio.
- **Dinero:** los precios leídos se guardan sin IVA, como `Decimal`, y el dueño los revisa antes de publicar.
- **LOPDP:** los comprobantes pueden contener datos personales; se envía a la IA solo la imagen necesaria y el proveedor está fuera de Ecuador.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 7.1.0 | Modelo de IA para imágenes en el adaptador y conversaciones guionadas con imágenes | — |
| 7.2.0 | `importar_menu_desde_foto`: propuesta y pantalla de revisión | Datos |
| 7.3.0 | Publicación de los productos revisados | Datos |
| 7.4.0 | Lectura del comprobante (monto, fecha, banco, transacción) (migración) | Datos |
| 7.5.0 | Comparación con el pedido y aviso de diferencia al dueño | — |
| 7.6.0 | Casos de ataque con imágenes (RS-11) | Seguridad |

## 7. Cómo se prueba

1. Adaptador de IA falso con respuestas fijas para menús y comprobantes (sin gasto).
2. Prueba de aislamiento con dos empresas; prueba de que una propuesta no confirmada no crea productos.
3. Imágenes reales de menús y comprobantes en las conversaciones guionadas; el set de 30 conversaciones sigue en 0 precios inventados.
4. CI en verde; en staging (`https://danstore-staging.onrender.com`) alguien que no lo programó carga un menú real desde un celular de 400 px.

## 8. Decisiones pendientes del dueño

- **Dónde sube el dueño la foto:** por WhatsApp (herramienta del rol dueño) o también desde una pantalla web.
- **Rol dueño antes del Sprint 6:** `importar_menu_desde_foto` es herramienta del dueño, pero la identificación del dueño por teléfono y su confirmación por chat se describen para el Sprint 6; definir qué parte se adelanta aquí.
- **Modelo para imágenes:** se elige midiendo, según la hoja de ruta; la decisión formal es del Sprint 7.
- **Campos nuevos del comprobante:** nombres y tipos.
- **Comprobante con monto distinto:** si solo se avisa o si el pedido se bloquea.

## 9. Fuera de alcance

Confirmar el pago automáticamente, verificar con el banco, cambiar precios o stock por chat (Sprint 6) y costos de IA por empresa (Sprint 7).
