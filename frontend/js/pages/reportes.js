/** Reportes (ADMIN): totales por rango y método de pago; exportación CSV del backend. */
import { descargar, get, post } from "../api.js";
import { METODOS } from "../config.js";
import { h, montar, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { badge, callout, encabezado, skeleton, tarjeta, vacio } from "../components/ui.js";
import { exito, error as toastError } from "../components/toast.js";
import { cop, diaCorto, fechaHora, isoDiaLocal, numero } from "../utils/format.js";
import { guardarBlob } from "../utils/helpers.js";
import { grafico } from "./graficos.js";

export default async function paginaReportes(ctx) {
  const hoy = new Date();
  const desde = h("input", { type: "date", class: "input", id: "rep-desde", value: isoDiaLocal(new Date(hoy.getFullYear(), hoy.getMonth(), 1)) });
  const hasta = h("input", { type: "date", class: "input", id: "rep-hasta", value: isoDiaLocal(hoy) });
  const consultar = h("button", { type: "submit", class: "btn btn--primary" }, icon("filter", { size: 16 }), "Consultar");
  const resultado = h("div", { class: "stack" });
  let destruir = [];

  async function cargar() {
    destruir.forEach((fn) => fn?.());
    destruir = [];
    if (!desde.value || !hasta.value || desde.value > hasta.value) {
      montar(resultado, callout("warning", "Rango no válido", "La fecha inicial debe ser anterior o igual a la final."));
      return;
    }
    montar(resultado, tarjeta({ cuerpo: skeleton(6) }));
    const r = await get("/reportes/resumen", { desde: desde.value, hasta: hasta.value }, { signal: ctx.signal });
    const facturas = Object.entries(r.facturas);
    const lineaDias = h("div");
    const barras = h("div");
    montar(resultado,
      h("div", { class: "grid grid--kpi" },
        h("div", { class: "card kpi" }, h("div", { class: "kpi__label" }, "Total vendido"), h("div", { class: "kpi__value" }, cop(r.ventas.total)), h("div", { class: "kpi__meta" }, `${numero(r.ventas.cantidad)} ventas pagadas`)),
        h("div", { class: "card kpi" }, h("div", { class: "kpi__label" }, "Ticket promedio"), h("div", { class: "kpi__value" }, cop(r.ventas.cantidad ? Number(r.ventas.total) / r.ventas.cantidad : 0))),
        h("div", { class: "card kpi" }, h("div", { class: "kpi__label" }, "Facturas"), h("div", { class: "kpi__value" }, numero(facturas.reduce((a, [, n]) => a + n, 0))),
          h("div", { class: "row" }, facturas.map(([estado, n]) => badge(estado, `${n} ${estado.toLowerCase()}`))))),
      h("div", { class: "grid grid--2" },
        tarjeta({ titulo: "Totales por método de pago", flush: true, cuerpo: r.por_metodo.length
          ? h("div", { class: "table-wrap" }, h("table", { class: "table" },
            h("thead", null, h("tr", null, h("th", null, "Método"), h("th", { class: "num" }, "Ventas"), h("th", { class: "num" }, "Total"), h("th", { class: "num" }, "%"))),
            h("tbody", null, r.por_metodo.map((m) => h("tr", null, h("td", null, METODOS[m.metodo_pago]), h("td", { class: "num" }, numero(m.cantidad)),
              h("td", { class: "num" }, h("strong", null, cop(m.total))),
              h("td", { class: "num" }, `${numero(Number(r.ventas.total) ? (Number(m.total) * 100) / Number(r.ventas.total) : 0)} %`))))))
          : vacio({ icono: "wallet", titulo: "Sin ventas en el rango" }) }),
        tarjeta({ titulo: "Distribución", cuerpo: barras })),
      tarjeta({ titulo: "Ventas por día", cuerpo: lineaDias }),
      tarjeta({ titulo: "Más vendidos", flush: true, cuerpo: r.mas_vendidos.length
        ? h("ul", { class: "list-plain" }, r.mas_vendidos.map((p, i) => h("li", null,
          h("div", { class: "row" }, h("span", { class: "rank" }, String(i + 1)), h("span", { class: "cell-main" }, p.nombre)),
          h("span", { class: "text-2" }, `${numero(p.unidades)} u · ${cop(p.total)}`))))
        : vacio({ icono: "chart", titulo: "Sin datos" }) }));
    if (r.por_metodo.length) {
      destruir.push(await grafico(barras, "barras", { etiquetas: r.por_metodo.map((m) => METODOS[m.metodo_pago]), valores: r.por_metodo.map((m) => Number(m.total)), nombre: "Total por método" }).catch(() => null));
    } else montar(barras, vacio({ icono: "chart", titulo: "Sin datos" }));
    if (r.por_dia.length) {
      destruir.push(await grafico(lineaDias, "linea", { etiquetas: r.por_dia.map((d) => diaCorto(String(d.dia).slice(0, 10))), valores: r.por_dia.map((d) => Number(d.total)), nombre: "Ventas por día" }).catch(() => null));
    } else montar(lineaDias, vacio({ icono: "chart", titulo: "Sin ventas en el rango" }));
  }

  async function exportar(tipo, boton) {
    await conBotonOcupado(boton, async () => {
      try {
        const { blob, nombre } = await descargar(`/reportes/${tipo}.csv`, { desde: desde.value, hasta: hasta.value }, { nombreArchivo: `${tipo}.csv` });
        guardarBlob(blob, nombre);
      } catch (e) { toastError(e, "No se pudo exportar"); }
    });
  }

  const btnVentas = h("button", { type: "button", class: "btn" }, icon("download", { size: 16 }), "Ventas CSV");
  btnVentas.addEventListener("click", () => exportar("ventas", btnVentas));
  const btnFacturas = h("button", { type: "button", class: "btn" }, icon("download", { size: 16 }), "Facturas CSV");
  btnFacturas.addEventListener("click", () => exportar("facturas", btnFacturas));

  // Catálogos de Factus (necesarios para validar municipios y unidades de medida).
  const estadoCatalogos = h("div", { class: "card__body" }, skeleton(2));
  const refrescar = h("button", { type: "button", class: "btn" }, icon("refresh", { size: 16 }), "Sincronizar con Factus");
  async function pintarCatalogos() {
    const r = await get("/catalogos/factus", null, { signal: ctx.signal });
    montar(estadoCatalogos, r.sincronizados.length
      ? h("ul", { class: "list-plain" }, r.sincronizados.map((c) => h("li", null, h("span", { class: "mono" }, c.tipo), h("span", { class: "cell-sub" }, `${numero(c.registros)} · ${fechaHora(c.actualizado_en)}`))))
      : vacio({ icono: "stack", titulo: "Catálogos sin sincronizar", texto: "Sincronízalos para elegir municipios y unidades de medida con búsqueda." }));
  }
  refrescar.addEventListener("click", () => conBotonOcupado(refrescar, async () => {
    try {
      const r = await post("/catalogos/factus/refrescar", {}, { timeout: 90000 });
      const errores = Object.entries(r).filter(([, v]) => v.error);
      if (errores.length) toastError({ message: errores.map(([k, v]) => `${k}: ${v.error}`).join(" · ") }, "Algunos catálogos fallaron");
      else exito("Catálogos sincronizados.");
      pintarCatalogos();
    } catch (e) { toastError(e); }
  }));

  const form = h("form", { class: "table-toolbar", onsubmit: (e) => { e.preventDefault(); conBotonOcupado(consultar, () => cargar().catch(toastError)); } },
    h("div", { class: "field" }, h("label", { class: "field__label", for: "rep-desde" }, "Desde"), desde),
    h("div", { class: "field" }, h("label", { class: "field__label", for: "rep-hasta" }, "Hasta"), hasta),
    consultar, h("span", { class: "grow-1" }), btnVentas, btnFacturas);

  ctx.root.append(
    encabezado("Reportes", "Ventas y facturación por rango de fechas."),
    h("div", { class: "stack" },
      h("section", { class: "card" }, form),
      resultado,
      tarjeta({ titulo: "Catálogos de Factus", acciones: refrescar, flush: true, cuerpo: estadoCatalogos })));
  ctx.alSalir(() => destruir.forEach((fn) => fn?.()));
  await Promise.all([cargar(), pintarCatalogos()]);
}
