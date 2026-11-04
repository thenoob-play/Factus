// Carga la tabla de facturas (compartida por Inicio y Facturas).
import { obtenerFacturas, mensajeDe } from '../api.js';
import { filaFactura, esqueletoFilas, mostrarEstado, ocultarEstado } from '../ui.js';
import { refrescarBuscador } from '../buscador.js';

export async function cargarTablaFacturas({ limite, alTerminar } = {}) {
    const cuerpo = document.getElementById('tabla-facturas');
    const envoltorio = cuerpo.closest('.tabla-wrap');
    const estado = document.getElementById('estado-facturas');
    let resultado = null;

    ocultarEstado(estado);
    envoltorio.hidden = false;
    cuerpo.setAttribute('aria-busy', 'true');
    cuerpo.innerHTML = esqueletoFilas();
    refrescarBuscador();

    try {
        const facturas = (await obtenerFacturas({ limite })).slice(0, limite || undefined);
        if (facturas.length === 0) {
            envoltorio.hidden = true;
            mostrarEstado(estado, { titulo: 'Aún no hay facturas', mensaje: 'Cuando emitas la primera aparecerá aquí.' });
        } else {
            cuerpo.innerHTML = facturas.map(filaFactura).join('');
        }
        resultado = facturas;
    } catch (error) {
        envoltorio.hidden = true;
        mostrarEstado(estado, {
            esError: true,
            titulo: 'No pudimos cargar las facturas',
            mensaje: mensajeDe(error),
            alReintentar: () => cargarTablaFacturas({ limite, alTerminar }),
        });
    } finally {
        cuerpo.removeAttribute('aria-busy');
        refrescarBuscador();
    }
    alTerminar?.(resultado);
}
