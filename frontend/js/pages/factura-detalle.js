/** Detalle de factura: CUFE, QR de la DIAN, cliente, ítems, impuestos, pago y acciones. */
import { get, post } from "../api.js";
import { CATALOGOS, CANALES, CONFIG, METODOS } from "../config.js";
import { h, montar, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { qrDesdeTexto } from "../components/qr.js";
import { badge, botonCopiar, callout, copiable, encabezado, tarjeta, vacio } from "../components/ui.js";
import { campo, errorGeneral, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { exito, error as toastError } from "../components/toast.js";
import { cop, fechaHora, numero } from "../utils/format.js";
import { descargarDocumento, enviarPorEmail, listaErrores, reintentarFactura, verPdf } from "./acciones-factura.js";
import { nombreCliente, documentoCliente } from "./clientes.js";

function abrirNotaCredito(f, alTerminar) {
  const vendidas = new Map(f.items.map((it) => [it.idproducto, it.cantidad]));
  const devueltas = new Map();
  for (const n of f.notas_credito) {
    if (n.estado === "FALLIDA") continue;
    for (const it of n.items ?? []) devueltas.set(it.idproducto, (devueltas.get(it.idproducto) ?? 0) + it.cantidad);
  }
  const concepto = campo({ nombre: "correction_concept_code", etiqueta: "Concepto", tipo: "select", opciones: CATALOGOS.conceptosNota });
  const motivo = campo({ nombre: "motivo", etiqueta: "Motivo", tipo: "textarea", requerido: true, attrs: { maxlength: "500" } });
  const restaurar = h("input", { type: "checkbox", name: "restaurar_stock", checked: true });
  const filas = f.items.map((it) => {
    const disponible = vendidas.get(it.idproducto) - (devueltas.get(it.idproducto) ?? 0);
    return { it, disponible, input: h("input", { type: "number", class: "input", min: "0", max: String(disponible), value: String(disponible), step: "1", disabled: disponible <= 0, "aria-label": `Unidades a acreditar de ${it.nombre}` }) };
  });
  const tablaItems = h("div", { class: "table-wrap" }, h("table", { class: "table" },
    h("thead", null, h("tr", null, h("th", null, "Producto"), h("th", { class: "num" }, "Disponibles"), h("th", { class: "num" }, "A acreditar"))),
    h("tbody", null, filas.map(({ it, disponible, input }) => h("tr", null, h("td", null, it.nombre), h("td", { class: "num" }, numero(disponible)), h("td", { class: "num" }, input))))));
  const zonaItems = h("div", { class: "stack stack--sm" }, h("span", { class: "field__label" }, "Unidades a acreditar"), tablaItems);

  const form = h("form", { class: "form", novalidate: true, id: "form-nota" },
    callout("warning", "Acción con efecto fiscal", "La nota crédito se envía a la DIAN y no se puede deshacer."),
    concepto, zonaItems, motivo, h("label", { class: "check" }, restaurar, "Devolver las unidades al inventario"));
  const selConcepto = /** @type {HTMLSelectElement} */ (concepto.querySelector("select"));
  const sincronizar = () => { zonaItems.hidden = selConcepto.value === "2"; };
  selConcepto.addEventListener("change", sincronizar);
  sincronizar();

  const emitir = h("button", { type: "submit", class: "btn btn--danger", form: "form-nota" }, "Emitir nota crédito");
  const modal = abrirModal({ titulo: `Nota crédito · ${f.numero}`, contenido: form, acciones: [emitir], tamano: "lg" });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const texto = /** @type {HTMLTextAreaElement} */ (motivo.querySelector("textarea")).value.trim();
    if (mostrarErrores(form, texto.length < 5 ? { motivo: "Describe el motivo (mínimo 5 caracteres)." } : {})) return;
    let items = null;
    if (selConcepto.value !== "2") {
      items = filas.map(({ it, input, disponible }) => ({ idproducto: it.idproducto, cantidad: Math.min(Math.max(Math.floor(Number(input.value) || 0), 0), disponible) }))
        .filter((x) => x.cantidad > 0);
      if (!items.length) { errorGeneral(form, "Indica al menos una unidad a acreditar."); return; }
    }
    conBotonOcupado(emitir, async () => {
      try {
        const nota = await post(`/facturas/${f.idfactura}/nota-credito`, {
          correction_concept_code: selConcepto.value, motivo: texto, items, restaurar_stock: restaurar.checked,
        }, { timeout: CONFIG.TIMEOUT_FACTUS_MS });
        exito(`Nota crédito ${nota.numero ?? ""} emitida.`);
        modal.cerrar();
        alTerminar();
      } catch (err) {
        if (!mostrarErrorApi(form, err)) errorGeneral(form, err?.message || "No se pudo emitir la nota crédito.");
        if (err.detalles?.idnota) alTerminar(); // la nota quedó registrada (fallida o pendiente)
      }
    });
  });
}

export default async function paginaFacturaDetalle(ctx) {
  const f = await get(`/facturas/${ctx.params.id}`, null, { signal: ctx.signal });
  const venta = await get(`/ventas/${f.idventa}`, null, { signal: ctx.signal });
  const pago = venta.pagos.find((p) => p.estado === "APROBADO");
  const recargar = () => ctx.navegar(`/facturas/${f.idfactura}`);
  const emitida = f.estado === "EMITIDA" || f.estado === "ANULADA";

  const botones = [];
  if (emitida) {
    const ver = h("button", { type: "button", class: "btn" }, icon("eye", { size: 16 }), "Ver PDF");
    ver.addEventListener("click", () => verPdf(f.idfactura, ver));
    const pdf = h("button", { type: "button", class: "btn" }, icon("download", { size: 16 }), "PDF");
    pdf.addEventListener("click", () => descargarDocumento(f.idfactura, "pdf", pdf));
    const xml = h("button", { type: "button", class: "btn" }, icon("download", { size: 16 }), "XML");
    xml.addEventListener("click", () => descargarDocumento(f.idfactura, "xml", xml));
    botones.push(ver, pdf, xml,
      h("button", { type: "button", class: "btn", onclick: () => enviarPorEmail(f.idfactura, f.cliente?.email) }, icon("mail", { size: 16 }), "Enviar por email"));
    if (f.estado === "EMITIDA") botones.push(h("button", { type: "button", class: "btn btn--danger", onclick: () => abrirNotaCredito(f, recargar) }, icon("undo", { size: 16 }), "Nota crédito"));
  }
  if (f.estado === "FALLIDA") {
    const r = h("button", { type: "button", class: "btn btn--primary" }, icon("refresh", { size: 16 }), "Reintentar emisión");
    r.addEventListener("click", async () => { if (await reintentarFactura(f.idfactura, r)) recargar(); });
    botones.push(r);
  }

  const qr = h("div");
  if (f.qr_url) qrDesdeTexto(f.qr_url, "Código QR de validación DIAN").then((img) => montar(qr, img)).catch(() => montar(qr, h("a", { href: f.qr_url, target: "_blank", rel: "noopener noreferrer" }, "Validar en la DIAN")));

  const cabecera = h("div", { class: "grid grid--3" },
    h("div", { class: "span-2 stack" },
      h("dl", { class: "dl" },
        h("dt", null, "Número"), h("dd", null, h("span", { class: "mono" }, f.numero || "—")),
        h("dt", null, "Prefijo"), h("dd", null, f.prefijo || "—"),
        h("dt", null, "Referencia"), h("dd", null, copiable(f.reference_code)),
        h("dt", null, "Estado"), h("dd", null, badge(f.estado), f.is_validated ? h("span", { class: "badge badge--success", title: "Validada por la DIAN" }, "DIAN ✓") : null),
        h("dt", null, "Emitida"), h("dd", null, fechaHora(f.validated_at || f.creado_en)),
        h("dt", null, "Intentos"), h("dd", null, numero(f.intentos))),
      f.cufe && h("div", { class: "stack stack--sm" }, h("span", { class: "field__label" }, "CUFE"),
        h("div", { class: "row" }, h("code", { class: "cufe grow-1" }, f.cufe), botonCopiar(f.cufe, "Copiar CUFE"))),
      f.public_url && h("a", { href: f.public_url, target: "_blank", rel: "noopener noreferrer" }, icon("external", { size: 15 }), " Representación gráfica en Factus")),
    h("div", { class: "qr-panel" }, qr, f.qr_url && h("span", { class: "cell-sub" }, "Escanéalo para validar en la DIAN")));

  const c = f.cliente;
  const clienteCard = c ? h("dl", { class: "dl" },
    h("dt", null, "Nombre"), h("dd", null, nombreCliente(c)),
    h("dt", null, "Documento"), h("dd", null, h("span", { class: "mono" }, documentoCliente(c))),
    h("dt", null, "Correo"), h("dd", null, c.email || "—"),
    h("dt", null, "Dirección"), h("dd", null, c.address || "—")) : h("p", { class: "muted" }, "—");

  const items = h("div", { class: "table-wrap" }, h("table", { class: "table table--cards" },
    h("thead", null, h("tr", null, ["Producto", "Cant.", "Precio", "IVA", "Total"].map((t, i) => h("th", { class: i ? "num" : null }, t)))),
    h("tbody", null, f.items.map((it) => h("tr", null,
      h("td", { "data-label": "Producto" }, h("div", { class: "cell-main" }, it.nombre), h("div", { class: "cell-sub mono" }, it.code_reference)),
      h("td", { class: "num", "data-label": "Cant." }, numero(it.cantidad)),
      h("td", { class: "num", "data-label": "Precio" }, cop(it.precio_unitario)),
      h("td", { class: "num", "data-label": "IVA" }, it.is_excluded ? "Excluido" : `${Number(it.tax_rate)} % · ${cop(it.iva)}`),
      h("td", { class: "num", "data-label": "Total" }, h("strong", null, cop(it.total))))))));

  const totales = h("div", { class: "totals" },
    h("div", { class: "totals__row" }, h("span", null, "Subtotal"), h("span", null, cop(venta.subtotal))),
    Number(venta.descuento_total) > 0 && h("div", { class: "totals__row" }, h("span", null, "Descuentos"), h("span", null, `− ${cop(venta.descuento_total)}`)),
    venta.impuestos.map((g) => h("div", { class: "totals__row" }, h("span", null, g.is_excluded ? "Excluido" : `IVA ${Number(g.tax_rate)} % · base ${cop(g.base)}`), h("span", null, cop(g.impuesto)))),
    h("div", { class: "totals__row totals__row--total" }, h("span", null, "Total"), h("span", null, cop(f.total))));

  const pagoCard = pago ? h("dl", { class: "dl" },
    h("dt", null, "Método"), h("dd", null, `${METODOS[pago.metodo]} · ${CANALES[pago.canal] ?? pago.canal}`),
    h("dt", null, "Referencia"), h("dd", null, h("span", { class: "mono" }, pago.referencia)),
    h("dt", null, "Aprobado"), h("dd", null, fechaHora(pago.verificado_en)),
    pago.proveedor_transaccion_id && [h("dt", null, "Transacción"), h("dd", null, h("span", { class: "mono" }, pago.proveedor_transaccion_id))],
    pago.comprobante_numero && [h("dt", null, "Comprobante"), h("dd", null, h("span", { class: "mono" }, pago.comprobante_numero))],
    pago.codigo_autorizacion && [h("dt", null, "Aprobación"), h("dd", null, h("span", { class: "mono" }, pago.codigo_autorizacion))],
    pago.tarjeta_ultimos4 && [h("dt", null, "Tarjeta"), h("dd", null, `${pago.tarjeta_franquicia ?? ""} •••• ${pago.tarjeta_ultimos4}`)],
    h("dt", null, "Código DIAN"), h("dd", null, h("span", { class: "mono" }, f.payment_method_code || "—"))) : h("p", { class: "muted" }, "Sin pago aprobado.");

  const notas = f.notas_credito.length ? h("ul", { class: "list-plain" }, f.notas_credito.map((n) => h("li", null,
    h("div", null, h("div", { class: "cell-main mono" }, n.numero || n.reference_code), h("div", { class: "cell-sub" }, `${fechaHora(n.creado_en)} · ${n.motivo}`)),
    h("div", { class: "row" }, cop(n.total), badge(n.estado),
      n.estado === "PENDIENTE" && h("button", { type: "button", class: "btn btn--sm", onclick: async (e) => {
        await conBotonOcupado(e.currentTarget, async () => {
          try { await post(`/facturas/notas-credito/${n.idnota}/reintentar`, {}, { timeout: CONFIG.TIMEOUT_FACTUS_MS }); exito("Nota crédito emitida."); } catch (err) { toastError(err, "La nota crédito sigue pendiente"); }
          recargar();
        });
      } }, "Reintentar")))))
    : vacio({ icono: "undo", titulo: "Sin notas crédito" });

  ctx.root.append(
    encabezado(`Factura ${f.numero || f.reference_code}`, `Venta ${venta.referencia}`,
      h("a", { class: "btn btn--ghost", href: "#/facturas" }, icon("arrowLeft", { size: 16 }), "Facturas"),
      h("a", { class: "btn btn--ghost", href: `#/ventas/${f.idventa}` }, "Ver venta"), ...botones),
    h("div", { class: "stack" },
      f.estado === "FALLIDA" && callout("danger", "Factus/DIAN rechazó la factura", f.mensaje || "", listaErrores(f.errores)),
      tarjeta({ cuerpo: cabecera }),
      h("div", { class: "grid grid--3" },
        h("div", { class: "span-2 stack" }, tarjeta({ titulo: "Productos", flush: true, cuerpo: items }), tarjeta({ titulo: "Totales", cuerpo: totales })),
        h("div", { class: "stack" }, tarjeta({ titulo: "Cliente", cuerpo: clienteCard }), tarjeta({ titulo: "Pago", cuerpo: pagoCard }),
          tarjeta({ titulo: "Notas crédito", flush: true, cuerpo: notas })))));
}
