/** Formato de moneda, números y fechas en es-CO. */

const copFmt = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});
const numFmt = new Intl.NumberFormat("es-CO", { maximumFractionDigits: 2 });
const fechaFmt = new Intl.DateTimeFormat("es-CO", { day: "2-digit", month: "short", year: "numeric" });
const fechaHoraFmt = new Intl.DateTimeFormat("es-CO", {
  day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});
const diaCortoFmt = new Intl.DateTimeFormat("es-CO", { day: "2-digit", month: "short" });

/**
 * Formatea un monto en pesos colombianos. Acepta números o strings decimales del backend.
 * @param {number|string|null|undefined} valor
 * @returns {string} p. ej. "$ 1.250.000"
 */
export function cop(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? copFmt.format(n) : "—";
}

/** @param {number|string} valor */
export function numero(valor) {
  const n = Number(valor);
  return Number.isFinite(n) ? numFmt.format(n) : "—";
}

/**
 * Convierte una fecha del backend a Date. El backend guarda UTC sin zona
 * ("2026-11-04T15:30:00"); se interpreta como UTC.
 * @param {string|null|undefined} valor
 * @returns {Date|null}
 */
export function parseFecha(valor) {
  if (!valor) return null;
  const texto = String(valor);
  const conZona = /[zZ]|[+-]\d{2}:?\d{2}$/.test(texto) || texto.length <= 10 ? texto : `${texto}Z`;
  const fecha = new Date(conZona.length === 10 ? `${conZona}T00:00:00` : conZona);
  return Number.isNaN(fecha.getTime()) ? null : fecha;
}

/** @param {string|Date|null} valor */
export function fecha(valor) {
  const d = valor instanceof Date ? valor : parseFecha(valor);
  return d ? fechaFmt.format(d) : "—";
}

/** @param {string|Date|null} valor */
export function fechaHora(valor) {
  const d = valor instanceof Date ? valor : parseFecha(valor);
  return d ? fechaHoraFmt.format(d) : "—";
}

/** "2026-11-04" (día calendario) → "04 nov" */
export function diaCorto(isoDia) {
  const [y, m, d] = String(isoDia).split("-").map(Number);
  return diaCortoFmt.format(new Date(y, m - 1, d));
}

/** Fecha local en formato YYYY-MM-DD (para inputs type=date). */
export function isoDiaLocal(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Fecha y hora local para inputs datetime-local. */
export function isoLocalMinutos(d = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${isoDiaLocal(d)}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Segundos → "mm:ss" (o "h:mm:ss"). */
export function duracion(segundos) {
  const s = Math.max(0, Math.floor(segundos));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${pad(m)}:${pad(r)}` : `${pad(m)}:${pad(r)}`;
}

/** Iniciales para avatares. */
export function iniciales(nombre = "") {
  return nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?";
}

/**
 * Escapa HTML. La interfaz construye el DOM con createElement/textContent; esta función
 * existe para los casos excepcionales en que haga falta interpolar texto en HTML.
 * @param {unknown} valor
 */
export function escapeHTML(valor) {
  return String(valor ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
