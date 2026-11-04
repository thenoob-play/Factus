/** Acciones sobre facturas reutilizadas por el flujo de pago y el detalle de factura. */
import { descargar, post } from "../api.js";
import { CONFIG } from "../config.js";
import { h, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { exito, error as toastError } from "../components/toast.js";
import { guardarBlob, validar } from "../utils/helpers.js";

const opcionesDescarga = { timeout: CONFIG.TIMEOUT_FACTUS_MS };

/** Descarga el PDF o XML de la factura. */
export async function descargarDocumento(idfactura, tipo, boton) {
  await conBotonOcupado(boton, async () => {
    try {
      const { blob, nombre } = await descargar(`/facturas/${idfactura}/${tipo}`, null, { ...opcionesDescarga, nombreArchivo: `factura-${idfactura}.${tipo}` });
      guardarBlob(blob, nombre);
    } catch (e) { toastError(e, `No se pudo descargar el ${tipo.toUpperCase()}`); }
  });
}

/** Muestra el PDF en un visor embebido (en móvil se abre en otra pestaña). */
export async function verPdf(idfactura, boton) {
  await conBotonOcupado(boton, async () => {
    try {
      const { blob, nombre } = await descargar(`/facturas/${idfactura}/pdf`, null, opcionesDescarga);
      const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      if (window.matchMedia("(max-width: 720px)").matches) {
        window.open(url, "_blank", "noopener");
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        return;
      }
      abrirModal({
        titulo: nombre, tamano: "xl",
        contenido: h("iframe", { class: "pdf-frame", src: url, title: `Factura ${nombre}` }),
        acciones: [h("a", { class: "btn btn--primary", href: url, download: nombre }, icon("download", { size: 16 }), "Descargar")],
        alCerrar: () => URL.revokeObjectURL(url),
      });
    } catch (e) { toastError(e, "No se pudo abrir el PDF"); }
  });
}

/** Modal para reenviar la factura por correo (el email es editable). */
export function enviarPorEmail(idfactura, emailPorDefecto) {
  const form = h("form", { class: "form", novalidate: true, id: "form-email" },
    h("p", { class: "text-2" }, "Factus enviará la factura (PDF y XML) al correo indicado."),
    campo({ nombre: "email", etiqueta: "Correo electrónico", tipo: "email", requerido: true, valor: emailPorDefecto ?? "", attrs: { autocomplete: "email" } }));
  const enviar = h("button", { type: "submit", class: "btn btn--primary", form: "form-email" }, icon("send", { size: 16 }), "Enviar");
  const modal = abrirModal({ titulo: "Enviar factura por correo", contenido: form, acciones: [enviar] });
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const { email } = valores(form);
    if (mostrarErrores(form, !email || !validar.email(email) ? { email: "Escribe un correo válido." } : {})) return;
    conBotonOcupado(enviar, async () => {
      try {
        await post(`/facturas/${idfactura}/enviar-email`, { email }, opcionesDescarga);
        exito(`Factura enviada a ${email}.`);
        modal.cerrar();
      } catch (err) { mostrarErrorApi(form, err); }
    });
  });
}

/** Reintenta la emisión de una factura fallida. Devuelve la factura actualizada o null. */
export async function reintentarFactura(idfactura, boton) {
  return conBotonOcupado(boton, async () => {
    try {
      const f = await post(`/facturas/${idfactura}/reintentar`, {}, opcionesDescarga);
      if (f.estado === "EMITIDA") exito(`Factura ${f.numero} emitida.`);
      else toastError({ message: f.mensaje || "Factus volvió a rechazar la factura." }, "La factura sigue fallida");
      return f;
    } catch (e) {
      toastError(e, "No se pudo reintentar");
      return null;
    }
  });
}

/** Lista legible de errores de validación de Factus/DIAN (estructura variable). */
export function listaErrores(errores) {
  const mensajes = [];
  const recorrer = (valor, ruta = "") => {
    if (valor == null) return;
    if (typeof valor === "string") mensajes.push(ruta ? `${ruta}: ${valor}` : valor);
    else if (Array.isArray(valor)) valor.forEach((v) => recorrer(v, ruta));
    else if (typeof valor === "object") Object.entries(valor).forEach(([k, v]) => recorrer(v, ["provider_status", "factus"].includes(k) ? ruta : k));
  };
  recorrer(errores);
  const unicos = [...new Set(mensajes)].slice(0, 12);
  return unicos.length ? h("ul", { class: "steps" }, unicos.map((m) => h("li", null, m))) : null;
}
