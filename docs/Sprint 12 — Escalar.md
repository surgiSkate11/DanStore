# Sprint 12 — Escalar

Versión 14.x.x · Rama sugerida `feat/sprint-12-escalar` · Depende de: Sprints 1 a 6 en uso con el piloto · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto.**

## 1. Qué cambia en una línea

El sistema queda **listo para crecer**: más rápido, vigilado, probado contra ataques e instalable en el celular como aplicación web (PWA).

## 2. Historias de usuario

**H1. Rendimiento**
Como dueño quiero que el sistema responda rápido aunque haya muchos negocios y pedidos, para no perder ventas en horas pico.
- *Dado* un volumen de datos y usuarios acordado, *cuando* se mide, *entonces* las pantallas y el asistente responden dentro del tiempo objetivo (por definir).

**H2. Monitoreo**
Como administrador de DanStore quiero enterarme de un fallo antes que el cliente.
- *Dado* un error o una caída, *cuando* ocurre, *entonces* llega un aviso con el detalle suficiente para corregirlo.

**H3. Seguridad probada**
Como administrador quiero una prueba de seguridad sobre el sistema, para confirmar que ninguna empresa ve datos de otra.
- *Dado* el sistema en staging, *cuando* se ejecuta la prueba, *entonces* se entrega una lista de hallazgos y cada uno se corrige o se acepta por escrito.

**H4. Instalable en el celular**
Como dueño quiero instalar DanStore en mi celular como una aplicación, para abrirlo con un toque.
- *Dado* un celular de gama media, *cuando* el dueño la instala, *entonces* abre a pantalla completa y funciona con datos móviles.

## 3. Mejoras

| Antes | Con el Sprint 12 |
| --- | --- |
| Se mide poco; los problemas se descubren por quejas | Rendimiento medido y errores avisados |
| Seguridad revisada por el equipo | Prueba de seguridad específica |
| Se abre desde el navegador | PWA instalable |
| Servicios dimensionados para el piloto | Dimensionados para más negocios |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Rendimiento | Medir consultas lentas, índices y caché sobre la base actual (Neon PostgreSQL) y el servicio en Render; cambios por definir tras medir |
| Monitoreo | Amplía el registro de errores del Sprint 2 (Sentry, RS-14) con métricas y alertas; cualquier herramienta nueva requiere aprobación |
| Prueba de seguridad | Sobre staging; quién la hace está por decidir |
| PWA | Manifiesto e ícono; funcionamiento sin conexión no incluido |
| Infraestructura | Plan de Render y de Neon según lo medido; Cloudflare delante (RS-15) |

## 5. Reglas que no se negocian

- **Aislamiento (RS-01):** ninguna optimización (caché, consultas, índices) puede mezclar datos de empresas; las claves de caché incluyen la empresa y hay prueba con dos empresas.
- **Sin pérdida de datos:** cambios de índices o migraciones se ensayan en staging; copia diaria y restauración probada (RS-16).
- **RS-15:** el dominio responde a través de Cloudflare.
- **Dependencias:** nuevas librerías con aprobación y versión fija; `pip-audit` sin hallazgos (RS-13).
- **Dinero:** ninguna optimización cambia redondeos ni totales.
- **LOPDP:** los registros y métricas no guardan datos personales innecesarios.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 14.1.0 | Línea base de rendimiento (medición) | — |
| 14.2.0 | Optimización de las consultas más lentas | Datos |
| 14.3.0 | Monitoreo y alertas | Entrega |
| 14.4.0 | Prueba de seguridad y corrección de hallazgos | Seguridad |
| 14.5.0 | PWA (manifiesto e instalación) | — |
| 14.6.0 | Ajuste de infraestructura | Entrega |

## 7. Cómo se prueba

1. Pruebas de rendimiento antes y después de cada cambio, con los mismos datos.
2. Pruebas de aislamiento con dos empresas repetidas tras cada optimización.
3. Instalación de la PWA en un celular real de 400 px; verificación en staging (`https://danstore-staging.onrender.com`) por alguien que no lo programó.
4. CI en verde.

## 8. Decisiones pendientes del dueño

- **Tiempo objetivo** de respuesta y volumen a soportar.
- **Quién hace la prueba de seguridad** y su costo.
- **Herramienta de monitoreo** adicional, si hace falta.
- **Plan de infraestructura** (Render y Neon).
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Caja sin internet para tiendas de barrio (demanda detectada; candidato a módulo futuro, solo si un cliente lo paga), app móvil nativa, marca blanca y módulo de citas.
