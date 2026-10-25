# Facturación: validación del IVA, cálculos y flujo rápido

Sprint 1, prioridad del usuario antes de los pedidos por transferencia. Rama `feat/facturacion-rapida` desde `main` (a50cbc9).
Versiones 3.1.0–3.7.0 (minor por tarea, patch por commit). Pruebas: `ADMIN_URL=gestion-prueba/ DATABASE_URL=sqlite:///db_pruebas_s1.sqlite3 env/Scripts/python.exe manage.py test --noinput`.

## Specs

- **S1 (regla de precios):** el usuario: "no incluyen ya q ello va al final al facturar". Los precios de `Producto` no incluyen IVA; el IVA se suma al facturar.
- **S2 (validación del IVA):** "permite introducir valores negativos, lo cual es incorrecto." "Valida los datos tanto en el frontend como en el backend." "Impide valores negativos, datos inválidos y porcentajes fuera del rango permitido." "Evita que un usuario pueda eludir las validaciones enviando datos manipulados directamente al servidor." Decisión: rango 0–30 % con 2 decimales (Ecuador usa 0 %, 5 %, 8 % y 15 %; 30 deja margen a cambios de ley). Un dato inválido nunca da error 500: el formulario muestra el error y no guarda.
- **S3 (descuento, envío, otros gastos):** "El descuento, el envío y los otros gastos se calculen correctamente." Ninguno puede ser negativo ni texto, y el descuento no puede superar el subtotal. Un dato inválido no crea la venta ni da error 500.
- **S4 (cálculo de la factura):** "El IVA se obtenga de la configuración correspondiente." "No se duplique ni se aplique incorrectamente el IVA." "Se utilice una precisión monetaria adecuada para evitar errores de redondeo." "Los cálculos se validen en el backend y no dependan exclusivamente de JavaScript." "Se mantenga la compatibilidad con las facturas existentes." Decisiones: base imponible = subtotal − descuento (norma del SRI: el IVA se calcula sobre el valor con descuento); envío y otros gastos se suman sin IVA, como hoy (pendiente de confirmar, L3); redondeo ROUND_HALF_UP a 0,01; el % de IVA se guarda en cada venta al crearla, y las ventas existentes reciben el % actual de su empresa sin recalcular totales.
- **S5 (integridad):** "Guardar la factura de forma segura y evitar duplicados por envíos repetidos." Venta, detalles y stock en una sola transacción, con bloqueo de stock; un mismo envío repetido no crea una segunda venta.
- **S6 (edición e impresión):** la edición no debe alterar el descuento guardado, y la factura impresa y el detalle muestran la línea de IVA. "Verifica que las opciones de impresión sigan funcionando correctamente."
- **S7 (flujo rápido):** "Crear facturas de manera rápida e intuitiva. Buscar y agregar productos fácilmente. Modificar cantidades y eliminar productos sin recargar innecesariamente la página. Calcular automáticamente subtotales, descuentos, IVA y total. Evitar errores al ingresar productos o cantidades. [...] Elegir entre imprimir, descargar, compartir o continuar con una nueva venta. Iniciar una nueva factura sin tener que navegar repetidamente por diferentes pantallas. Mantener la información de la factura recién generada y evitar que se pierda accidentalmente." "No implementes tecnologías innecesarias."
- **S8 (automatizaciones):** "Búsqueda rápida de productos por nombre o código. Autocompletado de clientes existentes. [...] Validación de existencias antes de confirmar una venta. Atajos de teclado para agilizar la atención. Acciones rápidas después de guardar una factura. [...] Prevención de ventas duplicadas y control de errores."
- **S9 (reglas generales):** "Evita duplicar lógica de negocio." "Respeta la arquitectura, los permisos y la separación de datos entre negocios." "No elimines funcionalidades que actualmente funcionan." "No alteres datos históricos ni modifiques innecesariamente la estructura de la base de datos." "Si necesitas modificar modelos, crea las migraciones correspondientes." "Añade pruebas para el IVA negativo, los límites permitidos, los descuentos, los gastos adicionales, los cálculos de las facturas y el flujo de creación rápida." "Comprueba los casos de error y los posibles envíos duplicados."

## Tasks

| ID | Specs | Versión | Ruta | Estado | Commit |
| --- | --- | --- | --- | --- | --- |
| T1 | S2, S9 | 3.1.0 | worker, TDD | pendiente | |
| T2 | S3, S9 | 3.2.0 | worker, TDD | pendiente | |
| T3 | S1, S4, S9 | 3.3.0 | worker, TDD, Risk 1 (migración y regla tributaria) | pendiente | |
| T4 | S5, S9 | 3.4.0 | worker, TDD, Risk 4 (concurrencia) | pendiente | |
| T5 | S6, S9 | 3.5.0 | worker, TDD | pendiente | |
| T6 | S7, S8, S9 | 3.6.0 | worker, TDD | pendiente | |
| T7 | S8, S9 | 3.7.0 | worker | pendiente | |

## Log

- **L1 (pedido original, 2026-10-24):** "Actúa como un desarrollador sénior especializado en Django, Python, PostgreSQL, seguridad, automatización de procesos y diseño de sistemas de facturación para pequeñas y medianas empresas. [...] Prioridad principal: corregir las validaciones del IVA y optimizar el proceso de facturación para que crear, guardar y continuar con la siguiente venta sea rápido, sin sacrificar la precisión de los cálculos ni la integridad de los datos. Primero inspecciona el proyecto y presenta tus hallazgos. Después, implementa las mejoras de forma controlada, verificando cada cambio antes de continuar." (texto completo en la conversación; las specs citan lo pertinente)
- **L2 (análisis de solo lectura, 2026-10-24):** problemas probados en el código. Configuración: `ventas/views.py:544` hace `Decimal(POST)` sin validar; `ventas/models.py:160` sin validadores; `configuracion_facturas.html:131` sin min/max; `-5` y `150` se guardan; `abc`, vacío y `NaN` dan 500. Creación y edición: `views.py:281-283` y `~505` aceptan negativos y texto (500); un descuento mayor al subtotal da total negativo. `Venta.calcular_total` (`models.py:113-127`) calcula el IVA sobre el subtotal antes del descuento, redondea HALF_EVEN y lee el % en vivo (editar una venta vieja la recalcula). Edición: `crear_venta.html:1394` y `2255-2265` toman el descuento en $ como %. `factura_pdf.html:137-169` y `detalle_venta.html:350-376` no muestran el IVA. `sheets_sync.py:846-885` crea ventas sin IVA que se recalculan con IVA al editarlas. Sin `transaction.atomic`, sin protección contra doble envío, sin `select_for_update`. La pantalla corta en 200 productos, no busca en el servidor, no tiene campo cantidad y no ofrece "Nueva venta" tras guardar. Probable: `config` no llega al contexto de `crear_venta` y el JS usa siempre 15 %. La sesión 2 no respondió (mensajería caída); el análisis se hizo con dos exploradores.
- **L3 (pendiente del usuario):** ¿el envío y los otros gastos llevan IVA? Hoy se suman sin IVA y así se mantienen.
- **L4 (respuesta del usuario, 2026-10-24):** "no incluyen ya q ello va al final al facturar". Confirma S1 y contradice el supuesto de la tienda online en `odd/tasks/sprint-1-pedidos-transferencia.md` (S2/L6): allí también hay que sumar el IVA al final.
