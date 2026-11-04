/**
 * Construcción segura de DOM. Todo el texto se inserta como nodo de texto (nunca innerHTML).
 *
 *   h("button", { class: "btn", onclick: guardar, "aria-label": "Guardar" }, icon("check"), "Guardar")
 *
 * Props especiales: class (string | array), dataset (objeto), on<evento> (listener),
 * hidden/disabled/checked (booleanos). El resto se asigna como atributo.
 * @param {string} tag
 * @param {Record<string, any>|null} [props]
 * @param  {...any} hijos strings, números, nodos, arrays, null/false (se ignoran)
 * @returns {HTMLElement}
 */
export function h(tag, props = null, ...hijos) {
  const el = document.createElement(tag);
  if (props) aplicarProps(el, props);
  agregar(el, hijos);
  // En <select> el value solo se puede fijar cuando ya existen las opciones.
  if (tag === "select" && props && props.value !== undefined && props.value !== null) el.value = String(props.value);
  return el;
}

const PROPIEDADES = new Set(["value", "checked", "disabled", "hidden", "selected", "indeterminate", "readOnly", "required"]);

function aplicarProps(el, props) {
  for (const [clave, valor] of Object.entries(props)) {
    if (valor === undefined || valor === null || valor === false) {
      if (PROPIEDADES.has(clave)) el[clave] = false;
      continue;
    }
    if (clave === "class") {
      el.className = Array.isArray(valor) ? valor.filter(Boolean).join(" ") : valor;
    } else if (clave === "dataset") {
      Object.assign(el.dataset, valor);
    } else if (clave.startsWith("on") && typeof valor === "function") {
      el.addEventListener(clave.slice(2).toLowerCase(), valor);
    } else if (PROPIEDADES.has(clave)) {
      el[clave] = valor;
    } else if (clave === "text") {
      el.textContent = String(valor);
    } else {
      el.setAttribute(clave, valor === true ? "" : String(valor));
    }
  }
}

/** Agrega hijos (texto o nodos) a un elemento. */
export function agregar(el, hijos) {
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    el.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return el;
}

/** Reemplaza todo el contenido de un elemento. */
export function montar(el, ...hijos) {
  el.replaceChildren();
  return agregar(el, hijos);
}

/** Fragmento con varios nodos. */
export function frag(...hijos) {
  const f = document.createDocumentFragment();
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    f.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return f;
}

/** Marca un botón como ocupado (deshabilitado + spinner) mientras dura la promesa. */
export async function conBotonOcupado(boton, accion) {
  if (!boton || boton.disabled) return undefined;
  boton.disabled = true;
  boton.setAttribute("aria-busy", "true");
  try {
    return await accion();
  } finally {
    boton.disabled = false;
    boton.removeAttribute("aria-busy");
  }
}
