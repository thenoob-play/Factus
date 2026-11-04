/** Tema claro/oscuro: sigue al sistema hasta que el usuario elige, y recuerda la elección. */
import { STORAGE_KEYS } from "./config.js";
import { storage } from "./utils/helpers.js";
import { icon } from "./components/icons.js";
import { h } from "./components/dom.js";

const media = window.matchMedia("(prefers-color-scheme: dark)");
const oyentes = new Set();

export function temaEfectivo() {
  const elegido = document.documentElement.dataset.theme;
  if (elegido === "light" || elegido === "dark") return elegido;
  return media.matches ? "dark" : "light";
}

function aplicar(tema) {
  if (tema === "light" || tema === "dark") document.documentElement.dataset.theme = tema;
  else delete document.documentElement.dataset.theme;
  oyentes.forEach((fn) => fn(temaEfectivo()));
}

export function iniciarTema() {
  aplicar(storage.get(STORAGE_KEYS.tema, "auto"));
  media.addEventListener("change", () => {
    if (!document.documentElement.dataset.theme) oyentes.forEach((fn) => fn(temaEfectivo()));
  });
}

export function alternarTema() {
  const nuevo = temaEfectivo() === "dark" ? "light" : "dark";
  storage.set(STORAGE_KEYS.tema, nuevo);
  aplicar(nuevo);
}

/** @param {(tema: "light"|"dark") => void} fn */
export function alCambiarTema(fn) {
  oyentes.add(fn);
  return () => oyentes.delete(fn);
}

/** Botón que alterna el tema y actualiza su icono y etiqueta. */
export function botonTema(clase = "btn btn--ghost btn--icon") {
  const boton = h("button", { type: "button", class: clase });
  const pintar = () => {
    const oscuro = temaEfectivo() === "dark";
    boton.replaceChildren(icon(oscuro ? "sun" : "moon"));
    boton.setAttribute("aria-label", oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro");
    boton.title = boton.getAttribute("aria-label");
  };
  boton.addEventListener("click", alternarTema);
  alCambiarTema(pintar);
  pintar();
  return boton;
}
