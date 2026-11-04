// Plantillas HTML (mismas clases del diseño original) y estados de carga/error/vacío.
import { escaparHtml, formatearFecha, formatearMoneda } from './utils.js';

const UMBRAL_STOCK_BAJO = 10;

export function estadoProducto(stock) {
    if (stock <= 0) return { clase: 'agotado', etiqueta: 'Agotado' };
    if (stock <= UMBRAL_STOCK_BAJO) return { clase: 'bajo', etiqueta: 'Stock bajo' };
    return { clase: 'ok', etiqueta: 'Disponible' };
}

export function tarjetaProducto(p) {
    const stock = Number(p.stock) || 0;
    const { clase, etiqueta } = estadoProducto(stock);
    const inicial = (String(p.nombre ?? '').match(/[\p{L}\p{N}]/u)?.[0] ?? '?').toUpperCase();
    return `<article class="card" data-buscable>
    <div class="card-top"><div class="card-icon" aria-hidden="true">${escaparHtml(inicial)}</div><span class="badge ${clase}">${etiqueta}</span></div>
    <div><h2>${escaparHtml(p.nombre)}</h2><div class="ref">Ref. ${escaparHtml(p.referencia)}</div></div>
    <div class="card-bottom"><span class="precio">${formatearMoneda(p.precio)}</span><span class="stock">${stock} ${stock === 1 ? 'ud.' : 'uds.'}</span></div>
</article>`;
}

export function filaFactura(f) {
    const estado = String(f.estado ?? '').toLowerCase();
    const clase = ['pagada', 'pendiente', 'vencida'].includes(estado) ? estado : '';
    const etiqueta = estado.charAt(0).toUpperCase() + estado.slice(1);
    return `<tr data-buscable>
    <td class="codigo">${escaparHtml(f.codigo)}</td><td>${escaparHtml(f.cliente)}</td><td>${formatearFecha(f.fecha)}</td>
    <td class="num">${formatearMoneda(f.total)}</td><td><span class="badge ${clase}">${escaparHtml(etiqueta)}</span></td>
</tr>`;
}

export const esqueletoTarjetas = (n = 8) => Array.from({ length: n }, () => `<article class="card" data-esqueleto aria-hidden="true">
    <div class="card-top"><div class="card-icon esqueleto"></div><span class="esqueleto esq-pildora"></span></div>
    <div><div class="esqueleto esq-linea"></div><div class="esqueleto esq-linea corta"></div></div>
    <div class="card-bottom"><span class="esqueleto esq-linea corta"></span></div>
</article>`).join('');

export const esqueletoFilas = (n = 5) => Array.from({ length: n }, () =>
    '<tr aria-hidden="true"><td colspan="5"><div class="esqueleto esq-linea ancha"></div></td></tr>').join('');

export function mostrarEstado(contenedor, { esError = false, titulo, mensaje, alReintentar }) {
    contenedor.hidden = false;
    contenedor.innerHTML = `<div class="vacio${esError ? ' error' : ''}" role="${esError ? 'alert' : 'status'}"><strong>${escaparHtml(titulo)}</strong>${escaparHtml(mensaje)}${alReintentar ? '<br><button type="button" class="btn-reintentar">Reintentar</button>' : ''}</div>`;
    contenedor.querySelector('button')?.addEventListener('click', alReintentar);
}

export function ocultarEstado(contenedor) {
    contenedor.hidden = true;
    contenedor.replaceChildren();
}
