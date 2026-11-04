/** Detalle de una venta: ítems, impuestos, pagos, línea de tiempo de estados y factura. */
import { get, post } from "../api.js";
import { METODOS, CANALES } from "../config.js";
import { h } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { badge, confirmar, encabezado, tarjeta, etiquetaEstado, vacio } from "../components/ui.js";
import { aviso, error as toastError } from "../components/toast.js";
import { cop, fechaHora, numero } from "../utils/format.js";

export default async function paginaVentaDetalle(ctx) {
  const v = await get(`/ventas/${ctx.params.id}`, null, { signal: ctx.signal });

  async function cancelar() {
    const motivo = await confirmar({ titulo: "Cancelar venta", mensaje: "Se anula el pago pendiente y se libera el stock reservado.", textoConfirmar: "Cancelar venta", peligro: true, pedirMotivo: true });
    if (!motivo) return;
    try {
      await post(`/ventas/${v.idventa}/cancelar`, { motivo });
      aviso("Venta cancelada.");
      ctx.navegar(`/ventas/${v.idventa}`);
    } catch (e) { toastError(e); }
  }

  const items = h("div", { class: "table-wrap" }, h("table", { class: "table table--cards", "aria-label": "Productos" },
    h("thead", null, h("tr", null, ["Producto", "Cant.", "Precio", "Desc.", "IVA", "Total"].map((t, i) => h("th", { class: i ? "num" : null }, t)))),
    h("tbody", null, v.items.map((it) => h("tr", null,
      h("td", { "data-label": "Producto" }, h("div", { class: "cell-main" }, it.nombre), h("div", { class: "cell-sub mono" }, it.code_reference)),
      h("td", { class: "num", "data-label": "Cant." }, numero(it.cantidad)),
      h("td", { class: "num", "data-label": "Precio" }, cop(it.precio_unitario)),
      h("td", { class: "num", "data-label": "Desc." }, Number(it.descuento) ? cop(it.descuento) : "—"),
      h("td", { class: "num", "data-label": "IVA" }, it.is_excluded ? "Excluido" : `${cop(it.iva)} (${Number(it.tax_rate)} %)`),
      h("td", { class: "num", "data-label": "Total" }, h("strong", null, cop(it.total))))))));

  const totales = h("div", { class: "totals" },
    h("div", { class: "totals__row" }, h("span", null, "Subtotal"), h("span", null, cop(v.subtotal))),
    Number(v.descuento_total) > 0 && h("div", { class: "totals__row" }, h("span", null, "Descuentos"), h("span", null, `− ${cop(v.descuento_total)}`)),
    h("div", { class: "totals__row" }, h("span", null, "Base gravable"), h("span", null, cop(v.base_gravable))),
    v.impuestos.map((g) => h("div", { class: "totals__row" },
      h("span", null, g.is_excluded ? "Excluido de IVA" : `IVA ${Number(g.tax_rate)} % · base ${cop(g.base)}`), h("span", null, cop(g.impuesto)))),
    h("div", { class: "totals__row totals__row--total" }, h("span", null, "Total"), h("span", null, cop(v.total))));

  const linea = h("ol", { class: "timeline" }, v.historial.map((e) => h("li", { class: "timeline__item" },
    h("span", { class: "timeline__dot", "aria-hidden": "true" }),
    h("div", { class: "timeline__title" }, e.estado_anterior && e.estado_anterior !== e.estado_nuevo
      ? [badge(e.estado_anterior), icon("chevronRight", { size: 14 }), badge(e.estado_nuevo)] : badge(e.estado_nuevo)),
    h("div", { class: "timeline__meta" }, fechaHora(e.creado_en), e.motivo ? ` · ${e.motivo}` : ""))));

  const pagos = v.pagos.length ? h("ul", { class: "list-plain" }, v.pagos.map((p) => h("li", null,
    h("div", null, h("div", { class: "cell-main mono" }, p.referencia),
      h("div", { class: "cell-sub" }, `${CANALES[p.canal] ?? p.canal} · ${fechaHora(p.creado_en)}${p.motivo_rechazo ? ` · ${p.motivo_rechazo}` : ""}`)),
    h("div", { class: "row" }, p.sospechoso && h("span", { class: "badge badge--danger", title: "Intento sospechoso" }, "Sospechoso"), cop(p.monto), badge(p.estado)))))
    : vacio({ icono: "wallet", titulo: "Sin pagos" });

  const factura = v.factura
    ? h("dl", { class: "dl" },
      h("dt", null, "Estado"), h("dd", null, badge(v.factura.estado)),
      h("dt", null, "Número"), h("dd", null, h("span", { class: "mono" }, v.factura.numero || "—")),
      v.factura.mensaje && [h("dt", null, "Mensaje"), h("dd", null, v.factura.mensaje)])
    : h("p", { class: "muted" }, v.estado === "PENDIENTE_PAGO" ? "Se emitirá al aprobarse el pago." : "Sin factura.");

  ctx.root.append(
    encabezado(`Venta ${v.referencia}`, `${METODOS[v.metodo_pago]} · ${fechaHora(v.creado_en)} · ${etiquetaEstado(v.estado)}`,
      h("a", { class: "btn btn--ghost", href: "#/ventas" }, icon("arrowLeft", { size: 16 }), "Ventas"),
      v.estado === "PENDIENTE_PAGO" && h("button", { type: "button", class: "btn", onclick: cancelar }, icon("ban", { size: 16 }), "Cancelar"),
      v.estado === "PENDIENTE_PAGO" && h("a", { class: "btn btn--primary", href: `#/ventas/${v.idventa}/pago` }, icon("wallet", { size: 16 }), "Ir al cobro"),
      ["PAGADA", "FACTURADA", "FACTURA_FALLIDA"].includes(v.estado) && h("a", { class: "btn", href: `#/ventas/${v.idventa}/pago` }, icon("receipt", { size: 16 }), "Comprobante"),
      v.factura?.idfactura && h("a", { class: "btn btn--primary", href: `#/facturas/${v.factura.idfactura}` }, icon("invoice", { size: 16 }), "Ver factura"),
      ["EXPIRADA", "CANCELADA"].includes(v.estado) && h("a", { class: "btn btn--primary", href: `#/ventas/nueva?repetir=${v.idventa}` }, icon("refresh", { size: 16 }), "Repetir venta")),
    h("div", { class: "grid grid--3" },
      h("div", { class: "span-2 stack" },
        tarjeta({ titulo: "Productos", flush: true, cuerpo: items }),
        tarjeta({ titulo: "Totales", cuerpo: totales })),
      h("div", { class: "stack" },
        tarjeta({ titulo: "Línea de tiempo", cuerpo: linea }),
        tarjeta({ titulo: "Pagos", flush: true, cuerpo: pagos }),
        tarjeta({ titulo: "Factura electrónica", cuerpo: factura }))));
}
