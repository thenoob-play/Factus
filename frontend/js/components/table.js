/**
 * Tabla de datos paginada en el servidor, con orden por columna, skeleton de carga,
 * estado vacío, delegación de eventos y vista de tarjetas en móvil (CSS).
 */
import { h, montar } from "./dom.js";
import { icon } from "./icons.js";
import { vacio } from "./ui.js";
import { error as toastError } from "./toast.js";
import { CONFIG } from "../config.js";

/**
 * @typedef {{ clave: string, titulo: string, ordenable?: boolean, num?: boolean,
 *   render?: (fila: any) => any, clase?: string }} Columna
 * @typedef {{ accion: string, icono: string, etiqueta: string, visible?: (fila: any) => boolean, peligro?: boolean }} AccionFila
 */

/**
 * @param {{
 *   columnas: Columna[],
 *   cargar: (params: {page:number, page_size:number, ordenar?:string, desc?:boolean}, signal: AbortSignal) => Promise<{items:any[], total:number, page:number, pages:number}>,
 *   clave: (fila: any) => string|number,
 *   alClic?: (fila: any) => void,
 *   acciones?: AccionFila[],
 *   alAccion?: (accion: string, fila: any) => void,
 *   vacio?: () => Node,
 *   orden?: {clave: string, desc: boolean},
 *   etiqueta: string,
 * }} opciones
 */
export function tablaDatos(opciones) {
  const { columnas, acciones = [] } = opciones;
  const estado = { page: 1, page_size: CONFIG.PAGE_SIZE, orden: opciones.orden ?? null, filas: [], total: 0, pages: 0 };
  let control = null;

  const thead = h("thead");
  const tbody = h("tbody");
  const tabla = h("table", { class: ["table", "table--cards", opciones.alClic && "table--clickable"], "aria-label": opciones.etiqueta }, thead, tbody);
  const info = h("span", { "aria-live": "polite" });
  const anterior = h("button", { type: "button", class: "btn btn--sm", "aria-label": "Página anterior" }, icon("chevronLeft", { size: 16 }));
  const siguiente = h("button", { type: "button", class: "btn btn--sm", "aria-label": "Página siguiente" }, icon("chevronRight", { size: 16 }));
  const tamano = h("select", { class: "select", "aria-label": "Filas por página", value: String(estado.page_size) },
    [10, 20, 50, 100].map((n) => h("option", { value: String(n) }, `${n} por página`)));
  const pager = h("div", { class: "pager" }, info, h("div", { class: "pager__controls" }, tamano, anterior, siguiente));
  const raiz = h("div", null, h("div", { class: "table-wrap" }, tabla), pager);

  function pintarEncabezado() {
    montar(thead, h("tr", null,
      columnas.map((c) => {
        const ordenada = estado.orden?.clave === c.clave;
        const th = h("th", { scope: "col", class: c.num ? "num" : null,
          "aria-sort": ordenada ? (estado.orden.desc ? "descending" : "ascending") : null });
        if (c.ordenable) {
          th.append(h("button", { type: "button", class: "th-sort", dataset: { orden: c.clave } }, c.titulo,
            icon(ordenada ? (estado.orden.desc ? "sortDown" : "sortUp") : "sort", { size: 13 })));
        } else {
          th.append(c.titulo);
        }
        return th;
      }),
      acciones.length ? h("th", { scope: "col" }, h("span", { class: "visually-hidden" }, "Acciones")) : null));
  }

  function pintarSkeleton() {
    montar(tbody, Array.from({ length: 5 }, () => h("tr", null,
      columnas.map((c) => h("td", { "data-label": c.titulo }, h("span", { class: "skeleton" }))),
      acciones.length ? h("td") : null)));
  }

  function pintarFilas() {
    if (!estado.filas.length) {
      montar(tbody, h("tr", null, h("td", { colspan: String(columnas.length + (acciones.length ? 1 : 0)), "data-label": "" },
        opciones.vacio?.() ?? vacio({ icono: "search", titulo: "Sin resultados", texto: "No hay registros que coincidan con los filtros." }))));
      return;
    }
    montar(tbody, estado.filas.map((fila, i) => h("tr", { dataset: { indice: String(i) }, tabindex: opciones.alClic ? "0" : null },
      columnas.map((c) => h("td", { "data-label": c.titulo, class: [c.num && "num", c.clase] },
        c.render ? c.render(fila) : (fila[c.clave] ?? "—"))),
      acciones.length ? h("td", { class: "cell-actions", "data-label": "" },
        acciones.filter((a) => !a.visible || a.visible(fila)).map((a) => h("button", {
          type: "button", class: ["btn btn--ghost btn--icon btn--sm"], dataset: { accion: a.accion },
          "aria-label": a.etiqueta, title: a.etiqueta,
        }, icon(a.icono, { size: 16 })))) : null)));
  }

  function pintarPager() {
    const desde = estado.total ? (estado.page - 1) * estado.page_size + 1 : 0;
    const hasta = Math.min(estado.page * estado.page_size, estado.total);
    info.textContent = estado.total ? `${desde}–${hasta} de ${estado.total}` : "0 resultados";
    anterior.disabled = estado.page <= 1;
    siguiente.disabled = estado.page >= estado.pages;
  }

  async function recargar({ reiniciar = false } = {}) {
    if (reiniciar) estado.page = 1;
    control?.abort();
    control = new AbortController();
    pintarSkeleton();
    try {
      const r = await opciones.cargar({
        page: estado.page, page_size: estado.page_size,
        ordenar: estado.orden?.clave, desc: estado.orden?.desc,
      }, control.signal);
      Object.assign(estado, { filas: r.items, total: r.total, pages: r.pages });
      pintarFilas();
      pintarPager();
    } catch (e) {
      if (e?.codigo === "CANCELADO") return;
      montar(tbody, h("tr", null, h("td", { colspan: String(columnas.length + 1), "data-label": "" },
        vacio({ icono: "alert", titulo: "No se pudieron cargar los datos", texto: e?.message,
          accion: h("button", { type: "button", class: "btn", onclick: () => recargar() }, icon("refresh"), "Reintentar") }))));
      toastError(e);
    }
  }

  // Delegación de eventos
  thead.addEventListener("click", (e) => {
    const b = /** @type {HTMLElement} */ (e.target).closest("[data-orden]");
    if (!b) return;
    const clave = b.dataset.orden;
    estado.orden = { clave, desc: estado.orden?.clave === clave ? !estado.orden.desc : false };
    pintarEncabezado();
    recargar({ reiniciar: true });
  });
  tbody.addEventListener("click", (e) => {
    const destino = /** @type {HTMLElement} */ (e.target);
    const tr = destino.closest("tr[data-indice]");
    if (!tr) return;
    const fila = estado.filas[Number(tr.dataset.indice)];
    const b = destino.closest("[data-accion]");
    if (b) { e.stopPropagation(); opciones.alAccion?.(b.dataset.accion, fila); return; }
    if (destino.closest("a, button, input")) return;
    opciones.alClic?.(fila);
  });
  tbody.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !opciones.alClic) return;
    const tr = /** @type {HTMLElement} */ (e.target).closest("tr[data-indice]");
    if (tr && e.target === tr) opciones.alClic(estado.filas[Number(tr.dataset.indice)]);
  });
  anterior.addEventListener("click", () => { estado.page -= 1; recargar(); });
  siguiente.addEventListener("click", () => { estado.page += 1; recargar(); });
  tamano.addEventListener("change", () => { estado.page_size = Number(tamano.value); recargar({ reiniciar: true }); });

  pintarEncabezado();
  return { el: raiz, recargar, abortar: () => control?.abort() };
}
