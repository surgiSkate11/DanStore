# Sprint 8 — Alta autónoma y cobro de suscripción

Versión 10.x.x · Rama sugerida `feat/sprint-8-alta-autonoma` · Depende de: Sprints 2 y 6 (canal de WhatsApp y configuración guiada) · **El orden de los Sprints 7 a 12 lo deciden los clientes del piloto.**

## 1. Qué cambia en una línea

Un negocio **se registra, conecta su WhatsApp y paga su suscripción sin intervención** de DanStore, que hasta ahora hace el alta a mano junto al dueño.

## 2. Historias de usuario

**H1. Registro autónomo**
Como dueño de un negocio quiero registrarme y dejar mi tienda lista sin ayuda, para empezar el mismo día.
- *Dado* un visitante, *cuando* completa el registro, *entonces* se crea su empresa y entra al asistente de configuración (meta: 15 minutos).

**H2. Conectar WhatsApp**
Como dueño quiero conectar mi número de WhatsApp yo mismo.
- *Dado* una empresa nueva, *cuando* sigue el registro integrado de Meta, *entonces* se crea su `CanalWhatsApp` sin que DanStore lo haga a mano.

**H3. Pagar la suscripción**
Como dueño quiero pagar mi suscripción con cobro automático.
- *Dado* una suscripción vigente, *cuando* llega la fecha de cobro y el pago se aprueba, *entonces* la cuenta sigue activa.
- *Dado* un pago fallido, *cuando* vence el plazo, *entonces* la cuenta queda suspendida (el middleware ya bloquea cuentas suspendidas).

## 3. Mejoras

| Antes | Con el Sprint 8 |
| --- | --- |
| DanStore da de alta cada negocio a mano | El negocio se registra solo |
| El número de WhatsApp se conecta junto al dueño | Registro integrado de Meta, con DanStore como Tech Provider |
| La suscripción se gestiona con las opciones actuales de planes | Cobro automático de la suscripción |

## 4. Diseño técnico

| Pieza | Detalle |
| --- | --- |
| Registro público | Nuevo flujo sobre `empresas` y `usuarios`; reutiliza planes, suscripciones y el asistente de configuración del Sprint 2 |
| Registro integrado de Meta | Requiere que DanStore sea Tech Provider de Meta; crea el `CanalWhatsApp` con token cifrado |
| Cobro automático | Sobre los modelos de suscripción existentes; el procesador de pagos está por decidir |
| Webhooks de pago | Firma verificada (RS-10) y respuesta rápida; reintentos idempotentes |

Stripe no sirve a comercios de Ecuador según la guía (por verificar en su lista de países); por eso el procesador no está decidido.

## 5. Reglas que no se negocian

- **RS-06:** límite de intentos por IP en registro y login (IP desde `tiendita_project.utils.obtener_ip_cliente`).
- **RS-10:** firma verificada en cada webhook de pagos y de WhatsApp.
- **RS-03:** claves del procesador de pagos solo en variables de entorno.
- **Aislamiento (RS-01):** una empresa nueva nace vacía y nunca ve datos de otra.
- **Dinero:** montos y prorrateos con `Decimal` y redondeo `ROUND_HALF_UP` a 0,01.
- **LOPDP:** datos de registro y de pago, tratados con el mínimo necesario; términos de servicio y política de privacidad publicados.

## 6. Tareas y versiones

Desglose propuesto; se ajusta al planificar el sprint.

| Versión | Tarea | Riesgo |
| --- | --- | --- |
| 10.1.0 | Registro público con límite por IP | Seguridad |
| 10.2.0 | Creación automática de la empresa y entrada al asistente de configuración | Datos |
| 10.3.0 | Registro integrado de Meta y creación de `CanalWhatsApp` | Seguridad |
| 10.4.0 | Cobro automático y webhook de pagos con firma | Seguridad |
| 10.5.0 | Suspensión y reactivación según el pago | Datos |

## 7. Cómo se prueba

1. Pruebas con adaptadores falsos del procesador de pagos y de Meta: firma inválida (403), evento repetido, pago fallido.
2. Pruebas de aislamiento entre dos empresas recién creadas.
3. Registro completo desde un celular de 400 px en staging (`https://danstore-staging.onrender.com`), por alguien que no lo programó.
4. CI en verde.

## 8. Decisiones pendientes del dueño

- **Procesador de pagos para Ecuador** y si cobra suscripciones recurrentes.
- **Tech Provider de Meta:** iniciar el trámite y plazos.
- **Periodo de prueba, ciclos de cobro y plazo antes de suspender.**
- **Prioridad del sprint:** la decide el piloto.

## 9. Fuera de alcance

Facturación electrónica de la suscripción (Sprint 9), marca blanca y app móvil nativa.
