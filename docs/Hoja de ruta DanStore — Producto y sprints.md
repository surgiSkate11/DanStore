# Hoja de ruta DanStore — Producto y sprints

Oct 25, 2026 · @Edwinrpb · Complementa `Guía de desarrollo DanStore — Fase 0.md` (secciones 1, 6 y 8).

## 1. Qué buscamos lograr

Que el dueño de un negocio pequeño solo se ocupe de preparar y entregar. Atender, vender, cobrar y llevar las cuentas lo hace el sistema.

**Metas medibles para el piloto:**

- Todos los mensajes respondidos en menos de 1 minuto, las 24 horas.
- Un pedido completo (consulta → pedido → pago → aviso al dueño) sin que el dueño escriba nada.
- Una tienda nueva configurada en 15 minutos.
- El dueño sabe cuánto vendió sin contar nada.
- En el mostrador, una venta típica se registra e imprime en menos de 30 segundos (escribir → Enter → F9 → Enter → N).

## 2. Cómo usa la IA

La IA cumple 4 trabajos, y en todos sigue una regla: **la IA decide, el código ejecuta.** La IA nunca toca la base de datos; llama funciones programadas y probadas, y la empresa siempre la pone el sistema, nunca la IA.

| Trabajo | Para quién | Ejemplo |
| --- | --- | --- |
| Vender | Cliente | "¿Tienen pan de yuca?" → consulta stock real → crea el pedido |
| Administrar | Dueño | "Subí el pan a 30 centavos" → pide confirmación → cambia el precio |
| Leer imágenes | Ambos | Foto del menú → productos cargados. Foto del comprobante → monto pre-validado (el dueño sigue confirmando con su banco) |
| Informar | Dueño | "Hoy vendiste $186; mañana hacé más empanadas, se agotaron a las 11" |

## 3. Qué lo diferencia

| Alternativa | Qué hace | Qué le falta frente a DanStore |
| --- | --- | --- |
| Bots de WhatsApp (Wati, Kommo, Leadsales) | Chatbot y bandeja de mensajes | El dueño configura todo solo; no tienen inventario, tienda ni cobros reales |
| Tiendas online (Shopify y similares) | Catálogo y carrito | No conversan por WhatsApp, que es donde compra la gente aquí |
| Sistemas contables (Contífico y similares) | Facturación e inventario | No venden ni atienden |

**Las 4 diferencias reales:**

1. **Todo en uno:** tienda, WhatsApp, cobro por transferencia, inventario, punto de venta y reportes en un solo sistema y una sola cuota.
2. **Hecho para Ecuador:** transferencia con comprobante, efectivo al retirar, IVA configurable por negocio (los precios se cargan sin IVA y el IVA se suma al facturar) y LOPDP.
3. **La IA trabaja con datos reales:** no inventa precios, porque los consulta.
4. **Cero configuración:** foto del menú y listo.

## 4. Elección del modelo de IA

**Nadie elige por fe; se elige por resultados medidos.** `asistente/adaptadores/ia.py` permite cambiar de modelo sin tocar el resto del código.

| Opción | Costo real | Problema |
| --- | --- | --- |
| API de DeepSeek | Barata, pero de pago por uso. Precio no confirmado en la página oficial | Servidores en China |
| Modelo abierto en servidor propio | El modelo es gratis; el servidor con GPU no, y es caro | Para un emprendimiento que empieza, sale más caro que una API |
| Versiones gratuitas (por ejemplo en OpenRouter) | $0 | Límites de uso y caídas: no sirven para clientes que pagan |

Lo que importa más que el precio: si el modelo se equivoca al crear un pedido o al leer un comprobante, se pierde un cliente, y eso cuesta mucho más que los tokens.

**Método:**

1. Correr las 30 conversaciones guionadas con cada modelo candidato.
2. Elegir el más barato que pase con 0 errores.
3. Mejor todavía, usar dos modelos: uno barato para preguntas simples ("¿a qué hora abren?") y uno confiable para crear pedidos y leer comprobantes.

**Datos personales (LOPDP) con cualquier proveedor:** todo servidor fuera de Ecuador implica transferencia internacional de datos. Aplica a DeepSeek (China) y también a Anthropic u OpenAI (EE. UU.), y a la infraestructura actual (Render, Neon). No descarta proveedores, pero exige siempre:

- Aviso de privacidad en el primer mensaje del cliente.
- Contratos con cláusulas de protección de datos con cada proveedor.
- Mandar a la IA solo los datos mínimos (el pedido, no la cédula ni datos que no necesita).
- Borrado de conversaciones a pedido del cliente.
- Revisar la norma de 2026 de la Superintendencia sobre transferencias internacionales antes del piloto.

## 5. Qué le falta al sistema

Los Sprints 1 a 6 dejan un producto vendible. Para que sea completo y escale, faltan 6 piezas:

1. **Control de costos de IA:** cuánto gasta cada negocio, límites por plan y elección automática del modelo.
2. **Alta sin intervención:** que un negocio se registre, conecte su WhatsApp y pague la suscripción solo.
3. **Facturación electrónica SRI:** la van a pedir. Se integra un proveedor, no se construye desde cero.
4. **Domicilios:** zonas, costo de envío, estado "en camino" y aviso al cliente.
5. **Inteligencia del negocio:** cuánto producir mañana, clientes frecuentes y promociones automáticas.
6. **Listo para escalar:** rendimiento, monitoreo, prueba de seguridad e instalable en el celular (PWA).

Demanda detectada: caja sin internet para tiendas de barrio. Candidato a módulo futuro.

## 6. Sprints: 13 en total, unos 6 meses

| Fase | Sprints | Semanas | Resultado |
| --- | --- | --- | --- |
| Cimientos | 0 ✅ | 1 | Seguro y con pruebas (terminado) |
| MVP vendible | 1 a 6 | 12–14 | Tienda + punto de venta + pedidos + IA cliente y dueño → piloto con 3 a 5 negocios |
| Producto completo | 7 a 12 | 12 | Las 6 piezas que faltan, una por sprint |

| Sprint | Objetivo |
| --- | --- |
| 1 | Facturación rápida en mostrador (IVA validado, cálculos correctos, sin duplicados, imprimir y compartir) y pedidos con pago por transferencia. La facturación rápida se agregó al plan original y mueve el piloto 1 a 2 semanas |
| 2 | Avisos al dueño por WhatsApp y panel del día |
| 3 y 4 | El asistente que atiende al cliente |
| 5 | Leer el menú y los comprobantes con IA |
| 6 | El asistente del dueño |
| 7 | Costos de IA: elección de modelo, límites por plan, costo por empresa |
| 8 | Alta autónoma y cobro automático de la suscripción |
| 9 | Facturación electrónica SRI |
| 10 | Domicilios |
| 11 | Inteligencia del negocio |
| 12 | Escalar: rendimiento, monitoreo, PWA |

**Regla:** el orden de los sprints 7 a 12 lo deciden los clientes del piloto. Si tres panaderías piden factura electrónica, el Sprint 9 pasa a ser el 7. No se construye lo que se cree que quieren; se construye lo que pagan.
