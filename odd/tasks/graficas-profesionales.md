# Gráficas profesionales (Dashboard, Reportes, SaaS)

Rediseño de las pantallas con gráficas: sin duplicados, con estadísticas útiles para el dueño.
Rama `feat/graficas-profesionales`, en el worktree `.worktrees/graficas`.

## Specs
- S1: "hay q aplicar mejoras en el diseño de los modulo que tienen gráficas, quiero gráficas profesionales y no esas q hay". Las gráficas comparten un tema visual común: paleta propia, moneda formateada, textos en español y estado vacío.
- S2: "hay gráficas repetidas, cuano en realidad podríamos aprovecharlo mucho mejor". Ninguna gráfica se repite entre el Dashboard y Reportes.
- S3: Reparto elegido: "Dashboard 'hoy' / Reportes análisis". El Dashboard tiene KPIs con % contra el período anterior, el mes actual contra el anterior, pedidos por estado y alertas de stock. Reportes tiene el análisis profundo con filtro de fechas.
- S4: Estadísticas nuevas en Reportes: "Ingresos + utilidad + margen", "Mapa de calor día/hora", "Pareto 80/20 + clientes recurrentes".
- S5: Alcance: "Las 3, incluido panel SaaS". El MRR inventado se reemplaza por el historial real.
- S6: "¿Las ventas 'pendiente de pago' deben contar como ingreso?" → "No, excluirlas". Ingreso = solo lo cobrado. Lo pendiente se muestra aparte como "por cobrar".
- S7: Los datos de una empresa nunca deben verse en otra (regla del AGENTS.md).

## Tasks
- T1 [S6,S7,S4,S5] Módulo `dashboard/estadisticas.py` con los cálculos, más sus tests. Inline. Commit: 388469f. Hecho.
- T2 [S1,S2,S3,S6] Dashboard del negocio: vista, plantilla y tema JS común. Inline. Commit: 872d156. Hecho.
- T3 [S1,S2,S4,S6] Reportes: vista y plantilla. Inline. Commit: dfd9642. Hecho.
- T4 [S1,S5] Panel SaaS: MRR real y diseño. Inline. Commit: 8a2b750. Hecho.

## Log
- L1: "hay q aplicar mejoras en el diseño de los modulo que tienen gráficas, quiero gráficas profesionales y no esas q hay, y hay gráficas repetidas, cuano en realidad podríamos aprovecharlo mucho mejor y mostrar estadisticas supervalioss para cualquier dueño de un negocio"
- L2: Respuestas del usuario: Enfoque = Dashboard 'hoy' / Reportes análisis. Estadísticas = Ingresos+utilidad+margen, Mapa de calor día/hora, Pareto 80/20 + clientes recurrentes. Alcance = Las 3, incluido panel SaaS. Pendiente de pago = No, excluirlas.
- L3: Hallazgos: el MRR del panel SaaS está hardcodeado; ingresos 30 días y top productos se repiten entre Dashboard y Reportes; ApexCharts se carga sin versión fijada; DetalleVenta = 1 unidad por fila; no hay tests de estas vistas.
- L4: Bug previo, fuera de alcance: `base.html:1068` usa `{% url 'completar_onboarding' %}`, pero el commit f0a8769 borró esa URL. Un dueño con el onboarding pendiente que entra a `dashboard_tenant` recibe NoReverseMatch (500). Los tests marcan el onboarding como completado.
- L5: Verificación: `manage.py test dashboard` da 62 tests OK y `manage.py check` sale limpio. `node --check` pasa en los scripts. No hubo revisión visual en el navegador. T4 lo hizo un worker; el parent corrigió que el historial de MRR filtre empresas activas.
- L6: Hubo dos intentos de `gentle-ai-verify` (Risk: item 6) y los dos fallaron por cuota, sin veredicto. No hay verificación independiente. Como evidencia propia, el parent renderizó las 3 páginas en una BD de test, con 105 ventas sembradas y también vacías. Ejecutó analytics.js y los scripts inline en Node, con ApexCharts y el DOM simulados. Las 14 gráficas con datos dieron OK: largos de serie y categorías, sin NaN y formatters sin errores. Las 12 vacías mostraron su estado vacío. No hubo revisión visual en un navegador real.
