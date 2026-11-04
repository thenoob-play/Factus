/**
 * Inicio. ADMIN: KPIs, gráficos y rankings (GET /dashboard).
 * TRABAJADOR: accesos rápidos, estado de su caja, últimas ventas y stock bajo
 * (el dashboard financiero es solo para administradores en el backend).
 */
import { get } from "../api.js";
import { esAdmin, usuario } from "../auth.js";
import { METODOS } from "../config.js";
import { h, montar } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { badge, encabezado, skeleton, tarjeta, vacio } from "../components/ui.js";
import { cop, fecha, fechaHora, numero } from "../utils/format.js";
import { grafico, serieDiaria } from "./graficos.js";

function kpi(etiqueta, valor, icono, { meta, variante, enlace } = {}) {
  const contenido = [
    h("div", { class: "kpi__label" }, h("span", { class: ["kpi__icon", variante && `kpi__icon--${variante}`] }, icon(icono, { size: 16 })), etiqueta),
    h("div", { class: "kpi__value" }, valor),
    meta && h("div", { class: "kpi__meta" }, meta),
  ];
  return enlace ? h("a", { class: "card kpi kpi--link", href: enlace }, contenido) : h("div", { class: "card kpi" }, contenido);
}

function listaVentas(ventas) {
  if (!ventas.length) return vacio({ icono: "receipt", titulo: "Aún no hay ventas", accion: h("a", { class: "btn btn--primary", href: "#/ventas/nueva" }, "Registrar la primera") });
  return h("ul", { class: "list-plain" }, ventas.map((v) => h("li", null,
    h("a", { href: `#/ventas/${v.idventa}` }, h("div", { class: "cell-main mono" }, v.referencia), h("div", { class: "cell-sub" }, `${v.cliente_nombre} · ${fechaHora(v.creado_en)}`)),
    h("div", { class: "row" }, h("strong", null, cop(v.total)), badge(v.estado)))));
}

function listaStockBajo(productos) {
  if (!productos.length) return vacio({ icono: "box", titulo: "Inventario en orden", texto: "Ningún producto está bajo su stock mínimo." });
  return h("ul", { class: "list-plain" }, productos.slice(0, 8).map((p) => h("li", null,
    h("div", null, h("div", { class: "cell-main" }, p.nombre), h("div", { class: "cell-sub mono" }, p.code_reference)),
    h("span", { class: "badge badge--warning" }, `${numero(p.stock_disponible)} / mín. ${numero(p.stock_minimo)}`))));
}

const accesos = () => h("div", { class: "quick-actions" },
  h("a", { class: "btn btn--primary", href: "#/ventas/nueva" }, icon("plus", { size: 16 }), "Nueva venta"),
  h("a", { class: "btn", href: "#/clientes" }, icon("users", { size: 16 }), "Nuevo cliente"),
  h("a", { class: "btn", href: "#/caja" }, icon("wallet", { size: 16 }), "Caja"));

export default async function paginaInicio(ctx) {
  const u = usuario();
  const saludo = `Hola, ${u.nombre.split(" ")[0]}`;
  if (!esAdmin()) return inicioTrabajador(ctx, saludo);

  const kpis = h("div", { class: "grid grid--kpi" }, Array.from({ length: 5 }, () => h("div", { class: "card kpi" }, skeleton(2))));
  const linea = h("div", null, h("span", { class: "skeleton skeleton--block" }));
  const barras = h("div", null, h("span", { class: "skeleton skeleton--block" }));
  const ultimas = h("div", { class: "card__body" }, skeleton(4));
  const top = h("div", { class: "card__body" }, skeleton(4));
  const bajo = h("div", { class: "card__body" }, skeleton(4));

  ctx.root.append(
    encabezado(saludo, `Resumen al ${fecha(new Date())}`, accesos()),
    h("div", { class: "stack" },
      kpis,
      h("div", { class: "grid grid--3" },
        h("div", { class: "span-2" }, tarjeta({ titulo: "Ventas de los últimos 30 días", cuerpo: linea })),
        tarjeta({ titulo: "Por método de pago (mes)", cuerpo: barras })),
      h("div", { class: "grid grid--3" },
        tarjeta({ titulo: "Últimas ventas", acciones: h("a", { href: "#/ventas" }, "Ver todas"), flush: true, cuerpo: ultimas }),
        tarjeta({ titulo: "Más vendidos del mes", flush: true, cuerpo: top }),
        tarjeta({ titulo: "Stock bajo", acciones: h("a", { href: "#/productos?stock_bajo=1" }, "Ver"), flush: true, cuerpo: bajo }))));

  const [d, ventas] = await Promise.all([
    get("/dashboard", null, { signal: ctx.signal }),
    get("/ventas", { page_size: 6 }, { signal: ctx.signal }),
  ]);
  const totalFacturas = Object.values(d.facturas_mes).reduce((a, n) => a + n, 0);
  const fallidas = d.facturas_fallidas.length;
  montar(kpis,
    kpi("Ventas de hoy", cop(d.ventas_hoy.total), "trend", { meta: `${numero(d.ventas_hoy.cantidad)} ventas` }),
    kpi("Ventas del mes", cop(d.ventas_mes.total), "chart", { meta: `${numero(d.ventas_mes.cantidad)} ventas`, variante: "info" }),
    kpi("Facturas del mes", numero(totalFacturas), "invoice", { meta: `${numero(d.facturas_mes.EMITIDA ?? 0)} emitidas`, enlace: "#/facturas" }),
    kpi("Facturas fallidas", numero(fallidas), "alert", { meta: fallidas ? "Requieren reintento" : "Todo emitido", variante: fallidas ? "danger" : undefined, enlace: "#/facturas?estado=FALLIDA" }),
    kpi("Stock bajo", numero(d.stock_bajo.length), "box", { meta: "productos bajo el mínimo", variante: d.stock_bajo.length ? "warning" : undefined, enlace: "#/productos?stock_bajo=1" }));

  montar(ultimas, listaVentas(ventas.items));
  montar(bajo, listaStockBajo(d.stock_bajo));
  montar(top, d.mas_vendidos_mes.length
    ? h("ul", { class: "list-plain" }, d.mas_vendidos_mes.slice(0, 8).map((p, i) => h("li", null,
      h("div", { class: "row" }, h("span", { class: "rank" }, String(i + 1)), h("span", { class: "cell-main" }, p.nombre)),
      h("span", { class: "text-2" }, `${numero(p.unidades)} u · ${cop(p.total)}`))))
    : vacio({ icono: "chart", titulo: "Sin ventas este mes" }));

  const serie = serieDiaria(d.ventas_por_dia, 30);
  const destruirLinea = await grafico(linea, "linea", { ...serie, nombre: "Ventas por día" }).catch(() => { linea.replaceChildren(h("p", { class: "muted" }, "No se pudo cargar el gráfico.")); return null; });
  const destruirBarras = d.por_metodo_mes.length
    ? await grafico(barras, "barras", { etiquetas: d.por_metodo_mes.map((m) => METODOS[m.metodo_pago]), valores: d.por_metodo_mes.map((m) => Number(m.total)), nombre: "Ventas por método" }).catch(() => null)
    : (montar(barras, vacio({ icono: "wallet", titulo: "Sin ventas este mes" })), null);
  ctx.alSalir(() => { destruirLinea?.(); destruirBarras?.(); });
}

async function inicioTrabajador(ctx, saludo) {
  const caja = h("div", { class: "card__body" }, skeleton(2));
  const ultimas = h("div", { class: "card__body" }, skeleton(4));
  const bajo = h("div", { class: "card__body" }, skeleton(4));
  ctx.root.append(
    encabezado(saludo, "¿Qué quieres hacer hoy?", accesos()),
    h("div", { class: "grid grid--3" },
      tarjeta({ titulo: "Mi caja", cuerpo: caja }),
      tarjeta({ titulo: "Últimas ventas", acciones: h("a", { href: "#/ventas" }, "Ver todas"), flush: true, cuerpo: ultimas }),
      tarjeta({ titulo: "Stock bajo", flush: true, cuerpo: bajo })));

  const [c, ventas, productos] = await Promise.all([
    get("/cajas/actual", null, { signal: ctx.signal }),
    get("/ventas", { page_size: 6, idtrabajador: usuario().idtrabajador }, { signal: ctx.signal }),
    get("/productos/stock-bajo", { page_size: 8 }, { signal: ctx.signal }),
  ]);
  montar(caja, c
    ? h("div", { class: "stack stack--sm" }, badge("ABIERTA"), h("div", { class: "kpi__value" }, cop(c.efectivo_esperado_actual)),
      h("p", { class: "cell-sub" }, `Efectivo esperado · ${c.movimientos.length} cobros`), h("a", { class: "btn btn--sm", href: "#/caja" }, "Ver caja"))
    : h("div", { class: "stack stack--sm" }, badge("CERRADA"), h("p", { class: "text-2" }, "Ábrela para recibir pagos en efectivo."), h("a", { class: "btn btn--primary btn--sm", href: "#/caja" }, "Abrir caja")));
  montar(ultimas, listaVentas(ventas.items));
  montar(bajo, listaStockBajo(productos.items));
}
