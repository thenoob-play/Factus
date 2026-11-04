/** Listado de facturas con filtros; vista "facturas de un cliente" con ?idcliente=. */
import { get } from "../api.js";
import { METODOS } from "../config.js";
import { h } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { tablaDatos } from "../components/table.js";
import { badge, encabezado, vacio, tarjeta } from "../components/ui.js";
import { cop, fechaHora } from "../utils/format.js";
import { debounce } from "../utils/helpers.js";
import { filtroFechas, selectTrabajadores } from "./ventas.js";

const ESTADOS = [["EMITIDA", "Emitida"], ["FALLIDA", "Fallida"], ["PROCESANDO", "Emitiendo"], ["PENDIENTE", "Pendiente"], ["ANULADA", "Anulada"]];

export default async function paginaFacturas(ctx) {
  const idcliente = ctx.query.get("idcliente");
  let cliente = null;
  if (idcliente) cliente = await get(`/clientes/${idcliente}`, null, { signal: ctx.signal }).catch(() => null);

  const filtros = { buscar: "", estado: ctx.query.get("estado") ?? "", metodo_pago: "", idtrabajador: "", desde: "", hasta: "" };
  const buscar = h("input", { type: "search", class: "input", placeholder: "Documento, nombre del cliente o número", "aria-label": "Buscar facturas" });
  const estado = h("select", { class: "select", "aria-label": "Estado", value: filtros.estado },
    h("option", { value: "" }, "Todos los estados"), ESTADOS.map(([v, t]) => h("option", { value: v }, t)));
  const metodo = h("select", { class: "select", "aria-label": "Método de pago" },
    h("option", { value: "" }, "Todos los métodos"), Object.entries(METODOS).map(([v, t]) => h("option", { value: v }, t)));
  const fechas = filtroFechas("facturas");
  const trabajador = idcliente ? null : await selectTrabajadores(ctx.signal);

  const tabla = tablaDatos({
    etiqueta: "Facturas",
    clave: (f) => f.idfactura,
    columnas: [
      { clave: "numero", titulo: "Número", render: (f) => h("div", null, h("div", { class: "cell-main mono" }, f.numero || "Sin número"), h("div", { class: "cell-sub" }, fechaHora(f.creado_en))) },
      { clave: "cliente_nombre", titulo: "Cliente", render: (f) => (f.cliente_nombre
        ? h("div", null, h("div", null, f.cliente_nombre), h("div", { class: "cell-sub mono" }, f.cliente_identificacion)) : "—") },
      { clave: "metodo_pago", titulo: "Método", render: (f) => METODOS[f.metodo_pago] ?? "—" },
      { clave: "trabajador_nombre", titulo: "Atendió", render: (f) => f.trabajador_nombre ?? "—" },
      { clave: "total", titulo: "Total", num: true, render: (f) => h("strong", null, cop(f.total)) },
      { clave: "estado", titulo: "Estado", render: (f) => h("div", null, badge(f.estado), f.estado === "FALLIDA" && f.mensaje && h("div", { class: "cell-sub" }, f.mensaje.slice(0, 80))) },
    ],
    acciones: [{ accion: "ver", icono: "eye", etiqueta: "Ver factura" }],
    cargar: (p, signal) => (idcliente
      ? get(`/facturas/cliente/${idcliente}`, { page: p.page, page_size: p.page_size }, { signal })
      : get("/facturas", { page: p.page, page_size: p.page_size, ...filtros }, { signal })),
    alClic: (f) => ctx.navegar(`/facturas/${f.idfactura}`),
    alAccion: (_, f) => ctx.navegar(`/facturas/${f.idfactura}`),
    vacio: () => vacio({ icono: "invoice", titulo: "No hay facturas", texto: "Las facturas se emiten automáticamente al aprobarse cada pago." }),
  });

  const aplicar = debounce(() => {
    Object.assign(filtros, { buscar: buscar.value.trim(), estado: estado.value, metodo_pago: metodo.value,
      idtrabajador: trabajador?.value ?? "", desde: fechas.desde.value, hasta: fechas.hasta.value });
    tabla.recargar({ reiniciar: true });
  }, 300);
  buscar.addEventListener("input", aplicar);
  [estado, metodo, trabajador, fechas.desde, fechas.hasta].forEach((el) => el?.addEventListener("change", aplicar));
  ctx.alSalir(() => { aplicar.cancel(); tabla.abortar(); });

  const nombre = cliente ? cliente.names || cliente.company : null;
  ctx.root.append(
    encabezado(nombre ? `Facturas de ${nombre}` : "Facturas", nombre ? `Documento ${cliente.identification}` : "Facturas electrónicas emitidas a través de Factus.",
      idcliente && h("a", { class: "btn btn--ghost", href: "#/facturas" }, icon("x", { size: 16 }), "Quitar filtro de cliente")),
    tarjeta({ flush: true, cuerpo: [
      !idcliente && h("div", { class: "table-toolbar" },
        h("div", { class: "field grow" }, h("span", { class: "field__label" }, "Buscar"), h("div", { class: "input-icon" }, icon("search", { size: 17 }), buscar)),
        fechas.el,
        h("div", { class: "field" }, h("span", { class: "field__label" }, "Estado"), estado),
        h("div", { class: "field" }, h("span", { class: "field__label" }, "Método"), metodo),
        trabajador && h("div", { class: "field" }, h("span", { class: "field__label" }, "Trabajador"), trabajador)),
      tabla.el,
    ] }));
  tabla.recargar();
}
