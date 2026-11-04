/**
 * Cliente HTTP central de la API.
 * - Agrega el token Bearer y maneja JSON.
 * - Timeout con AbortController (combinable con la señal de la página).
 * - Errores uniformes (ApiError) a partir de {"error": {codigo, mensaje, detalles}}.
 * - 401 → cierra la sesión; 403 → aviso de permisos.
 * - Descarga de archivos (PDF, XML, CSV) como Blob.
 */
import { CONFIG } from "./config.js";

export class ApiError extends Error {
  /**
   * @param {number} status código HTTP (0 = sin conexión)
   * @param {string} codigo código de error del backend (p. ej. STOCK_INSUFICIENTE)
   * @param {string} mensaje mensaje legible
   * @param {any} [detalles]
   */
  constructor(status, codigo, mensaje, detalles) {
    super(mensaje);
    this.name = "ApiError";
    this.status = status;
    this.codigo = codigo;
    this.detalles = detalles;
  }

  /** Errores de validación por campo: { campo: mensaje }. */
  get erroresCampo() {
    if (!Array.isArray(this.detalles)) return {};
    const errores = {};
    for (const d of this.detalles) {
      if (d && typeof d === "object" && "campo" in d && d.campo) {
        errores[d.campo] = traducirError(d);
      }
    }
    return errores;
  }

  /** Errores de validación generales (sin campo). */
  get erroresGenerales() {
    if (!Array.isArray(this.detalles)) return [];
    return this.detalles.filter((d) => d && typeof d === "object" && "campo" in d && !d.campo).map(traducirError);
  }
}

const TRADUCCIONES = {
  missing: "Este campo es obligatorio.",
  string_pattern_mismatch: "El formato no es válido.",
  string_too_short: "Es demasiado corto.",
  string_too_long: "Es demasiado largo.",
  greater_than: "Debe ser mayor.",
  greater_than_equal: "El valor es muy bajo.",
  less_than_equal: "El valor es muy alto.",
  int_parsing: "Debe ser un número entero.",
  decimal_parsing: "Debe ser un número.",
  literal_error: "Elige una opción válida.",
  extra_forbidden: "Campo no permitido.",
  bool_parsing: "Valor no válido.",
  datetime_from_date_parsing: "Fecha no válida.",
};

function traducirError(d) {
  if (d.tipo === "value_error") return String(d.mensaje || "").replace(/^Value error,\s*/i, "");
  if (d.tipo === "email" || /email/i.test(d.mensaje || "")) return "Correo electrónico no válido.";
  return TRADUCCIONES[d.tipo] || d.mensaje || "Valor no válido.";
}

/** Manejadores inyectados por auth/main para evitar dependencias circulares. */
const manejadores = {
  noAutenticado: /** @type {(e: ApiError) => void} */ (() => {}),
  prohibido: /** @type {(e: ApiError) => void} */ (() => {}),
  token: /** @type {() => string|null} */ (() => null),
};

export function configurarApi(opciones) {
  Object.assign(manejadores, opciones);
}

function construirUrl(ruta, query) {
  const url = new URL(`${CONFIG.API_BASE_URL}${ruta}`, window.location.origin);
  if (query) {
    for (const [clave, valor] of Object.entries(query)) {
      if (valor === undefined || valor === null || valor === "") continue;
      url.searchParams.set(clave, String(valor));
    }
  }
  return url.toString();
}

function nombreArchivo(respuesta, porDefecto) {
  const cd = respuesta.headers.get("Content-Disposition") || "";
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  return match ? decodeURIComponent(match[1]) : porDefecto;
}

/**
 * Llama a la API.
 * @param {string} ruta p. ej. "/ventas"
 * @param {{
 *   method?: string, body?: any, query?: Record<string, any>, headers?: Record<string,string>,
 *   timeout?: number, signal?: AbortSignal, archivo?: boolean, nombreArchivo?: string,
 *   silencioso403?: boolean,
 * }} [opciones]
 * @returns {Promise<any>} JSON, null (204) o {blob, nombre} si `archivo`
 */
export async function api(ruta, opciones = {}) {
  const {
    method = "GET", body, query, headers = {}, timeout = CONFIG.TIMEOUT_MS, signal,
    archivo = false, nombreArchivo: nombrePorDefecto = "archivo", silencioso403 = false,
  } = opciones;

  const control = new AbortController();
  const temporizador = setTimeout(() => control.abort(new DOMException("timeout", "TimeoutError")), timeout);
  const alAbortarExterno = () => control.abort(signal?.reason);
  signal?.addEventListener("abort", alAbortarExterno, { once: true });

  const token = manejadores.token();
  const cabeceras = { Accept: archivo ? "*/*" : "application/json", ...headers };
  if (token) cabeceras.Authorization = `Bearer ${token}`;
  if (body !== undefined) cabeceras["Content-Type"] = "application/json";

  let respuesta;
  try {
    respuesta = await fetch(construirUrl(ruta, query), {
      method,
      headers: cabeceras,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: control.signal,
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    if (signal?.aborted) throw new ApiError(0, "CANCELADO", "Petición cancelada.");
    if (control.signal.aborted) {
      throw new ApiError(0, "TIMEOUT", "El servidor tardó demasiado en responder. Intenta de nuevo.");
    }
    throw new ApiError(0, "RED", "No se pudo conectar con el servidor. Revisa tu conexión.");
  } finally {
    clearTimeout(temporizador);
    signal?.removeEventListener("abort", alAbortarExterno);
  }

  if (respuesta.ok) {
    if (archivo) return { blob: await respuesta.blob(), nombre: nombreArchivo(respuesta, nombrePorDefecto) };
    if (respuesta.status === 204) return null;
    const tipo = respuesta.headers.get("Content-Type") || "";
    return tipo.includes("application/json") ? respuesta.json() : respuesta.text();
  }

  let cuerpo = null;
  try {
    cuerpo = await respuesta.json();
  } catch {
    /* respuesta sin JSON */
  }
  const e = cuerpo?.error ?? {};
  const error = new ApiError(
    respuesta.status,
    e.codigo || `HTTP_${respuesta.status}`,
    e.mensaje || mensajePorEstado(respuesta.status),
    e.detalles,
  );

  if (respuesta.status === 401 && token) manejadores.noAutenticado(error);
  if (respuesta.status === 403 && !silencioso403) manejadores.prohibido(error);
  throw error;
}

function mensajePorEstado(status) {
  if (status >= 500) return "Error del servidor. Intenta de nuevo en unos minutos.";
  if (status === 404) return "No se encontró el recurso.";
  if (status === 429) return "Demasiadas peticiones. Espera un momento.";
  return "No se pudo completar la operación.";
}

/** Atajos. */
export const get = (ruta, query, op = {}) => api(ruta, { ...op, query });
export const post = (ruta, body, op = {}) => api(ruta, { ...op, method: "POST", body: body ?? {} });
export const put = (ruta, body, op = {}) => api(ruta, { ...op, method: "PUT", body });
export const del = (ruta, op = {}) => api(ruta, { ...op, method: "DELETE" });
export const descargar = (ruta, query, op = {}) => api(ruta, { ...op, query, archivo: true });
