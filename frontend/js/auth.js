/**
 * Sesión: token JWT y datos del usuario en localStorage, con expiración local.
 * El backend es quien autoriza; los roles aquí solo ocultan menús y botones.
 */
import { STORAGE_KEYS } from "./config.js";
import { post } from "./api.js";
import { storage } from "./utils/helpers.js";

/** @returns {{token:string, expira:number, usuario:{idtrabajador:number,nombre:string,email:string,rol:string}}|null} */
export function sesion() {
  const s = storage.get(STORAGE_KEYS.sesion);
  if (!s || typeof s.token !== "string" || typeof s.expira !== "number") return null;
  if (Date.now() >= s.expira) {
    storage.remove(STORAGE_KEYS.sesion);
    return null;
  }
  return s;
}

export const token = () => sesion()?.token ?? null;
export const usuario = () => sesion()?.usuario ?? null;
export const esAdmin = () => usuario()?.rol === "ADMIN";

/** @param {...string} roles */
export function tieneRol(...roles) {
  const u = usuario();
  return Boolean(u && (roles.length === 0 || roles.includes(u.rol)));
}

/** Inicia sesión y guarda el token. */
export async function iniciarSesion(email, password) {
  const r = await post("/auth/login", { email, password });
  storage.set(STORAGE_KEYS.sesion, {
    token: r.access_token,
    expira: Date.now() + (r.expires_in - 30) * 1000,
    usuario: r.usuario,
  });
  return r.usuario;
}

/**
 * Cierra la sesión y vuelve al login.
 * @param {string} [motivo] "expirada" | "salir"
 */
export function cerrarSesion(motivo = "salir") {
  storage.remove(STORAGE_KEYS.sesion);
  const destino = new URL("index.html", window.location.href);
  if (motivo !== "salir") destino.searchParams.set("motivo", motivo);
  window.location.replace(destino.toString());
}
