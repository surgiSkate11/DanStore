# Sprint 3 — Asistente: consultas por WhatsApp

Versión 5.x.x · Rama sugerida `feat/sprint-3-asistente-consultas` · Depende de: Sprint 2 (app `asistente`, `CanalWhatsApp`, adaptador de envío) · Plan técnico: `odd/tasks/asistente-whatsapp.md` (por crear, compartido con el Sprint 4) · Calendario original: semanas 6–7

## 1. Qué cambia en una línea

El negocio empieza a **recibir** mensajes: un asistente de IA responde al cliente por WhatsApp, a cualquier hora, con precios, productos y horarios reales del catálogo, y pasa la conversación a una persona cuando no sabe responder. Todavía no toma pedidos (Sprint 4).

## 2. Historias de usuario

**H1. Consultar productos y precios**
Como cliente quiero preguntar por WhatsApp si hay un producto y cuánto cuesta, y recibir la respuesta al instante a cualquier hora.
- *Dado* un producto existente con stock, *cuando* el cliente pregunta por él, *entonces* el asistente responde con el precio y la disponibilidad que devuelve `buscar_productos`.
- *Dado* un producto que no existe, *cuando* el cliente pregunta, *entonces* el asistente dice que no lo encuentra y no inventa precio.

**H2. Consultar el horario**
Como cliente quiero saber el horario del negocio, para saber cuándo puedo pedir o retirar.
- *Dado* un horario configurado, *cuando* el cliente pregunta, *entonces* la respuesta sale de `ver_horario`.

**H3. Pasar a una persona**
Como dueño quiero que el asistente me pase la conversación cuando no sepa responder, para atender yo los casos que lo requieren.
- *Dado* una pregunta que el asistente no puede resolver, *cuando* llama a `pasar_a_humano`, *entonces* la conversación queda en estado `humano`, el bot deja de contestar y el dueño recibe el aviso.

## 3. Mejoras

| Antes | Con el Sprint 3 |
| --- | --- |
| El cliente espera a que el dueño lea el chat | Respuesta en menos de 1 minuto, las 24 horas |
| El dueño responde "¿cuánto cuesta?" a mano | El asistente consulta el catálogo real |
| Nadie mide si la IA inventa | 30 conversaciones guionadas corren en cada cambio del prompt |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| `asistente/webhooks.py` | GET de verificación y POST de mensajes de Meta; valida `X-Hub-Signature-256` y responde 200 enseguida |
| Celery + Redis | Procesan cada mensaje fuera del webhook (`asistente/tareas.py`). Dependencias nuevas — **requieren aprobación**, versión fija; Redis como servicio en Render |
| `Conversacion` | `empresa`, teléfono del cliente, `estado` (bot o humano) |
| `Mensaje` | `conversacion`, `rol`, `texto`, `wa_message_id` único para ignorar repetidos |
| `dominio/orquestador.py` | Decide el rol por el número de teléfono, arma el contexto y llama a la IA |
| `dominio/herramientas.py` y `permisos.py` | Herramientas del rol cliente en este sprint: `buscar_productos`, `ver_horario`, `pasar_a_humano` |
| `adaptadores/ia.py` | Cliente de la API de IA con uso de herramientas; permite cambiar de modelo sin tocar el resto |
| Set de 30 conversaciones | Precios, productos que no existen, horarios y pedidos incompletos; se corre en cada cambio del prompt |

La empresa la fija el sistema a partir del número de WhatsApp del negocio que recibió el mensaje, nunca la IA. Las pruebas reemplazan los adaptadores por falsos que no gastan dinero.

## 5. Reglas que no se negocian

- **La IA decide, el código ejecuta:** nunca toca la base; solo llama funciones probadas.
- **No inventa datos:** precios, stock y horarios solo salen de las herramientas.
- **RS-10:** un POST al webhook sin firma válida recibe 403.
- **Aislamiento (RS-01):** `buscar_productos` filtra por la empresa del canal; hay una prueba con dos empresas.
- **Idempotencia:** un `wa_message_id` repetido no se procesa dos veces.
- **Dinero:** los precios se informan sin IVA, tal como se guardan; el IVA se suma al facturar (regla del Sprint 1).
- **Datos personales (LOPDP):** la IA recibe solo los datos mínimos; el proveedor de IA está fuera de Ecuador (transferencia internacional).

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 5.1.0 | `Conversacion` y `Mensaje` con `wa_message_id` único (migración) | Datos |
| 5.2.0 | Webhook con verificación de firma (RS-10) | Seguridad |
| 5.3.0 | Celery y Redis; procesar el mensaje fuera del webhook | Concurrencia |
| 5.4.0 | Adaptador de IA y orquestador con roles y permisos | Seguridad |
| 5.5.0 | Herramientas `buscar_productos` y `ver_horario` | — |
| 5.6.0 | `pasar_a_humano` y aviso al dueño | — |
| 5.7.0 | Set de 30 conversaciones guionadas como línea base | — |

## 7. Cómo se prueba

1. Pruebas con adaptadores falsos de IA y WhatsApp; prueba de firma inválida (403) y de mensaje repetido.
2. Las 30 conversaciones guionadas: criterio de la guía, 0 precios inventados.
3. CI en verde; staging (`https://danstore-staging.onrender.com`) con un número de prueba, probado por alguien que no lo programó, en celular de 400 px.

## 8. Decisiones pendientes del dueño

- **Celery y Redis:** aprobar dependencias y versiones fijas.
- **Proveedor y modelo inicial de IA:** la guía propone la API de Claude; la hoja de ruta exige elegir midiendo con las 30 conversaciones (decisión formal en el Sprint 7).
- **Aviso de privacidad:** la guía lo pide en el primer mensaje del cliente, pero este plan lo ubica en el Sprint 4. Mientras tanto, este sprint solo debería usarse con números de prueba. Decidir si el aviso se adelanta aquí.
- **RS-11 y RS-12:** la guía los fecha en el Sprint 3; aquí se ubican en el Sprint 4. Confirmar.
- **Conversaciones de pedido del set:** sin `crear_pedido`, definir qué respuesta se espera (por ejemplo, `pasar_a_humano`).
- **Mensaje del dueño:** definir qué responde el sistema si el dueño escribe antes del Sprint 6; el campo de teléfono en `UserProfile` debe verificarse.

## 9. Fuera de alcance

Crear pedidos y recibir comprobantes (Sprint 4), leer imágenes (Sprint 5), herramientas del dueño (Sprint 6) y control de costos de IA (Sprint 7).
