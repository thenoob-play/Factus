/** Listado de ventas con filtros por fecha, estado, método, trabajador y búsqueda. */
import { get } from "../api.js";
import { esAdmin } from "../auth.js";
import { METODOS } from "../config.js";
import { h } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { tablaDatos } from "../components/table.js";
import { badge, encabezado, vacio, tarjeta } from "../components/ui.js";
import { cop, fechaHora } from "../utils/format.js";
import { debounce } from "../utils/helpers.js";

export const ESTADOS_VENTA = [["PENDIENTE_PAGO", "Pendiente de pago"], ["PAGADA", "Pagada"], ["FACTURADA", "Facturada"],
  ["FACTURA_FALLIDA", "Factura fallida"], ["EXPIRADA", "Expirada"], ["CANCELADA", "Cancelada"]];

/** Select de trabajadores (solo ADMIN puede listarlos). */
export async function selectTrabajadores(signal) {
  const select = h("select", { class: "select", "aria-label": "Trabajador" }, h("option", { value: "" }, "Todos los trabajadores"));
  if (!esAdmin()) return null;
  try {
    const r = await get("/trabajadores", { page_size: 100 }, { signal });
    r.items.forEach((t) => select.append(h("option", { value: String(t.idtrabajador) }, t.nombre)));
  } catch { /* sin permisos o sin conexión: se oculta el filtro */ return null; }
  return select;
}

export function filtroFechas(prefijo) {
  const desde = h("input", { type: "date", class: "input", id: `${prefijo}-desde` });
  const hasta = h("input", { type: "date", class: "input", id: `${prefijo}-hasta` });
  return {
    desde, hasta,
    el: [
      h("div", { class: "field" }, h("label", { class: "field__label", for: desde.id }, "Desde"), desde),
      h("div", { class: "field" }, h("label", { class: "field__label", for: hasta.id }, "Hasta"), hasta),
    ],
  };
}

export default async function paginaVentas(ctx) {
  const filtros = { buscar: "", estado: ctx.query.get("estado") ?? "", metodo_pago: "", idtrabajador: "", desde: "", hasta: "" };
  const buscar = h("input", { type: "search", class: "input", placeholder: "Referencia, documento o cliente", "aria-label": "Buscar ventas" });
  const estado = h("select", { class: "select", "aria-label": "Estado", value: filtros.estado },
    h("option", { value: "" }, "Todos los estados"), ESTADOS_VENTA.map(([v, t]) => h("option", { value: v }, t)));
  const metodo = h("select", { class: "select", "aria-label": "Método de pago" },
    h("option", { value: "" }, "Todos los métodos"), Object.entries(METODOS).map(([v, t]) => h("option", { value: v }, t)));
  const fechas = filtroFechas("ventas");
  const trabajador = await selectTrabajadores(ctx.signal);

  const tabla = tablaDatos({
    etiqueta: "Ventas",
    clave: (f) => f.idventa,
    columnas: [
      { clave: "referencia", titulo: "Referencia", render: (f) => h("div", null, h("div", { class: "cell-main mono" }, f.referencia), h("div", { class: "cell-sub" }, fechaHora(f.creado_en))) },
      { clave: "cliente_nombre", titulo: "Cliente" },
      { clave: "metodo_pago", titulo: "Método", render: (f) => METODOS[f.metodo_pago] },
      { clave: "trabajador_nombre", titulo: "Atendió" },
      { clave: "total", titulo: "Total", num: true, render: (f) => h("strong", null, cop(f.total)) },
      { clave: "estado", titulo: "Estado", render: (f) => badge(f.estado) },
    ],
    acciones: [
      { accion: "cobrar", icono: "wallet", etiqueta: "Ir al cobro", visible: (f) => f.estado === "PENDIENTE_PAGO" },
      { accion: "ver", icono: "eye", etiqueta: "Ver detalle" },
    ],
    cargar: (p, signal) => get("/ventas", { page: p.page, page_size: p.page_size, ...filtros }, { signal }),
    alClic: (f) => ctx.navegar(`/ventas/${f.idventa}`),
    alAccion: (accion, f) => ctx.navegar(accion === "cobrar" ? `/ventas/${f.idventa}/pago` : `/ventas/${f.idventa}`),
    vacio: () => vacio({ icono: "receipt", titulo: "No hay ventas", texto: "No hay ventas con esos filtros.",
      accion: h("a", { class: "btn btn--primary", href: "#/ventas/nueva" }, icon("plus", { size: 16 }), "Nueva venta") }),
  });

  const aplicar = debounce(() => {
    Object.assign(filtros, {
      buscar: buscar.value.trim(), estado: estado.value, metodo_pago: metodo.value,
      idtrabajador: trabajador?.value ?? "", desde: fechas.desde.value, hasta: fechas.hasta.value,
    });
    tabla.recargar({ reiniciar: true });
  }, 300);
  buscar.addEventListener("input", aplicar);
  [estado, metodo, trabajador, fechas.desde, fechas.hasta].forEach((el) => el?.addEventListener("change", aplicar));
  ctx.alSalir(() => { aplicar.cancel(); tabla.abortar(); });

  ctx.root.append(
    encabezado("Ventas", "Historial de ventas y su estado de pago y facturación.",
      h("a", { class: "btn btn--primary", href: "#/ventas/nueva" }, icon("plus", { size: 16 }), "Nueva venta")),
    tarjeta({ flush: true, cuerpo: [
      h("div", { class: "table-toolbar" },
        h("div", { class: "field grow" }, h("span", { class: "field__label" }, "Buscar"), h("div", { class: "input-icon" }, icon("search", { size: 17 }), buscar)),
        fechas.el,
        h("div", { class: "field" }, h("span", { class: "field__label" }, "Estado"), estado),
        h("div", { class: "field" }, h("span", { class: "field__label" }, "Método"), metodo),
        trabajador && h("div", { class: "field" }, h("span", { class: "field__label" }, "Trabajador"), trabajador)),
      tabla.el,
    ] }));
  tabla.recargar();
}
