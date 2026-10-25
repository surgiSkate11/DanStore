# Sprint 7 — Costos de IA

Versión 9.x.x · Rama sugerida `feat/sprint-7-costos-ia` · Depende de: Sprints 3 a 6 (asistente en uso) y de los datos del piloto · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto**: no se construye lo que se cree que quieren, sino lo que pagan.

## 1. Qué cambia en una línea

El sistema **mide cuánto gasta en IA cada negocio**, elige el modelo por resultados medidos y aplica límites por plan, para que ningún negocio consuma más de lo que paga.

## 2. Historias de usuario

**H1. Costo por empresa**
Como administrador de DanStore quiero ver cuánto gasta cada negocio en IA, para fijar el precio con costes reales.
- *Dado* mensajes procesados por el asistente, *cuando* abro el panel de administración propio, *entonces* veo el costo de IA por empresa y por periodo.

**H2. Límites por plan**
Como administrador quiero límites de uso de IA por plan, para que un negocio no gaste la cuota de todos.
- *Dado* una empresa que alcanzó su límite, *cuando* un cliente escribe, *entonces* se aplica el comportamiento acordado (por definir) y no se procesa más IA.

**H3. Modelo adecuado**
Como administrador quiero que las preguntas simples usen un modelo barato y los pedidos y comprobantes uno confiable.
- *Dado* una pregunta simple, *cuando* se procesa, *entonces* se usa el modelo barato; *dado* un pedido o un comprobante, *entonces* el confiable.

## 3. Mejoras para el dueño de DanStore

| Antes | Con el Sprint 7 |
| --- | --- |
| No se sabe cuánto cuesta cada negocio | Costo de IA por empresa |
| Un modelo para todo | Modelo elegido por prueba y, si conviene, dos modelos |
| Un negocio puede gastar sin límite | Límites por plan |
| El precio de la suscripción se estima | Se fija con costes medidos del piloto: WhatsApp, IA y servidor por cliente |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Elección de modelo | Correr las 30 conversaciones con cada candidato y elegir el más barato que pase con 0 errores; el cambio de modelo no toca el resto del código (`asistente/adaptadores/ia.py`) |
| Registro de uso | Por mensaje: empresa, modelo y consumo. Campos por definir |
| Límites por plan | Reutiliza los planes existentes (`requiere_modulo` y planes con módulos). Cantidades por definir |
| Selección automática | Modelo barato para preguntas simples, confiable para pedidos y comprobantes |
| Panel | Vista de costo por empresa en el panel propio (`/saas/`), protegido con `es_superadmin` |

Opciones de proveedor que la hoja de ruta compara: API de DeepSeek (barata, pago por uso, servidores en China), modelo abierto en servidor propio (GPU cara) y versiones gratuitas (no sirven para clientes que pagan).

## 5. Reglas que no se negocian

- **Se elige por resultados medidos:** un modelo que falla al crear un pedido o leer un comprobante cuesta más que los tokens que ahorra.
- **LOPDP:** todo proveedor fuera de Ecuador implica transferencia internacional. Exige aviso de privacidad, contratos con cláusulas de protección de datos, enviar a la IA solo los datos mínimos, borrado a pedido y revisar la norma de 2026 de la Superintendencia.
- **Aislamiento (RS-01):** el costo y el uso de una empresa no son visibles para otra.
- **Dinero:** costos con `Decimal` y redondeo `ROUND_HALF_UP`.
- **Dependencias:** cualquier librería nueva requiere aprobación y versión fija.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 9.1.0 | Registro de uso de IA por empresa (migración) | Datos |
| 9.2.0 | Comparación de modelos con las 30 conversaciones | — |
| 9.3.0 | Panel de costo por empresa | — |
| 9.4.0 | Límites por plan y comportamiento al alcanzarlos | Datos |
| 9.5.0 | Selección automática del modelo | — |

## 7. Cómo se prueba

1. Pruebas con el adaptador falso: el uso se registra por empresa y respeta el límite.
2. Prueba de aislamiento con dos empresas.
3. Las 30 conversaciones por cada modelo candidato, con 0 errores como condición.
4. CI en verde; staging (`https://danstore-staging.onrender.com`) probado por alguien que no lo programó, en celular de 400 px.

## 8. Decisiones pendientes del dueño

- **Proveedor y modelos candidatos.**
- **Límites por plan:** cantidades y qué pasa al alcanzarlos (pausar, pasar a una persona, cobrar extra).
- **Precio de los planes:** según los costes medidos en el piloto.
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Cobro automático de la suscripción (Sprint 8) y entrenamiento de modelos propios.
