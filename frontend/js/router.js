/**
 * Router por hash con carga diferida de páginas.
 * Cada página exporta por defecto `async function (ctx)` y registra su limpieza con
 * ctx.alSalir(fn). Al cambiar de página se abortan sus peticiones (ctx.signal), se ejecutan
 * sus limpiezas (intervalos, listeners globales) y se cierran los modales abiertos.
 */
import { h, montar } from "./components/dom.js";
import { vacio, skeleton } from "./components/ui.js";
import { cerrarModales } from "./components/modal.js";
import { tieneRol } from "./auth.js";

/**
 * @typedef {{ patron: string, modulo: () => Promise<any>, titulo: string, nav?: string, roles?: string[] }} Ruta
 * @typedef {{ root: HTMLElement, params: Record<string,string>, query: URLSearchParams,
 *   signal: AbortSignal, alSalir: (fn: () => void) => void, navegar: (ruta: string) => void }} Contexto
 */

/** @type {Ruta[]} */
export const RUTAS = [
  { patron: "/", modulo: () => import("./pages/dashboard.js"), titulo: "Inicio", nav: "/" },
  { patron: "/ventas/nueva", modulo: () => import("./pages/venta-nueva.js"), titulo: "Nueva venta", nav: "/ventas/nueva" },
  { patron: "/ventas/:id/pago", modulo: () => import("./pages/pago.js"), titulo: "Pago", nav: "/ventas" },
  { patron: "/ventas/:id", modulo: () => import("./pages/venta-detalle.js"), titulo: "Venta", nav: "/ventas" },
  { patron: "/ventas", modulo: () => import("./pages/ventas.js"), titulo: "Ventas", nav: "/ventas" },
  { patron: "/clientes", modulo: () => import("./pages/clientes.js"), titulo: "Clientes", nav: "/clientes" },
  { patron: "/productos", modulo: () => import("./pages/productos.js"), titulo: "Productos", nav: "/productos" },
  { patron: "/facturas/:id", modulo: () => import("./pages/factura-detalle.js"), titulo: "Factura", nav: "/facturas" },
  { patron: "/facturas", modulo: () => import("./pages/facturas.js"), titulo: "Facturas", nav: "/facturas" },
  { patron: "/caja", modulo: () => import("./pages/caja.js"), titulo: "Caja", nav: "/caja" },
  { patron: "/trabajadores", modulo: () => import("./pages/trabajadores.js"), titulo: "Trabajadores", nav: "/trabajadores", roles: ["ADMIN"] },
  { patron: "/reportes", modulo: () => import("./pages/reportes.js"), titulo: "Reportes", nav: "/reportes", roles: ["ADMIN"] },
];

function coincidir(patron, ruta) {
  const a = patron.split("/").filter(Boolean);
  const b = ruta.split("/").filter(Boolean);
  if (a.length !== b.length) return null;
  const params = {};
  for (let i = 0; i < a.length; i += 1) {
    if (a[i].startsWith(":")) params[a[i].slice(1)] = decodeURIComponent(b[i]);
    else if (a[i] !== b[i]) return null;
  }
  return params;
}

export function leerHash() {
  const [ruta = "/", consulta = ""] = window.location.hash.replace(/^#/, "").split("?");
  return { ruta: ruta || "/", query: new URLSearchParams(consulta) };
}

/** Navega a una ruta de la app (sin el "#"). */
export function navegar(ruta) {
  const destino = `#${ruta.startsWith("/") ? ruta : `/${ruta}`}`;
  if (window.location.hash === destino) window.dispatchEvent(new HashChangeEvent("hashchange"));
  else window.location.hash = destino;
}

/** Actualiza la query del hash sin recargar la página actual. */
export function fijarQuery(query) {
  const { ruta } = leerHash();
  const texto = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== null && v !== undefined && v !== "")).toString();
  history.replaceState(null, "", `#${ruta}${texto ? `?${texto}` : ""}`);
}

/**
 * @param {{ root: HTMLElement, alCambiar: (ruta: Ruta|null) => void, nombreApp: string }} opciones
 */
export function iniciarRouter({ root, alCambiar, nombreApp }) {
  let actual = null;
  let turno = 0;

  async function resolver() {
    const miTurno = ++turno;
    const { ruta, query } = leerHash();

    if (actual) {
      actual.control.abort();
      actual.limpiezas.forEach((fn) => { try { fn(); } catch { /* limpieza best-effort */ } });
      actual = null;
    }
    cerrarModales();

    let encontrada = null;
    let params = {};
    for (const r of RUTAS) {
      const p = coincidir(r.patron, ruta);
      if (p) { encontrada = r; params = p; break; }
    }
    alCambiar(encontrada);

    if (!encontrada) {
      pintarError("Página no encontrada", "La dirección no existe o fue movida.", "search");
      document.title = `No encontrada · ${nombreApp}`;
      return;
    }
    if (encontrada.roles && !tieneRol(...encontrada.roles)) {
      pintarError("Sin permisos", "Esta sección es solo para administradores.", "ban");
      document.title = `Sin permisos · ${nombreApp}`;
      return;
    }

    montar(root, h("div", { class: "card card__body" }, skeleton(6)));
    const control = new AbortController();
    const limpiezas = [];
    actual = { control, limpiezas };

    let modulo;
    try {
      modulo = await encontrada.modulo();
    } catch {
      if (miTurno === turno) pintarError("No se pudo cargar la página", "Revisa tu conexión y recarga.", "alert");
      return;
    }
    if (miTurno !== turno) return; // el usuario ya navegó a otra página

    root.replaceChildren();
    root.classList.remove("page-enter");
    void root.offsetWidth; // reinicia la animación de entrada
    root.classList.add("page-enter");
    document.title = `${encontrada.titulo} · ${nombreApp}`;

    /** @type {Contexto} */
    const ctx = { root, params, query, signal: control.signal, alSalir: (fn) => limpiezas.push(fn), navegar };
    try {
      await modulo.default(ctx);
    } catch (e) {
      if (control.signal.aborted || e?.codigo === "CANCELADO") return;
      console.error(e);
      pintarError("Algo salió mal", e?.message || "Error al mostrar la página.", "alert");
    }
    if (miTurno === turno) {
      const titulo = /** @type {HTMLElement|null} */ (root.querySelector("[data-foco='titulo']"));
      titulo?.focus({ preventScroll: true });
      window.scrollTo({ top: 0 });
    }
  }

  function pintarError(titulo, texto, icono) {
    montar(root, h("div", { class: "error-page" }, vacio({
      icono, titulo, texto,
      accion: h("a", { class: "btn btn--primary", href: "#/" }, "Ir al inicio"),
    })));
  }

  window.addEventListener("hashchange", resolver);
  resolver();
}
