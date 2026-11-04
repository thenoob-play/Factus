/**
 * Configuración del frontend.
 *
 * API_BASE_URL:
 *  - Vacío ("") cuando la interfaz la sirve la propia API (http://127.0.0.1:8000/ui/): mismo origen.
 *  - URL absoluta si sirves el frontend desde otro servidor, p. ej. "http://127.0.0.1:8000".
 *    En ese caso agrega el origen del frontend a CORS_ORIGINS en el .env del backend y a
 *    connect-src en la Content-Security-Policy de index.html y app.html.
 * También se puede sobrescribir sin tocar este archivo con
 *   localStorage.setItem("factu.apiBaseUrl", "http://127.0.0.1:8000")
 */
function leerOverride() {
  try {
    return localStorage.getItem("factu.apiBaseUrl");
  } catch {
    return null;
  }
}

export const CONFIG = Object.freeze({
  API_BASE_URL: (leerOverride() ?? "").replace(/\/$/, ""),
  TIMEOUT_MS: 20000,
  TIMEOUT_FACTUS_MS: 60000,
  POLL_PAGO_MS: 4000,
  POLL_FACTURA_MS: 3000,
  PAGE_SIZE: 20,
  CHART_JS_URL: "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js",
  QR_LIB_URL: "https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js",
});

/** Subresource Integrity: el navegador rechaza el script si el CDN lo modifica. */
export const SRI = Object.freeze({
  [CONFIG.CHART_JS_URL]: "sha384-9nhczxUqK87bcKHh20fSQcTGD4qq5GhayNYSYWqwBkINBhOfQLg/P5HG5lF1urn4",
  [CONFIG.QR_LIB_URL]: "sha384-lQXOAyZwHXE55JFyrOMB7nY2Wv+m5ZWNtJcHrd1rceRQXAYNLak8ukN5TjBTcIwz",
});

export const STORAGE_KEYS = Object.freeze({
  sesion: "factu.sesion",
  tema: "factu.tema",
  sidebar: "factu.sidebar",
  borradorVenta: "factu.borrador.venta",
});

/** Tablas oficiales de Factus (las mismas que valida el backend). */
export const CATALOGOS = Object.freeze({
  tiposDocumento: [
    ["13", "Cédula de ciudadanía"],
    ["31", "NIT"],
    ["22", "Cédula de extranjería"],
    ["41", "Pasaporte"],
    ["12", "Tarjeta de identidad"],
    ["11", "Registro civil"],
    ["21", "Tarjeta de extranjería"],
    ["42", "Documento de identificación extranjero"],
    ["47", "PEP"],
    ["48", "PPT"],
    ["50", "NIT de otro país"],
    ["91", "NUIP"],
  ],
  tributos: [
    ["ZZ", "No aplica"],
    ["01", "Responsable de IVA"],
  ],
  conceptosNota: [
    ["2", "Anulación de factura electrónica"],
    ["1", "Devolución parcial de bienes / servicio"],
    ["3", "Rebaja o descuento parcial o total"],
    ["4", "Ajuste de precio"],
    ["5", "Descuento por pronto pago"],
    ["6", "Descuento por volumen de ventas"],
  ],
  unidadesComunes: [
    ["94", "Unidad"],
    ["KGM", "Kilogramo"],
    ["GRM", "Gramo"],
    ["LTR", "Litro"],
    ["MTR", "Metro"],
    ["HUR", "Hora"],
    ["MON", "Mes"],
  ],
});

export const METODOS = Object.freeze({
  EFECTIVO: "Efectivo",
  TRANSFERENCIA: "Transferencia",
  TARJETA: "Tarjeta",
});

export const CANALES = Object.freeze({
  EFECTIVO: "Efectivo",
  WOMPI: "Pasarela Wompi",
  BREB_MANUAL: "Bre-B (manual)",
  DATAFONO: "Datáfono",
});
