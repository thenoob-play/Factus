// Utilidades puras de formato y texto.
const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export const escaparHtml = (texto) => String(texto ?? '').replace(/[&<>"']/g, (c) => ESCAPES[c]);

// Ignora tildes y mayúsculas: "cafe" encuentra "Café".
export function normalizarTexto(texto) {
    return String(texto ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('es');
}

// 1250000 -> $1.250.000 (sin decimales)
export function formatearMoneda(valor) {
    const n = Number(valor);
    if (!Number.isFinite(n)) return '—';
    const entero = Math.round(Math.abs(n)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return `${n < 0 ? '-' : ''}$${entero}`;
}

// '2026-11-04' o '2026-11-04T21:28:04' -> 04/11/2026 (sin desfases de zona horaria)
export function formatearFecha(valor) {
    const texto = String(valor ?? '');
    const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(texto);
    if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
    const fecha = new Date(texto);
    if (!texto || Number.isNaN(fecha.getTime())) return '—';
    const partes = Object.fromEntries(
        new Intl.DateTimeFormat('es-CO', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'America/Bogota' })
            .formatToParts(fecha).map((p) => [p.type, p.value]),
    );
    return `${partes.day}/${partes.month}/${partes.year}`;
}

export const contar = (n, singular, plural) => `${n} ${n === 1 ? singular : plural}`;
