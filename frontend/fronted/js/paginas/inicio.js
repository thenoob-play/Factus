import { obtenerResumen, mensajeDe } from '../api.js';
import { formatearMoneda, contar } from '../utils.js';
import { mostrarEstado, ocultarEstado } from '../ui.js';
import { cargarTablaFacturas } from './tablaFacturas.js';

const LIMITE_ULTIMAS = 5;
const $ = (id) => document.getElementById(id);

function pintarFecha() {
    const fecha = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'long', timeZone: 'America/Bogota' }).format(new Date());
    $('fecha-hoy').textContent = `, ${fecha}`;
}

function pintarIndicadores({ ventas_hoy: v, por_cobrar: c, clientes_nuevos_mes: nuevos, stock_bajo: s }) {
    $('ventas-valor').textContent = formatearMoneda(v.total);
    $('ventas-detalle').textContent = v.facturas === 0 ? 'Sin facturas emitidas hoy' : `${contar(v.facturas, 'factura emitida', 'facturas emitidas')} hoy`;
    $('cobrar-valor').textContent = formatearMoneda(c.total);
    $('cobrar-detalle').textContent = c.facturas === 0
        ? 'Sin facturas por cobrar'
        : `${contar(c.facturas, 'factura', 'facturas')}, ${c.vencidas === 0 ? 'ninguna vencida' : contar(c.vencidas, 'vencida', 'vencidas')}`;
    $('clientes-valor').textContent = nuevos;
    $('stock-valor').textContent = s.productos;
    $('stock-detalle').textContent = s.agotados === 0 ? 'Ninguno agotado' : contar(s.agotados, 'producto agotado', 'productos agotados');
}

async function cargarResumen() {
    const seccion = $('indicadores');
    const estado = $('estado-resumen');
    ocultarEstado(estado);
    seccion.setAttribute('aria-busy', 'true');
    try {
        pintarIndicadores(await obtenerResumen());
    } catch (error) {
        ['ventas', 'cobrar', 'clientes', 'stock'].forEach((k) => { $(`${k}-valor`).textContent = '—'; });
        ['ventas', 'cobrar', 'stock'].forEach((k) => { $(`${k}-detalle`).textContent = 'No disponible'; });
        mostrarEstado(estado, { esError: true, titulo: 'No pudimos cargar los indicadores', mensaje: mensajeDe(error), alReintentar: cargarResumen });
    } finally {
        seccion.removeAttribute('aria-busy');
    }
}

export function iniciar() {
    pintarFecha();
    cargarResumen();
    cargarTablaFacturas({ limite: LIMITE_ULTIMAS });
}
