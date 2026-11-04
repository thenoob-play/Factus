/** Piezas de interfaz pequeñas: badges, estados vacíos, skeletons, confirmación, copiar. */
import { h } from "./dom.js";
import { icon } from "./icons.js";
import { abrirModal } from "./modal.js";
import { toast } from "./toast.js";
import { copiar } from "../utils/helpers.js";

const ESTADOS = {
  // Ventas
  PENDIENTE_PAGO: ["Pendiente de pago", "warning"],
  PAGADA: ["Pagada", "info"],
  FACTURADA: ["Facturada", "success"],
  EXPIRADA: ["Expirada", "neutral"],
  CANCELADA: ["Cancelada", "neutral"],
  FACTURA_FALLIDA: ["Factura fallida", "danger"],
  // Pagos
  PENDIENTE: ["Pendiente", "warning"],
  APROBADO: ["Aprobado", "success"],
  RECHAZADO: ["Rechazado", "danger"],
  EXPIRADO: ["Expirado", "neutral"],
  ANULADO: ["Anulado", "neutral"],
  // Facturas
  PROCESANDO: ["Emitiendo…", "info"],
  EMITIDA: ["Emitida", "success"],
  FALLIDA: ["Fallida", "danger"],
  ANULADA: ["Anulada", "neutral"],
  // Generales
  ACTIVO: ["Activo", "success"],
  INACTIVO: ["Inactivo", "neutral"],
  ABIERTA: ["Abierta", "success"],
  CERRADA: ["Cerrada", "neutral"],
  ADMIN: ["Administrador", "primary"],
  TRABAJADOR: ["Trabajador", "info"],
};

/** Badge de estado con color semántico. */
export function badge(estado, textoAlterno) {
  const [texto, variante] = ESTADOS[estado] ?? [textoAlterno ?? estado ?? "—", "neutral"];
  return h("span", { class: ["badge", variante !== "neutral" && `badge--${variante}`] }, textoAlterno ?? texto);
}

export function etiquetaEstado(estado) {
  return ESTADOS[estado]?.[0] ?? estado;
}

/** Estado vacío con mensaje útil y acción opcional. */
export function vacio({ icono = "info", titulo, texto, accion }) {
  return h("div", { class: "empty" },
    h("div", { class: "empty__icon" }, icon(icono, { size: 24 })),
    h("p", { class: "empty__title" }, titulo),
    texto && h("p", { class: "empty__text" }, texto),
    accion);
}

/** Skeleton de N líneas. */
export function skeleton(lineas = 3) {
  return h("div", { class: "stack stack--sm", "aria-busy": "true", "aria-label": "Cargando" },
    Array.from({ length: lineas }, () => h("span", { class: "skeleton" })));
}

export function cargando(texto = "Cargando…") {
  return h("div", { class: "row", role: "status" }, h("div", { class: "spinner" }), h("span", { class: "muted" }, texto));
}

/** Aviso destacado. */
export function callout(tipo, titulo, ...contenido) {
  const iconos = { info: "info", warning: "alert", danger: "xCircle", success: "checkCircle" };
  return h("div", { class: ["callout", tipo !== "info" && `callout--${tipo}`], role: tipo === "danger" ? "alert" : null },
    icon(iconos[tipo]),
    h("div", null, titulo && h("div", { class: "callout__title" }, titulo), ...contenido));
}

/** Botón que copia un valor al portapapeles. */
export function botonCopiar(valor, etiqueta = "Copiar") {
  return h("button", {
    type: "button", class: "btn btn--ghost btn--icon btn--sm", "aria-label": etiqueta, title: etiqueta,
    onclick: async () => toast((await copiar(valor)) ? "Copiado al portapapeles." : "No se pudo copiar.", { tipo: "info", duracion: 1800 }),
  }, icon("copy", { size: 15 }));
}

/** Valor con botón de copiar. */
export function copiable(valor, { mono = true, etiqueta = "Copiar" } = {}) {
  return h("span", { class: "copy" },
    h("span", { class: ["copy__value", mono && "mono"] }, valor),
    botonCopiar(valor, `${etiqueta}: ${valor}`));
}

/**
 * Confirmación modal. Si `pedirMotivo`, exige un texto y lo devuelve.
 * @returns {Promise<false|true|string>}
 */
export function confirmar({ titulo, mensaje, textoConfirmar = "Confirmar", peligro = false, pedirMotivo = false, etiquetaMotivo = "Motivo" }) {
  const motivo = pedirMotivo ? h("textarea", { class: "textarea", id: "confirm-motivo", required: true, minlength: "3", maxlength: "255" }) : null;
  const error = h("p", { class: "field__error", "aria-live": "polite" });
  const contenido = [
    h("p", { class: "text-2" }, mensaje),
    motivo && h("div", { class: "field" }, h("label", { class: "field__label", for: "confirm-motivo" }, etiquetaMotivo, h("span", { class: "req" }, "*")), motivo, error),
  ];
  const botonOk = h("button", { type: "button", class: ["btn", peligro ? "btn--danger" : "btn--primary"] }, textoConfirmar);
  const botonNo = h("button", { type: "button", class: "btn" }, "Cancelar");
  const modal = abrirModal({ titulo, contenido, acciones: [botonNo, botonOk] });
  botonNo.addEventListener("click", () => modal.cerrar(false));
  botonOk.addEventListener("click", () => {
    if (motivo) {
      const texto = motivo.value.trim();
      if (texto.length < 3) {
        error.textContent = "Escribe un motivo (mínimo 3 caracteres).";
        motivo.focus();
        return;
      }
      modal.cerrar(texto);
    } else {
      modal.cerrar(true);
    }
  });
  if (!motivo) botonOk.focus();
  return modal.cerrado.then((v) => v ?? false);
}

/** Encabezado estándar de página. */
export function encabezado(titulo, subtitulo, ...acciones) {
  return h("header", { class: "page-header" },
    h("div", { class: "page-header__titles" },
      h("h1", { tabindex: "-1", dataset: { foco: "titulo" } }, titulo),
      subtitulo && h("p", { class: "page-header__sub" }, subtitulo)),
    acciones.length ? h("div", { class: "page-header__actions" }, acciones) : null);
}

/** Tarjeta con encabezado opcional. */
export function tarjeta({ titulo, acciones, cuerpo, flush = false, pie, clase }) {
  return h("section", { class: ["card", clase] },
    titulo && h("div", { class: "card__header" }, h("h2", { class: "card__title" }, titulo), acciones && h("div", { class: "row" }, acciones)),
    h("div", { class: ["card__body", flush && "card__body--flush"] }, cuerpo),
    pie && h("div", { class: "card__footer" }, pie));
}
