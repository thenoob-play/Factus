/** Notificaciones (aria-live). */
import { h } from "./dom.js";
import { icon } from "./icons.js";

let region;

function obtenerRegion() {
  if (!region) {
    region = h("div", { class: "toasts", role: "region", "aria-label": "Notificaciones" });
    document.body.append(region);
  }
  return region;
}

const ICONO = { success: "checkCircle", error: "xCircle", warning: "alert", info: "info" };

/**
 * Muestra una notificación.
 * @param {string} mensaje
 * @param {{tipo?: "success"|"error"|"warning"|"info", titulo?: string, duracion?: number}} [opciones]
 */
export function toast(mensaje, { tipo = "info", titulo, duracion = tipo === "error" ? 7000 : 4000 } = {}) {
  const el = h(
    "div",
    { class: `toast toast--${tipo}`, role: tipo === "error" ? "alert" : "status", "aria-live": tipo === "error" ? "assertive" : "polite" },
    icon(ICONO[tipo]),
    h("div", { class: "toast__body" }, titulo && h("div", { class: "toast__title" }, titulo), h("div", null, mensaje)),
    h("button", { type: "button", class: "btn btn--ghost btn--icon btn--sm", "aria-label": "Cerrar notificación", onclick: () => cerrar() }, icon("x", { size: 16 })),
  );
  const cerrar = () => {
    el.classList.add("toast--leaving");
    setTimeout(() => el.remove(), 250);
  };
  obtenerRegion().append(el);
  if (duracion > 0) setTimeout(cerrar, duracion);
}

export const exito = (m, t) => toast(m, { tipo: "success", titulo: t });
export const aviso = (m, t) => toast(m, { tipo: "warning", titulo: t });

/** Muestra un error de la API (o cualquier error). */
export function error(err, titulo) {
  if (err?.codigo === "CANCELADO") return;
  const mensaje = err?.message || "Ocurrió un error inesperado.";
  const generales = err?.erroresGenerales?.length ? ` ${err.erroresGenerales.join(" ")}` : "";
  toast(mensaje + generales, { tipo: "error", titulo });
}
