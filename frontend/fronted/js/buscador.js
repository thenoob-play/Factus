// Filtro de búsqueda compartido: filtra cualquier elemento [data-buscable],
// incluidos los generados dinámicamente (se consultan en cada filtrado).
import { normalizarTexto } from './utils.js';

const cache = new WeakMap();
let entrada = null;

function textoDe(el) {
    if (!cache.has(el)) cache.set(el, normalizarTexto(el.textContent));
    return cache.get(el);
}

export function filtrar() {
    if (!entrada) return;
    const consulta = normalizarTexto(entrada.value.trim());
    const elementos = document.querySelectorAll('[data-buscable]');
    let visibles = 0;

    elementos.forEach((el) => {
        const coincide = textoDe(el).includes(consulta);
        el.hidden = !coincide;
        if (coincide) visibles += 1;
    });

    const mensajeVacio = document.getElementById('sin-resultados');
    const info = document.getElementById('resultados-info');
    if (mensajeVacio) mensajeVacio.hidden = visibles > 0 || elementos.length === 0;
    if (info) {
        const { singular, plural } = entrada.dataset;
        info.textContent = elementos.length ? `${visibles} ${visibles === 1 ? singular : plural}.` : '';
    }
}

export const refrescarBuscador = filtrar;

export function iniciarBuscador() {
    entrada = document.getElementById('buscador');
    if (!entrada) return;
    entrada.addEventListener('input', filtrar);
    filtrar();
}
