/**
 * Formularios: construcción de campos accesibles, lectura de valores y errores por campo
 * (validación local + errores 422 del backend).
 */
import { h } from "./dom.js";
import { ApiError } from "../api.js";

let contador = 0;

/**
 * Campo con label, control, ayuda y error.
 * @param {{
 *   nombre: string, etiqueta: string, tipo?: string, valor?: any, requerido?: boolean,
 *   opciones?: [string, string][], ayuda?: string, placeholder?: string, completo?: boolean,
 *   attrs?: Record<string, any>, control?: HTMLElement, mono?: boolean,
 * }} c
 */
export function campo(c) {
  const id = `f-${c.nombre}-${++contador}`;
  const idAyuda = `${id}-ayuda`;
  const idError = `${id}-error`;
  let control = c.control;
  if (!control) {
    const comunes = {
      id, name: c.nombre, required: c.requerido || null,
      "aria-describedby": [c.ayuda && idAyuda, idError].filter(Boolean).join(" "),
      ...c.attrs,
    };
    if (c.tipo === "select") {
      control = h("select", { ...comunes, class: "select", value: c.valor ?? "" },
        c.opciones.map(([valor, texto]) => h("option", { value: valor }, texto)));
    } else if (c.tipo === "textarea") {
      control = h("textarea", { ...comunes, class: "textarea", placeholder: c.placeholder }, c.valor ?? "");
    } else {
      control = h("input", {
        ...comunes, type: c.tipo ?? "text", class: ["input", c.mono && "input--mono"],
        value: c.valor ?? "", placeholder: c.placeholder,
      });
    }
  } else {
    control.id ||= id;
    control.setAttribute("aria-describedby", idError);
  }
  return h("div", { class: ["field", c.completo && "full"], dataset: { campo: c.nombre } },
    h("label", { class: "field__label", for: control.id }, c.etiqueta, c.requerido && h("span", { class: "req", "aria-hidden": "true" }, "*")),
    control,
    c.ayuda && h("p", { class: "field__hint", id: idAyuda }, c.ayuda),
    h("p", { class: "field__error", id: idError, "aria-live": "polite" }));
}

/** Lee los valores de un formulario como objeto (checkbox → boolean, vacío → null). */
export function valores(form) {
  const datos = {};
  for (const el of /** @type {any[]} */ ([...form.elements])) {
    if (!el.name || el.disabled) continue;
    if (el.type === "checkbox") datos[el.name] = el.checked;
    else if (el.type === "radio") { if (el.checked) datos[el.name] = el.value; }
    else if (el.type === "file") continue;
    else datos[el.name] = el.value.trim() === "" ? null : el.value.trim();
  }
  return datos;
}

export function limpiarErrores(form) {
  form.querySelectorAll(".field--invalid").forEach((f) => f.classList.remove("field--invalid"));
  form.querySelectorAll(".field__error").forEach((e) => { e.textContent = ""; });
  form.querySelectorAll("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
  form.querySelector(".form-error")?.remove();
}

/**
 * Marca errores por campo. Devuelve true si se marcó alguno.
 * @param {HTMLElement} form
 * @param {Record<string, string>} errores
 */
export function mostrarErrores(form, errores) {
  let primero = null;
  for (const [nombre, mensaje] of Object.entries(errores)) {
    const contenedor = form.querySelector(`[data-campo="${CSS.escape(nombre)}"]`);
    if (!contenedor) continue;
    contenedor.classList.add("field--invalid");
    contenedor.querySelector(".field__error").textContent = mensaje;
    const control = contenedor.querySelector("input, select, textarea");
    control?.setAttribute("aria-invalid", "true");
    primero ??= control;
  }
  primero?.focus();
  return primero !== null;
}

/** Error general al inicio del formulario. */
export function errorGeneral(form, mensaje) {
  form.querySelector(".form-error")?.remove();
  const el = h("p", { class: "callout callout--danger form-error", role: "alert" }, mensaje);
  form.prepend(el);
}

/**
 * Muestra un error de la API en el formulario: errores 422 junto a cada campo y el resto arriba.
 * Devuelve true si lo pudo mostrar en el formulario.
 */
export function mostrarErrorApi(form, err) {
  if (!(err instanceof ApiError)) return false;
  const porCampo = err.erroresCampo;
  const marcados = mostrarErrores(form, porCampo);
  const generales = err.erroresGenerales;
  if (generales.length) errorGeneral(form, generales.join(" "));
  else if (!marcados) errorGeneral(form, err.message);
  return true;
}
