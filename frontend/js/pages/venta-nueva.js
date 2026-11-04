/**
 * Nueva venta (punto de venta).
 * - El frontend solo envía idcliente, metodoPago, canal e items {idproducto, cantidad}.
 *   Los totales que se muestran son referenciales; los oficiales los devuelve el servidor.
 * - El carrito se guarda como borrador en localStorage.
 * - Cada borrador tiene una Idempotency-Key: si la confirmación falla por red y se reintenta
 *   sin cambios, el backend devuelve la misma venta (nunca se crea dos veces).
 */
import { get, post } from "../api.js";
import { STORAGE_KEYS, METODOS } from "../config.js";
import { h, montar, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { combobox } from "../components/combobox.js";
import { callout, confirmar, encabezado, vacio } from "../components/ui.js";
import { exito, error as toastError } from "../components/toast.js";
import { cop, numero } from "../utils/format.js";
import { debounce, storage, uuid } from "../utils/helpers.js";
import { abrirFormularioCliente, nombreCliente, documentoCliente } from "./clientes.js";

/** Totales estimados en centavos enteros, con el mismo redondeo por línea que el backend. */
export function estimarTotales(items) {
  let subtotal = 0; let descuento = 0; let iva = 0;
  const porTarifa = new Map();
  for (const it of items) {
    const precio = Math.round(Number(it.precio_unitario) * 100);
    const bruto = precio * it.cantidad;
    const desc = Math.round((bruto * Math.round(Number(it.discount_rate || 0) * 100)) / 10000);
    const base = bruto - desc;
    const tarifa = it.is_excluded ? 0 : Math.round(Number(it.tax_rate || 0) * 100);
    const impuesto = Math.round((base * tarifa) / 10000);
    subtotal += bruto; descuento += desc; iva += impuesto;
    const clave = it.is_excluded ? "Excluido" : `${tarifa / 100} %`;
    const g = porTarifa.get(clave) ?? { base: 0, iva: 0 };
    porTarifa.set(clave, { base: g.base + base, iva: g.iva + impuesto });
  }
  return {
    subtotal: subtotal / 100, descuento: descuento / 100, iva: iva / 100,
    total: (subtotal - descuento + iva) / 100,
    porTarifa: [...porTarifa.entries()].map(([tarifa, g]) => ({ tarifa, base: g.base / 100, iva: g.iva / 100 })),
  };
}

const CANALES_METODO = {
  EFECTIVO: [],
  TRANSFERENCIA: [["", "Automático"], ["BREB_MANUAL", "Bre-B con comprobante"], ["WOMPI", "Pasarela Wompi"]],
  TARJETA: [["", "Automático"], ["DATAFONO", "Datáfono"], ["WOMPI", "Pasarela Wompi"]],
};

function borradorVacio() {
  return { clave: uuid(), cliente: null, metodo: "EFECTIVO", canal: "", items: [] };
}

export default async function paginaNuevaVenta(ctx) {
  let borrador = storage.get(STORAGE_KEYS.borradorVenta) ?? borradorVacio();
  if (!Array.isArray(borrador.items)) borrador = borradorVacio();
  // Si viene "?repetir=" (venta expirada/cancelada), se precarga desde esa venta.
  const repetir = ctx.query.get("repetir");
  if (repetir) await precargarDesdeVenta(repetir);

  /** Cualquier cambio invalida la clave anterior (otro cuerpo = otra venta). */
  function guardar({ cambioContenido = true } = {}) {
    if (cambioContenido) borrador.clave = uuid();
    storage.set(STORAGE_KEYS.borradorVenta, borrador);
  }

  async function precargarDesdeVenta(idventa) {
    try {
      const v = await get(`/ventas/${idventa}`, null, { signal: ctx.signal });
      const cliente = await get(`/clientes/${v.idcliente}`, null, { signal: ctx.signal }).catch(() => null);
      borrador = {
        clave: uuid(), metodo: v.metodo_pago, canal: "",
        cliente: cliente ? { valor: cliente.idcliente, etiqueta: nombreCliente(cliente), sub: documentoCliente(cliente) } : null,
        items: [],
      };
      for (const it of v.items) {
        const p = await get(`/productos/${it.idproducto}`, null, { signal: ctx.signal }).catch(() => null);
        if (p && p.estado === "ACTIVO" && p.stock_disponible > 0) {
          borrador.items.push({ ...resumenProducto(p), cantidad: Math.min(it.cantidad, p.stock_disponible) });
        }
      }
      storage.set(STORAGE_KEYS.borradorVenta, borrador);
    } catch (e) { toastError(e); }
  }

  // ------------------------------------------------------------ búsqueda
  const busqueda = /** @type {HTMLInputElement} */ (h("input", {
    type: "search", class: "input", placeholder: "Buscar producto por nombre o código…", autocomplete: "off",
    role: "combobox", "aria-expanded": "true", "aria-controls": "pos-resultados", "aria-label": "Buscar producto",
  }));
  const resultados = h("ul", { class: "pos__results", id: "pos-resultados", role: "listbox", "aria-label": "Productos" });
  let productos = [];
  let activo = -1;
  let control = null;

  function resumenProducto(p) {
    return {
      idproducto: p.idproducto, nombre: p.nombre, code_reference: p.code_reference,
      precio_unitario: p.precio_unitario, tax_rate: p.tax_rate, is_excluded: Boolean(p.is_excluded),
      discount_rate: p.discount_rate, disponible: p.stock_disponible,
    };
  }

  function pintarResultados() {
    if (!productos.length) {
      montar(resultados, h("li", { role: "presentation" }, vacio({ icono: "box", titulo: "Sin productos", texto: "Prueba con otro nombre o código." })));
      return;
    }
    montar(resultados, productos.map((p, i) => {
      const enCarrito = borrador.items.find((it) => it.idproducto === p.idproducto)?.cantidad ?? 0;
      const agotado = p.stock_disponible - enCarrito <= 0;
      return h("li", {
        id: `prod-${i}`, role: "option", class: "product-row", "aria-selected": String(i === activo),
        "aria-disabled": String(agotado), dataset: { indice: String(i) },
      },
      h("div", null,
        h("div", { class: "product-row__name" }, p.nombre),
        h("div", { class: "product-row__meta" }, h("span", { class: "mono" }, p.code_reference), " · ",
          p.is_excluded ? "Excluido de IVA" : `IVA ${Number(p.tax_rate)} %`,
          Number(p.discount_rate) > 0 ? ` · ${Number(p.discount_rate)} % dto.` : "")),
      h("span", { class: ["badge", agotado ? "badge--danger" : p.stock_bajo ? "badge--warning" : "badge--plain"] },
        agotado ? "Agotado" : `${numero(p.stock_disponible - enCarrito)} disp.`),
      h("span", { class: "product-row__price" }, cop(p.precio_unitario)));
    }));
  }

  const buscarProductos = debounce(async () => {
    control?.abort();
    control = new AbortController();
    try {
      const r = await get("/productos", { buscar: busqueda.value.trim(), estado: "ACTIVO", page_size: 20 }, { signal: control.signal });
      productos = r.items;
      activo = productos.length ? 0 : -1;
      pintarResultados();
    } catch (e) { if (e?.codigo !== "CANCELADO") toastError(e); }
  }, 220);

  function mover(delta) {
    if (!productos.length) return;
    activo = (activo + delta + productos.length) % productos.length;
    pintarResultados();
    const el = resultados.querySelector(`#prod-${activo}`);
    busqueda.setAttribute("aria-activedescendant", el.id);
    el.scrollIntoView({ block: "nearest" });
  }

  function agregar(p) {
    const existente = borrador.items.find((it) => it.idproducto === p.idproducto);
    const actual = existente?.cantidad ?? 0;
    if (actual + 1 > p.stock_disponible) {
      toastError({ message: `No hay más unidades disponibles de “${p.nombre}”.` });
      return;
    }
    if (existente) { Object.assign(existente, resumenProducto(p)); existente.cantidad += 1; }
    else borrador.items.push({ ...resumenProducto(p), cantidad: 1 });
    guardar();
    pintarCarrito();
    pintarResultados();
  }

  busqueda.addEventListener("input", buscarProductos);
  busqueda.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); mover(1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mover(-1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (activo >= 0) { agregar(productos[activo]); busqueda.select(); }
    }
  });
  resultados.addEventListener("click", (e) => {
    const li = /** @type {HTMLElement} */ (e.target).closest("[data-indice]");
    if (!li || li.getAttribute("aria-disabled") === "true") return;
    activo = Number(li.dataset.indice);
    agregar(productos[activo]);
  });

  // ------------------------------------------------------------ cliente
  const cliente = combobox({
    placeholder: "Buscar cliente por nombre o documento…", minimo: 2,
    inicial: borrador.cliente,
    buscar: async (texto, signal) => (await get("/clientes", { buscar: texto, estado: "ACTIVO", page_size: 8 }, { signal })).items
      .map((c) => ({ valor: c.idcliente, etiqueta: nombreCliente(c), sub: `${documentoCliente(c)}${c.email ? ` · ${c.email}` : ""}` })),
    alElegir: (op) => { borrador.cliente = { valor: op.valor, etiqueta: op.etiqueta, sub: op.sub }; guardar(); pintarCliente(); },
  });
  cliente.input.setAttribute("aria-label", "Cliente");
  const zonaCliente = h("div");

  function pintarCliente() {
    if (borrador.cliente) {
      montar(zonaCliente, h("div", { class: "client-selected" },
        h("div", null, h("div", { class: "cell-main" }, borrador.cliente.etiqueta), h("div", { class: "cell-sub mono" }, borrador.cliente.sub || "")),
        h("button", { type: "button", class: "btn btn--ghost btn--sm", onclick: () => {
          borrador.cliente = null; cliente.fijar(null); guardar(); pintarCliente(); cliente.input.focus();
        } }, "Cambiar")));
    } else {
      montar(zonaCliente, h("div", { class: "row" },
        h("div", { class: "input-icon grow-1" }, icon("user", { size: 17 }), cliente.el),
        h("button", { type: "button", class: "btn btn--soft", onclick: crearClienteRapido }, icon("plus", { size: 16 }), "Cliente nuevo")));
    }
  }

  async function crearClienteRapido() {
    const c = await abrirFormularioCliente();
    if (c) {
      borrador.cliente = { valor: c.idcliente, etiqueta: nombreCliente(c), sub: documentoCliente(c) };
      guardar();
      pintarCliente();
    }
  }

  // ------------------------------------------------------------ carrito
  const lista = h("ul", { class: "cart-items", "aria-label": "Productos en la venta" });
  const totales = h("div", { class: "totals", "aria-live": "polite" });
  const confirmarBtn = h("button", { type: "button", class: "btn btn--primary btn--lg btn--block" });
  const errorStock = h("div");

  function pintarCarrito() {
    if (!borrador.items.length) {
      montar(lista, h("li", null, vacio({ icono: "pos", titulo: "Carrito vacío", texto: "Busca un producto y presiona Enter para agregarlo." })));
    } else {
      montar(lista, borrador.items.map((it, i) => {
        const lineaTotal = estimarTotales([it]).total;
        return h("li", { class: "cart-item", dataset: { indice: String(i) } },
          h("div", null,
            h("div", { class: "cart-item__name" }, it.nombre),
            h("div", { class: "cart-item__meta" }, `${cop(it.precio_unitario)} c/u · `, it.is_excluded ? "excluido" : `IVA ${Number(it.tax_rate)} %`,
              it.error && h("span", { class: "field__error" }, ` · ${it.error}`))),
          h("div", { class: "cart-item__total" }, cop(lineaTotal)),
          h("div", { class: "cart-item__controls" },
            h("div", { class: "qty" },
              h("button", { type: "button", dataset: { op: "menos" }, "aria-label": `Quitar una unidad de ${it.nombre}`, disabled: it.cantidad <= 1 }, icon("minus", { size: 14 })),
              h("input", { type: "number", inputmode: "numeric", min: "1", max: String(it.disponible), value: String(it.cantidad), dataset: { op: "cantidad" }, "aria-label": `Cantidad de ${it.nombre}` }),
              h("button", { type: "button", dataset: { op: "mas" }, "aria-label": `Agregar una unidad de ${it.nombre}`, disabled: it.cantidad >= it.disponible }, icon("plus", { size: 14 }))),
            h("span", { class: "cell-sub" }, `máx. ${numero(it.disponible)}`),
            h("button", { type: "button", class: "btn btn--ghost btn--icon btn--sm", dataset: { op: "quitar" }, "aria-label": `Quitar ${it.nombre}`, title: "Quitar" }, icon("trash", { size: 16 }))));
      }));
    }
    const t = estimarTotales(borrador.items);
    montar(totales,
      h("div", { class: "totals__row" }, h("span", null, "Subtotal"), h("span", null, cop(t.subtotal))),
      t.descuento > 0 && h("div", { class: "totals__row" }, h("span", null, "Descuentos"), h("span", null, `− ${cop(t.descuento)}`)),
      t.porTarifa.filter((g) => g.iva > 0).map((g) => h("div", { class: "totals__row" }, h("span", null, `IVA ${g.tarifa}`), h("span", null, cop(g.iva)))),
      h("div", { class: "totals__row totals__row--total" }, h("span", null, "Total estimado"), h("span", null, cop(t.total))),
      h("p", { class: "cell-sub" }, "El total definitivo lo calcula el servidor al confirmar."));
    const unidades = borrador.items.reduce((a, it) => a + it.cantidad, 0);
    montar(confirmarBtn, icon("check", { size: 18 }), unidades ? `Confirmar venta · ${cop(t.total)}` : "Confirmar venta");
  }

  lista.addEventListener("click", (e) => {
    const b = /** @type {HTMLElement} */ (e.target).closest("button[data-op]");
    if (!b) return;
    const i = Number(b.closest("[data-indice]").dataset.indice);
    const it = borrador.items[i];
    if (b.dataset.op === "mas" && it.cantidad < it.disponible) it.cantidad += 1;
    else if (b.dataset.op === "menos" && it.cantidad > 1) it.cantidad -= 1;
    else if (b.dataset.op === "quitar") borrador.items.splice(i, 1);
    delete it?.error;
    guardar();
    pintarCarrito();
    pintarResultados();
  });
  lista.addEventListener("change", (e) => {
    const input = /** @type {HTMLInputElement} */ (e.target);
    if (input.dataset.op !== "cantidad") return;
    const it = borrador.items[Number(input.closest("[data-indice]").dataset.indice)];
    const n = Math.floor(Number(input.value));
    it.cantidad = Math.min(Math.max(Number.isFinite(n) ? n : 1, 1), it.disponible);
    if (n > it.disponible) toastError({ message: `Solo hay ${it.disponible} unidades disponibles.` });
    guardar();
    pintarCarrito();
    pintarResultados();
  });

  // ------------------------------------------------------------ método de pago
  const iconosMetodo = { EFECTIVO: "cash", TRANSFERENCIA: "bank", TARJETA: "card" };
  const metodos = h("div", { class: "method-cards", role: "radiogroup", "aria-label": "Método de pago" },
    Object.entries(METODOS).map(([valor, texto]) => h("label", { class: "method-card" },
      h("input", { type: "radio", name: "metodo", value: valor, checked: borrador.metodo === valor }),
      icon(iconosMetodo[valor], { size: 22 }), texto)));
  const canal = h("select", { class: "select", "aria-label": "Canal de pago" });
  const zonaCanal = h("div", { class: "field" }, h("label", { class: "field__label", for: "pos-canal" }, "Canal"), canal);
  canal.id = "pos-canal";

  function pintarCanal() {
    const opciones = CANALES_METODO[borrador.metodo];
    zonaCanal.hidden = !opciones.length;
    montar(canal, opciones.map(([v, t]) => h("option", { value: v }, t)));
    canal.value = opciones.some(([v]) => v === borrador.canal) ? borrador.canal : "";
  }
  metodos.addEventListener("change", (e) => {
    borrador.metodo = /** @type {HTMLInputElement} */ (e.target).value;
    borrador.canal = "";
    guardar();
    pintarCanal();
  });
  canal.addEventListener("change", () => { borrador.canal = canal.value; guardar(); });

  // ------------------------------------------------------------ confirmar
  async function confirmarVenta() {
    errorStock.replaceChildren();
    if (!borrador.cliente) { toastError({ message: "Selecciona o crea el cliente." }); cliente.input?.focus(); return; }
    if (!borrador.items.length) { toastError({ message: "Agrega al menos un producto." }); busqueda.focus(); return; }
    const cuerpo = {
      idcliente: Number(borrador.cliente.valor),
      metodoPago: borrador.metodo,
      ...(borrador.canal ? { canal: borrador.canal } : {}),
      items: borrador.items.map((it) => ({ idproducto: it.idproducto, cantidad: it.cantidad })),
    };
    await conBotonOcupado(confirmarBtn, async () => {
      try {
        const venta = await post("/ventas", cuerpo, { headers: { "Idempotency-Key": borrador.clave } });
        storage.remove(STORAGE_KEYS.borradorVenta);
        exito(`Venta ${venta.referencia} creada por ${cop(venta.total)}.`, "Venta registrada");
        ctx.navegar(`/ventas/${venta.idventa}/pago`);
      } catch (err) {
        if (err.codigo === "STOCK_INSUFICIENTE" && Array.isArray(err.detalles)) {
          for (const d of err.detalles) {
            const it = borrador.items.find((x) => x.idproducto === d.idproducto);
            if (it && d.disponible !== undefined) {
              it.disponible = d.disponible;
              it.error = `solo quedan ${d.disponible}`;
            }
          }
          pintarCarrito();
          errorStock.replaceChildren(callout("danger", "Stock insuficiente", "Ajusta las cantidades marcadas y confirma de nuevo."));
        } else if (err.codigo === "RED" || err.codigo === "TIMEOUT") {
          // Se conserva la misma clave: reintentar no duplicará la venta.
          errorStock.replaceChildren(callout("warning", "Sin respuesta del servidor",
            "Vuelve a confirmar: si la venta ya se había creado, se recuperará la misma (no se duplica)."));
        } else {
          toastError(err, "No se pudo crear la venta");
        }
      }
    });
  }
  confirmarBtn.addEventListener("click", confirmarVenta);

  async function vaciar() {
    if (borrador.items.length && !(await confirmar({ titulo: "Vaciar venta", mensaje: "Se quitarán todos los productos y el cliente.", textoConfirmar: "Vaciar", peligro: true }))) return;
    borrador = borradorVacio();
    guardar({ cambioContenido: false });
    cliente.fijar(null);
    pintarTodo();
    busqueda.focus();
  }

  // Atajos: F2 buscar producto, F4 cliente, Ctrl+Enter confirmar.
  const atajos = (e) => {
    if (e.key === "F2") { e.preventDefault(); busqueda.focus(); busqueda.select(); }
    else if (e.key === "F4") { e.preventDefault(); if (!borrador.cliente) cliente.input.focus(); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); confirmarVenta(); }
  };
  document.addEventListener("keydown", atajos);
  ctx.alSalir(() => { document.removeEventListener("keydown", atajos); buscarProductos.cancel(); control?.abort(); });

  function pintarTodo() {
    pintarCliente();
    pintarCarrito();
    pintarCanal();
    metodos.querySelectorAll("input").forEach((r) => { /** @type {HTMLInputElement} */ (r).checked = r.value === borrador.metodo; });
  }

  ctx.root.append(
    encabezado("Nueva venta", null,
      h("span", { class: "cell-sub hide-mobile" }, h("span", { class: "kbd" }, "F2"), " producto · ", h("span", { class: "kbd" }, "F4"), " cliente · ",
        h("span", { class: "kbd" }, "Ctrl"), "+", h("span", { class: "kbd" }, "Enter"), " confirmar"),
      h("button", { type: "button", class: "btn", onclick: vaciar }, icon("trash", { size: 16 }), "Vaciar")),
    h("div", { class: "pos" },
      h("section", { class: "card", "aria-label": "Productos" },
        h("div", { class: "pos__search" }, h("div", { class: "input-icon" }, icon("search", { size: 19 }), busqueda)),
        resultados),
      h("section", { class: "card pos__cart", "aria-label": "Venta actual" },
        h("div", { class: "card__body stack" }, h("h2", { class: "card__title" }, "Cliente"), zonaCliente),
        h("div", { class: "card__header" }, h("h2", { class: "card__title" }, "Productos")),
        lista,
        h("div", { class: "card__body stack" }, totales,
          h("div", { class: "stack stack--sm" }, h("span", { class: "field__label" }, "Método de pago"), metodos), zonaCanal,
          errorStock, confirmarBtn))));

  pintarTodo();
  buscarProductos();
  busqueda.focus();
}
