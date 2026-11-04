import { formatearMoneda, contar } from '../utils.js';
import { cargarTablaFacturas } from './tablaFacturas.js';

export function iniciar() {
    const resumen = document.getElementById('resumen-facturas');
    cargarTablaFacturas({
        alTerminar: (facturas) => {
            if (!facturas) resumen.textContent = 'Consulta las facturas emitidas.';
            else if (facturas.length === 0) resumen.textContent = 'Aún no hay facturas registradas.';
            else {
                const total = facturas.reduce((acc, f) => acc + (Number(f.total) || 0), 0);
                resumen.textContent = `${contar(facturas.length, 'factura', 'facturas')} por un total de ${formatearMoneda(total)}.`;
            }
        },
    });
}
