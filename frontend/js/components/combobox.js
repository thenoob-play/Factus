/**
 * Select con búsqueda (patrón ARIA combobox + listbox), con fuente asíncrona.
 * Teclado: ↑/↓ para moverse, Enter para elegir, Escape para cerrar.
 */
import { h } from "./dom.js";
import { debounce } from "../utils/helpers.js";

let contador = 0;

/**
 * @param {{
 *   nombre?: string, placeholder?: string,
 *   buscar: (texto: string, signal: AbortSignal) => Promise<{valor: string|number, etiqueta: string, sub?: string, datos?: any}[]>,
 *   alElegir?: (opcion: any) => void, inicial?: {valor: any, etiqueta: string}|null,
 *   minimo?: number, vacioTexto?: string,
 * }} opciones
 */
export function combobox({ nombre, placeholder = "Buscar…", buscar, alElegir, inicial = null, minimo = 1, vacioTexto = "Sin resultados" }) {
  const id = `cb-${++contador}`;
  const lista = h("ul", { class: "listbox", id: `${id}-lista`, role: "listbox", hidden: true });
  const oculto = h("input", { type: "hidden", name: nombre, value: inicial?.valor ?? "" });
  const input = /** @type {HTMLInputElement} */ (h("input", {
    id, type: "text", class: "input", placeholder, autocomplete: "off", role: "combobox",
    "aria-expanded": "false", "aria-controls": lista.id, "aria-autocomplete": "list",
    value: inicial?.etiqueta ?? "",
  }));
  const raiz = h("div", { class: "combobox" }, input, oculto, lista);

  let opciones = [];
  let activo = -1;
  let control = null;
  let seleccion = inicial;

  const abrir = () => { lista.hidden = false; input.setAttribute("aria-expanded", "true"); };
  const cerrar = () => { lista.hidden = true; input.setAttribute("aria-expanded", "false"); activo = -1; input.removeAttribute("aria-activedescendant"); };

  function pintar() {
    lista.replaceChildren();
    if (!opciones.length) {
      lista.append(h("li", { class: "listbox__empty", role: "presentation" }, vacioTexto));
      return;
    }
    opciones.forEach((op, i) => {
      lista.append(h("li", {
        id: `${id}-op-${i}`, role: "option", class: "listbox__option", "aria-selected": String(i === activo),
        dataset: { indice: String(i) },
      }, h("span", { class: "listbox__label" }, op.etiqueta), op.sub && h("span", { class: "listbox__sub" }, op.sub)));
    });
  }

  function mover(delta) {
    if (!opciones.length) return;
    activo = (activo + delta + opciones.length) % opciones.length;
    pintar();
    const el = lista.querySelector(`#${id}-op-${activo}`);
    input.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  }

  function elegir(i) {
    const op = opciones[i];
    if (!op) return;
    seleccion = op;
    input.value = op.etiqueta;
    oculto.value = String(op.valor);
    cerrar();
    alElegir?.(op);
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  const consultar = debounce(async (texto) => {
    control?.abort();
    control = new AbortController();
    try {
      opciones = await buscar(texto, control.signal);
      activo = opciones.length ? 0 : -1;
      pintar();
      abrir();
    } catch (e) {
      if (e?.codigo !== "CANCELADO") {
        opciones = [];
        lista.replaceChildren(h("li", { class: "listbox__empty" }, e?.message || "Error al buscar"));
        abrir();
      }
    }
  }, 250);

  input.addEventListener("input", () => {
    oculto.value = "";
    seleccion = null;
    if (input.value.trim().length >= minimo) consultar(input.value.trim());
    else { consultar.cancel(); cerrar(); }
  });
  input.addEventListener("focus", () => { if (minimo === 0 && !seleccion) consultar(""); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (lista.hidden) consultar(input.value.trim()); else mover(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mover(-1); }
    else if (e.key === "Enter" && !lista.hidden && activo >= 0) { e.preventDefault(); elegir(activo); }
    else if (e.key === "Escape" && !lista.hidden) { e.stopPropagation(); e.preventDefault(); cerrar(); }
  });
  // mousedown para elegir antes de que el input pierda el foco
  lista.addEventListener("mousedown", (e) => {
    const li = /** @type {HTMLElement} */ (e.target).closest("[data-indice]");
    if (li) { e.preventDefault(); elegir(Number(li.dataset.indice)); }
  });
  input.addEventListener("blur", () => setTimeout(cerrar, 120));

  return {
    el: raiz,
    input,
    get valor() { return oculto.value || null; },
    get seleccion() { return seleccion; },
    fijar(op) {
      seleccion = op;
      input.value = op?.etiqueta ?? "";
      oculto.value = op ? String(op.valor) : "";
    },
  };
}
