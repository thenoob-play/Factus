/** Utilidades generales: debounce, almacenamiento seguro, validaciones, descargas. */
import { SRI } from "../config.js";

/**
 * Retrasa la ejecución hasta que pasen `ms` sin nuevas llamadas.
 * @template {(...args: any[]) => void} F
 * @param {F} fn
 * @param {number} ms
 * @returns {F & {cancel: () => void}}
 */
export function debounce(fn, ms = 300) {
  let t;
  const wrapped = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(t);
  return /** @type {any} */ (wrapped);
}

/** localStorage que nunca lanza (modo privado, almacenamiento bloqueado…). */
export const storage = {
  get(clave, porDefecto = null) {
    try {
      const valor = localStorage.getItem(clave);
      return valor === null ? porDefecto : JSON.parse(valor);
    } catch {
      return porDefecto;
    }
  },
  set(clave, valor) {
    try {
      localStorage.setItem(clave, JSON.stringify(valor));
    } catch {
      /* sin almacenamiento: la app sigue funcionando */
    }
  },
  remove(clave) {
    try {
      localStorage.removeItem(clave);
    } catch {
      /* ignorar */
    }
  },
};

const PESOS_DV = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71];

/**
 * Dígito de verificación del NIT (algoritmo DIAN). Devuelve null si el NIT no es válido.
 * @param {string} nit solo dígitos, sin DV
 */
export function dvNit(nit) {
  const limpio = String(nit ?? "").trim();
  if (!/^\d{1,15}$/.test(limpio)) return null;
  const suma = [...limpio].reverse().reduce((acc, d, i) => acc + Number(d) * PESOS_DV[i], 0);
  const r = suma % 11;
  return String(r === 0 || r === 1 ? r : 11 - r);
}

export const validar = {
  email: (v) => !v || /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v),
  telefono: (v) => !v || /^\+?[0-9 ]{7,20}$/.test(v),
  requerido: (v) => String(v ?? "").trim().length > 0,
};

/** Descarga un Blob con el nombre indicado. */
export function guardarBlob(blob, nombre) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

/** Copia texto al portapapeles. Devuelve true si se pudo. */
export async function copiar(texto) {
  try {
    await navigator.clipboard.writeText(texto);
    return true;
  } catch {
    return false;
  }
}

/** Carga un script externo una sola vez (Chart.js, generador de QR). */
const scriptsCargados = new Map();
export function cargarScript(url) {
  if (!scriptsCargados.has(url)) {
    scriptsCargados.set(url, new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = url;
      if (SRI[url]) s.integrity = SRI[url];
      s.async = true;
      s.crossOrigin = "anonymous";
      s.referrerPolicy = "no-referrer";
      s.onload = () => resolve();
      s.onerror = () => {
        scriptsCargados.delete(url);
        reject(new Error(`No se pudo cargar ${url}`));
      };
      document.head.append(s);
    }));
  }
  return scriptsCargados.get(url);
}

/** Genera una clave única (para Idempotency-Key). */
export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Lee un archivo como data URL (base64). */
export function leerComoDataURL(archivo) {
  return new Promise((resolve, reject) => {
    const lector = new FileReader();
    lector.onload = () => resolve(String(lector.result));
    lector.onerror = () => reject(lector.error);
    lector.readAsDataURL(archivo);
  });
}
