/*
 * Tema común de gráficas (ApexCharts) para Dashboard, Reportes y panel SaaS.
 * Expone window.DS con la paleta, formateadores y un helper de render con estado vacío.
 */
(function () {
    'use strict';

    var PALETA = {
        brand: '#4f46e5',
        brandSoft: '#c7d2fe',
        profit: '#10b981',
        warning: '#f59e0b',
        danger: '#f43f5e',
        sky: '#0ea5e9',
        violet: '#8b5cf6',
        slate: '#94a3b8',
        grid: '#eef2f7',
        text: '#64748b'
    };
    var SERIE = [PALETA.brand, PALETA.profit, PALETA.warning, PALETA.sky, PALETA.violet, PALETA.danger, '#14b8a6', '#eab308', '#6366f1', '#84cc16'];

    var fmtMoneda = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });
    var fmtCompacto = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });
    var fmtEntero = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 });

    function money(v) { return v === null || v === undefined ? '—' : fmtMoneda.format(v); }
    function moneyShort(v) {
        if (v === null || v === undefined) return '';
        return Math.abs(v) >= 1000 ? '$' + fmtCompacto.format(v) : '$' + fmtEntero.format(v);
    }
    function pct(v) { return v === null || v === undefined ? '—' : v.toFixed(1) + '%'; }
    function int(v) { return fmtEntero.format(v || 0); }

    var LOCALE_ES = {
        name: 'es',
        options: {
            months: ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
            shortMonths: ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'],
            days: ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'],
            shortDays: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'],
            toolbar: {
                exportToSVG: 'Descargar SVG', exportToPNG: 'Descargar PNG', exportToCSV: 'Descargar CSV',
                selection: 'Selección', selectionZoom: 'Zoom', zoomIn: 'Acercar', zoomOut: 'Alejar',
                pan: 'Mover', reset: 'Restablecer'
            }
        }
    };

    // Opciones globales: ApexCharts las aplica a toda gráfica creada después de este script.
    {
        window.Apex = {
            chart: {
                fontFamily: "'Inter', 'Plus Jakarta Sans', system-ui, sans-serif",
                foreColor: PALETA.text,
                locales: [LOCALE_ES],
                defaultLocale: 'es',
                toolbar: { show: false },
                zoom: { enabled: false },
                animations: { enabled: true, speed: 450 }
            },
            colors: SERIE,
            dataLabels: { enabled: false },
            grid: { borderColor: PALETA.grid, strokeDashArray: 4, padding: { left: 8, right: 8 } },
            legend: { position: 'top', horizontalAlign: 'right', fontWeight: 600, markers: { radius: 12 } },
            tooltip: { theme: 'light', style: { fontSize: '13px' } },
            xaxis: { axisBorder: { show: false }, axisTicks: { show: false } },
            states: { hover: { filter: { type: 'darken', value: 0.9 } } },
            noData: { text: 'Sin datos en este período', style: { color: PALETA.slate, fontSize: '14px' } }
        };
    }

    function tieneDatos(series) {
        if (!series || !series.length) return false;
        return series.some(function (s) {
            if (typeof s === 'number') return s > 0;
            var data = s.data || [];
            return data.some(function (p) {
                var v = (p && typeof p === 'object') ? p.y : p;
                return v !== null && v !== undefined && Number(v) !== 0;
            });
        });
    }

    /* Renderiza la gráfica o muestra el estado vacío del contenedor. */
    function render(selector, options, mensajeVacio) {
        var el = typeof selector === 'string' ? document.querySelector(selector) : selector;
        if (!el || typeof ApexCharts === 'undefined') return null;
        if (!tieneDatos(options.series)) {
            el.innerHTML = '<div class="ds-empty"><i class="bi bi-bar-chart-line"></i><span>' +
                (mensajeVacio || 'Aún no hay datos para este período') + '</span></div>';
            return null;
        }
        var chart = new ApexCharts(el, options);
        chart.render();
        return chart;
    }

    function leerJSON(id) {
        var nodo = document.getElementById(id);
        return nodo ? JSON.parse(nodo.textContent) : null;
    }

    window.DS = {
        color: PALETA, palette: SERIE,
        money: money, moneyShort: moneyShort, pct: pct, int: int,
        render: render, data: leerJSON, hasData: tieneDatos
    };
})();
