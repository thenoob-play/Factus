/** Gráficos con Chart.js (cargado por demanda) que siguen el tema claro/oscuro. */
import { CONFIG } from "../config.js";
import { h } from "../components/dom.js";
import { cargarScript } from "../utils/helpers.js";
import { alCambiarTema } from "../theme.js";
import { cop, diaCorto } from "../utils/format.js";

const color = (variable) => getComputedStyle(document.documentElement).getPropertyValue(variable).trim();

function paleta() {
  return {
    primario: color("--c-primary"), acento: color("--c-accent"), info: color("--c-info"),
    texto: color("--c-text-2"), rejilla: color("--c-border"), fuente: color("--font-ui"),
  };
}

/**
 * Crea un gráfico dentro de un contenedor. Devuelve una función que lo destruye.
 * @param {HTMLElement} contenedor
 * @param {"linea"|"barras"} tipo
 * @param {{etiquetas: string[], valores: number[], nombre: string}} datos
 */
export async function grafico(contenedor, tipo, datos) {
  const lienzo = h("canvas", { role: "img", "aria-label": `${datos.nombre}: ${datos.etiquetas.map((e, i) => `${e} ${cop(datos.valores[i])}`).join(", ")}` });
  contenedor.replaceChildren(h("div", { class: "chart-box" }, lienzo));
  await cargarScript(CONFIG.CHART_JS_URL);
  const Chart = window.Chart;
  let chart;

  const construir = () => {
    chart?.destroy();
    const p = paleta();
    const lineal = tipo === "linea";
    chart = new Chart(lienzo, {
      type: lineal ? "line" : "bar",
      data: {
        labels: datos.etiquetas,
        datasets: [{
          label: datos.nombre, data: datos.valores,
          borderColor: p.primario, backgroundColor: lineal ? `${p.primario}22` : [p.primario, p.acento, p.info],
          fill: lineal, tension: 0.35, borderWidth: lineal ? 2.5 : 0, pointRadius: lineal ? 2.5 : 0,
          borderRadius: 8, maxBarThickness: 56,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 400 },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${cop(c.parsed.y)}` } } },
        scales: {
          x: { grid: { display: false }, ticks: { color: p.texto, font: { family: p.fuente }, maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } },
          y: { grid: { color: p.rejilla }, border: { display: false },
            ticks: { color: p.texto, font: { family: p.fuente }, callback: (v) => cop(v).replace(/\s?COP/, "") } },
        },
      },
    });
  };
  construir();
  const desuscribir = alCambiarTema(construir);
  return () => { desuscribir(); chart?.destroy(); };
}

/** Rellena los días faltantes con 0 para una serie continua. */
export function serieDiaria(filas, dias) {
  const mapa = new Map(filas.map((f) => [String(f.dia).slice(0, 10), Number(f.total)]));
  const etiquetas = [];
  const valores = [];
  const hoy = new Date();
  for (let i = dias - 1; i >= 0; i -= 1) {
    const d = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate() - i);
    const clave = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    etiquetas.push(diaCorto(clave));
    valores.push(mapa.get(clave) ?? 0);
  }
  return { etiquetas, valores };
}
