/** Arranque del shell de la aplicación (app.html). */
import { configurarApi, get, post } from "./api.js";
import { cerrarSesion, sesion, token, usuario, esAdmin } from "./auth.js";
import { STORAGE_KEYS } from "./config.js";
import { h } from "./components/dom.js";
import { icon } from "./components/icons.js";
import { abrirModal } from "./components/modal.js";
import { combobox } from "./components/combobox.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "./components/form.js";
import { toast, exito } from "./components/toast.js";
import { conBotonOcupado } from "./components/dom.js";
import { iniciarRouter, navegar } from "./router.js";
import { iniciarTema, botonTema } from "./theme.js";
import { iniciales } from "./utils/format.js";
import { storage } from "./utils/helpers.js";

const NOMBRE_APP = "Factu";

// --------------------------------------------------------------- guardas
iniciarTema();
if (!sesion()) cerrarSesion("expirada");

configurarApi({
  token,
  noAutenticado: () => cerrarSesion("expirada"),
  prohibido: () => toast("No tienes permisos para esta acción.", { tipo: "warning", titulo: "Acceso denegado" }),
});

// --------------------------------------------------------------- navegación
const NAV = [
  { ruta: "/ventas/nueva", texto: "Nueva venta", icono: "plus", cta: true },
  { seccion: "General" },
  { ruta: "/", texto: "Inicio", icono: "dashboard" },
  { ruta: "/ventas", texto: "Ventas", icono: "receipt" },
  { ruta: "/facturas", texto: "Facturas", icono: "invoice" },
  { ruta: "/caja", texto: "Caja", icono: "wallet" },
  { seccion: "Catálogo" },
  { ruta: "/clientes", texto: "Clientes", icono: "users" },
  { ruta: "/productos", texto: "Productos", icono: "box" },
  { seccion: "Administración", admin: true },
  { ruta: "/trabajadores", texto: "Trabajadores", icono: "badge", admin: true },
  { ruta: "/reportes", texto: "Reportes", icono: "chart", admin: true },
];

const appEl = /** @type {HTMLElement} */ (document.getElementById("app"));
const navEl = /** @type {HTMLElement} */ (document.getElementById("nav"));
const contenido = /** @type {HTMLElement} */ (document.getElementById("contenido"));

function construirNav() {
  const admin = esAdmin();
  navEl.replaceChildren(...NAV.filter((n) => !n.admin || admin).map((n) => (n.seccion
    ? h("li", { class: "nav__section", role: "presentation" }, n.seccion)
    : h("li", null, h("a", {
      class: ["nav__link", n.cta && "nav__link--cta"], href: `#${n.ruta}`, dataset: { ruta: n.ruta }, title: n.texto,
    }, icon(n.icono, { size: 19 }), h("span", { class: "nav__label" }, n.texto))))));
}

function marcarActivo(ruta) {
  navEl.querySelectorAll(".nav__link").forEach((a) => {
    if (a.dataset.ruta === ruta?.nav) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  appEl.dataset.navOpen = "false";
}

// --------------------------------------------------------------- barra lateral
function iniciarBarraLateral() {
  appEl.dataset.sidebar = storage.get(STORAGE_KEYS.sidebar, "expanded");
  document.getElementById("btn-colapsar").addEventListener("click", () => {
    const nuevo = appEl.dataset.sidebar === "collapsed" ? "expanded" : "collapsed";
    appEl.dataset.sidebar = nuevo;
    storage.set(STORAGE_KEYS.sidebar, nuevo);
  });
  const menuMovil = document.getElementById("btn-menu");
  menuMovil.addEventListener("click", () => {
    appEl.dataset.navOpen = appEl.dataset.navOpen === "true" ? "false" : "true";
    menuMovil.setAttribute("aria-expanded", appEl.dataset.navOpen);
  });
  document.getElementById("nav-backdrop").addEventListener("click", () => { appEl.dataset.navOpen = "false"; });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && appEl.dataset.navOpen === "true") appEl.dataset.navOpen = "false";
  });
}

// --------------------------------------------------------------- buscador global
function iniciarBuscador() {
  const cb = combobox({
    placeholder: "Buscar clientes, productos o ventas…",
    minimo: 2,
    buscar: async (texto, signal) => {
      const q = { buscar: texto, page_size: 4 };
      const [clientes, productos, ventas] = await Promise.all([
        get("/clientes", q, { signal }), get("/productos", q, { signal }), get("/ventas", q, { signal }),
      ]);
      return [
        ...ventas.items.map((v) => ({ valor: `/ventas/${v.idventa}`, etiqueta: v.referencia, sub: `Venta · ${v.cliente_nombre}` })),
        ...clientes.items.map((c) => ({ valor: `/clientes?buscar=${encodeURIComponent(c.identification)}`, etiqueta: c.names || c.company, sub: `Cliente · ${c.identification}` })),
        ...productos.items.map((p) => ({ valor: `/productos?buscar=${encodeURIComponent(p.code_reference)}`, etiqueta: p.nombre, sub: `Producto · ${p.code_reference}` })),
      ];
    },
    alElegir: (op) => {
      navegar(String(op.valor));
      cb.fijar(null);
      cb.input.blur();
    },
  });
  cb.input.setAttribute("aria-label", "Búsqueda global");
  const contenedor = document.getElementById("buscador");
  contenedor.append(h("div", { class: "input-icon" }, icon("search", { size: 17 }), cb.el));
  // Atajo: "/" enfoca el buscador
  document.addEventListener("keydown", (e) => {
    const t = /** @type {HTMLElement} */ (e.target);
    if (e.key === "/" && !t.closest("input, textarea, select, [contenteditable]")) {
      e.preventDefault();
      cb.input.focus();
    }
  });
}

// --------------------------------------------------------------- menú de usuario
function iniciarUsuario() {
  const u = usuario();
  const panel = h("div", { class: "menu__panel", role: "menu", hidden: true, id: "menu-usuario" },
    h("div", { class: "menu__head" }, u.email),
    h("button", { type: "button", class: "menu__item", role: "menuitem", onclick: () => { cerrar(); cambiarPassword(); } }, icon("key", { size: 16 }), "Cambiar contraseña"),
    h("div", { class: "menu__sep", role: "separator" }),
    h("button", { type: "button", class: "menu__item", role: "menuitem", onclick: () => cerrarSesion("salir") }, icon("logout", { size: 16 }), "Cerrar sesión"));
  const boton = h("button", { type: "button", class: "user-chip", "aria-haspopup": "menu", "aria-expanded": "false", "aria-controls": "menu-usuario" },
    h("span", { class: "avatar", "aria-hidden": "true" }, iniciales(u.nombre)),
    h("span", { class: "user-chip__text" },
      h("span", { class: "user-chip__name" }, u.nombre),
      h("span", { class: "user-chip__role" }, u.rol === "ADMIN" ? "Administrador" : "Trabajador")),
    icon("chevronDown", { size: 16 }));
  const cerrar = () => { panel.hidden = true; boton.setAttribute("aria-expanded", "false"); };
  boton.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    boton.setAttribute("aria-expanded", String(!panel.hidden));
    if (!panel.hidden) /** @type {HTMLElement} */ (panel.querySelector("button")).focus();
  });
  document.addEventListener("click", (e) => { if (!menu.contains(/** @type {Node} */ (e.target))) cerrar(); });
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") { cerrar(); boton.focus(); } });
  const menu = h("div", { class: "menu" }, boton, panel);
  document.getElementById("acciones-usuario").append(botonTema(), menu);
}

function cambiarPassword() {
  const form = h("form", { class: "form", novalidate: true },
    campo({ nombre: "password_actual", etiqueta: "Contraseña actual", tipo: "password", requerido: true, attrs: { autocomplete: "current-password" } }),
    campo({ nombre: "password_nueva", etiqueta: "Nueva contraseña", tipo: "password", requerido: true, ayuda: "Mínimo 10 caracteres.", attrs: { autocomplete: "new-password", minlength: "10" } }),
    campo({ nombre: "confirmar", etiqueta: "Confirmar nueva contraseña", tipo: "password", requerido: true, attrs: { autocomplete: "new-password" } }));
  const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-pass" }, "Cambiar contraseña");
  form.id = "form-pass";
  const modal = abrirModal({ titulo: "Cambiar contraseña", contenido: form, acciones: [guardar] });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const v = valores(form);
    const errores = {};
    if (!v.password_actual) errores.password_actual = "Escribe tu contraseña actual.";
    if (!v.password_nueva || v.password_nueva.length < 10) errores.password_nueva = "Mínimo 10 caracteres.";
    if (v.password_nueva !== v.confirmar) errores.confirmar = "Las contraseñas no coinciden.";
    if (mostrarErrores(form, errores)) return;
    conBotonOcupado(guardar, async () => {
      try {
        await post("/auth/cambiar-password", { password_actual: v.password_actual, password_nueva: v.password_nueva });
        modal.cerrar();
        exito("Tu contraseña se actualizó.");
      } catch (err) {
        mostrarErrorApi(form, err);
      }
    });
  });
}

// Las peticiones canceladas al cambiar de página son esperadas: no son errores.
window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.codigo === "CANCELADO") e.preventDefault();
});

// --------------------------------------------------------------- arranque
if (sesion()) {
  construirNav();
  iniciarBarraLateral();
  iniciarBuscador();
  iniciarUsuario();
  iniciarRouter({ root: contenido, alCambiar: marcarActivo, nombreApp: NOMBRE_APP });
  appEl.hidden = false;
  // Si la sesión expira con la pestaña abierta, volver al login.
  setInterval(() => { if (!sesion()) cerrarSesion("expirada"); }, 60000);
}
