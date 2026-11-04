/**
 * Modal accesible basado en <dialog> (showModal hace inerte el resto de la página,
 * atrapa el foco y cierra con Escape). Devuelve el foco al elemento que lo abrió.
 */
import { h } from "./dom.js";
import { icon } from "./icons.js";

let contador = 0;

/**
 * @param {{
 *   titulo: string, contenido: Node|Node[], acciones?: Node[], tamano?: "md"|"lg"|"xl",
 *   alCerrar?: (valor: any) => void, cerrable?: boolean,
 * }} opciones
 * @returns {{dialog: HTMLDialogElement, cuerpo: HTMLElement, pie: HTMLElement, cerrar: (valor?: any) => void, cerrado: Promise<any>}}
 */
export function abrirModal({ titulo, contenido, acciones = [], tamano = "md", alCerrar, cerrable = true }) {
  const idTitulo = `modal-titulo-${++contador}`;
  const previo = /** @type {HTMLElement|null} */ (document.activeElement);
  let valorCierre;
  let resolver;
  const cerrado = new Promise((r) => { resolver = r; });

  const cuerpo = h("div", { class: "modal__body" }, contenido);
  const pie = h("div", { class: "modal__footer" }, acciones);
  const dialog = /** @type {HTMLDialogElement} */ (h(
    "dialog",
    { class: ["modal", tamano !== "md" && `modal--${tamano}`], "aria-labelledby": idTitulo },
    h("div", { class: "modal__header" },
      h("h2", { class: "modal__title", id: idTitulo }, titulo),
      cerrable && h("button", { type: "button", class: "btn btn--ghost btn--icon", "aria-label": "Cerrar", onclick: () => cerrar() }, icon("x"))),
    cuerpo,
    acciones.length ? pie : null,
  ));

  function cerrar(valor) {
    valorCierre = valor;
    if (dialog.open) dialog.close();
  }

  dialog.addEventListener("cancel", (e) => {
    if (!cerrable) e.preventDefault();
  });
  dialog.addEventListener("click", (e) => {
    if (cerrable && e.target === dialog) cerrar(); // clic en el fondo
  });
  dialog.addEventListener("close", () => {
    dialog.remove();
    alCerrar?.(valorCierre);
    resolver(valorCierre);
    if (previo && document.contains(previo)) previo.focus();
  });

  document.body.append(dialog);
  dialog.showModal();
  const primero = cuerpo.querySelector("[autofocus], input:not([type=hidden]):not([disabled]), select, textarea");
  (/** @type {HTMLElement|null} */ (primero))?.focus();
  return { dialog, cuerpo, pie, cerrar, cerrado };
}

/** Cierra todos los modales abiertos (al cambiar de página). */
export function cerrarModales() {
  document.querySelectorAll("dialog.modal[open]").forEach((d) => /** @type {HTMLDialogElement} */ (d).close());
}
