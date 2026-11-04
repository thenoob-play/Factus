/** Caja: apertura con base, movimientos en efectivo, cierre con arqueo e historial. */
import { get, post } from "../api.js";
import { h, montar, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { tablaDatos } from "../components/table.js";
import { campo, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { badge, encabezado, tarjeta, vacio } from "../components/ui.js";
import { exito } from "../components/toast.js";
import { cop, fechaHora } from "../utils/format.js";

function claseDiferencia(d) {
  return `diff ${Number(d) === 0 ? "diff--ok" : "diff--bad"}`;
}

export default async function paginaCaja(ctx) {
  const zonaActual = h("div");
  const historial = tablaDatos({
    etiqueta: "Historial de cajas",
    clave: (f) => f.idcaja,
    columnas: [
      { clave: "abierta_en", titulo: "Apertura", render: (f) => fechaHora(f.abierta_en) },
      { clave: "cerrada_en", titulo: "Cierre", render: (f) => fechaHora(f.cerrada_en) },
      { clave: "base_inicial", titulo: "Base", num: true, render: (f) => cop(f.base_inicial) },
      { clave: "efectivo_esperado", titulo: "Esperado", num: true, render: (f) => (f.efectivo_esperado == null ? "—" : cop(f.efectivo_esperado)) },
      { clave: "efectivo_contado", titulo: "Contado", num: true, render: (f) => (f.efectivo_contado == null ? "—" : cop(f.efectivo_contado)) },
      { clave: "diferencia", titulo: "Diferencia", num: true, render: (f) => (f.diferencia == null ? "—" : h("span", { class: claseDiferencia(f.diferencia) }, cop(f.diferencia))) },
      { clave: "estado", titulo: "Estado", render: (f) => badge(f.estado) },
    ],
    cargar: (p, signal) => get("/cajas", { page: p.page, page_size: p.page_size }, { signal }),
    vacio: () => vacio({ icono: "wallet", titulo: "Sin cierres todavía" }),
  });
  ctx.alSalir(() => historial.abortar());

  async function pintarActual() {
    const caja = await get("/cajas/actual", null, { signal: ctx.signal });
    if (!caja) {
      const base = h("input", { type: "number", class: "input input--lg num", min: "0", step: "100", value: "0", id: "base-inicial", inputmode: "decimal" });
      const abrir = h("button", { type: "button", class: "btn btn--primary btn--lg" }, icon("wallet", { size: 18 }), "Abrir caja");
      abrir.addEventListener("click", () => conBotonOcupado(abrir, async () => {
        try {
          await post("/cajas/abrir", { base_inicial: Number(base.value || 0).toFixed(2) });
          exito("Caja abierta.");
          pintarActual();
          historial.recargar();
        } catch (e) { mostrarErrorApi(zonaActual.querySelector("form") ?? zonaActual, e); }
      }));
      montar(zonaActual, tarjeta({ titulo: "Tu caja está cerrada", cuerpo: h("form", { class: "form", onsubmit: (e) => { e.preventDefault(); abrir.click(); } },
        h("p", { class: "text-2" }, "Abre la caja con el efectivo con el que empiezas el turno. Los pagos en efectivo quedan asociados a ella."),
        h("div", { class: "field" }, h("label", { class: "field__label", for: "base-inicial" }, "Base inicial"), base),
        h("div", null, abrir)) }));
      base.focus();
      return;
    }

    const movimientos = caja.movimientos.length
      ? h("div", { class: "table-wrap" }, h("table", { class: "table table--cards", "aria-label": "Movimientos en efectivo" },
        h("thead", null, h("tr", null, h("th", null, "Venta"), h("th", null, "Hora"), h("th", { class: "num" }, "Total"), h("th", { class: "num" }, "Recibido"), h("th", { class: "num" }, "Cambio"))),
        h("tbody", null, caja.movimientos.map((m) => h("tr", null,
          h("td", { "data-label": "Venta" }, h("a", { href: `#/ventas/${m.idventa}`, class: "mono" }, m.referencia)),
          h("td", { "data-label": "Hora" }, fechaHora(m.fecha)),
          h("td", { class: "num", "data-label": "Total" }, h("strong", null, cop(m.monto))),
          h("td", { class: "num", "data-label": "Recibido" }, cop(m.recibido)),
          h("td", { class: "num", "data-label": "Cambio" }, cop(m.cambio)))))))
      : vacio({ icono: "cash", titulo: "Sin ventas en efectivo", texto: "Los cobros en efectivo de este turno aparecerán aquí." });

    const cerrar = h("button", { type: "button", class: "btn btn--primary" }, icon("check", { size: 16 }), "Cerrar caja");
    cerrar.addEventListener("click", () => cerrarCaja(caja));
    montar(zonaActual, h("div", { class: "stack" },
      h("div", { class: "grid grid--kpi" },
        kpi("Base inicial", cop(caja.base_inicial), "wallet"),
        kpi("Ventas en efectivo", cop(caja.ventas_efectivo), "cash", `${caja.movimientos.length} cobros`),
        kpi("Efectivo esperado", cop(caja.efectivo_esperado_actual), "check", `Abierta ${fechaHora(caja.abierta_en)}`)),
      tarjeta({ titulo: "Movimientos del turno", acciones: cerrar, flush: true, cuerpo: movimientos })));
  }

  function kpi(etiqueta, valor, icono, meta) {
    return h("div", { class: "card kpi" },
      h("div", { class: "kpi__label" }, h("span", { class: "kpi__icon" }, icon(icono, { size: 16 })), etiqueta),
      h("div", { class: "kpi__value" }, valor), meta && h("div", { class: "kpi__meta" }, meta));
  }

  function cerrarCaja(caja) {
    const esperado = Number(caja.efectivo_esperado_actual);
    const contado = h("input", { type: "number", class: "input input--lg num", min: "0", step: "50", id: "contado", inputmode: "decimal" });
    const diferencia = h("p", { "aria-live": "polite" });
    const observacion = h("textarea", { class: "textarea", id: "obs", maxlength: "255" });
    const actualizar = () => {
      if (contado.value === "") { diferencia.replaceChildren(); return; }
      const d = Number(contado.value) - esperado;
      diferencia.replaceChildren("Diferencia: ", h("span", { class: claseDiferencia(d) }, `${d > 0 ? "+" : ""}${cop(d)}`),
        d === 0 ? " · cuadra" : d > 0 ? " · sobrante" : " · faltante");
    };
    contado.addEventListener("input", actualizar);
    const form = h("form", { class: "form", id: "form-cierre", novalidate: true },
      h("dl", { class: "dl" }, h("dt", null, "Efectivo esperado"), h("dd", null, h("strong", null, cop(esperado)))),
      h("div", { class: "field", dataset: { campo: "efectivo_contado" } }, h("label", { class: "field__label", for: "contado" }, "Efectivo contado"), contado, h("p", { class: "field__error" })),
      diferencia,
      h("div", { class: "field" }, h("label", { class: "field__label", for: "obs" }, "Observación"), observacion));
    const confirmarBtn = h("button", { type: "submit", class: "btn btn--primary", form: "form-cierre" }, "Cerrar caja");
    const modal = abrirModal({ titulo: "Arqueo y cierre de caja", contenido: form, acciones: [confirmarBtn] });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      limpiarErrores(form);
      if (mostrarErrores(form, contado.value === "" || Number(contado.value) < 0 ? { efectivo_contado: "Escribe el efectivo contado." } : {})) return;
      conBotonOcupado(confirmarBtn, async () => {
        try {
          const r = await post("/cajas/cerrar", { efectivo_contado: Number(contado.value).toFixed(2), observacion: observacion.value.trim() || null });
          modal.cerrar();
          exito(`Caja cerrada. Diferencia: ${cop(r.diferencia)}.`);
          pintarActual();
          historial.recargar();
        } catch (err) { mostrarErrorApi(form, err); }
      });
    });
  }

  ctx.root.append(
    encabezado("Caja", "Efectivo del turno y arqueo."),
    h("div", { class: "stack" }, zonaActual, tarjeta({ titulo: "Historial", flush: true, cuerpo: historial.el })));
  await pintarActual();
  historial.recargar();
}
