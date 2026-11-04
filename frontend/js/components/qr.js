/** QR: usa la imagen del backend cuando existe; si no, la genera con qrcode-generator. */
import { h } from "./dom.js";
import { CONFIG } from "../config.js";
import { cargarScript } from "../utils/helpers.js";

/** Imagen a partir del PNG en base64 que entrega el backend. */
export function qrDesdeBase64(base64, alt, clase = "qr-panel__img") {
  return h("img", { src: `data:image/png;base64,${base64}`, alt, class: clase, width: "232", height: "232" });
}

/** Genera un QR para un texto (p. ej. la URL de validación de la DIAN). */
export async function qrDesdeTexto(texto, alt, clase = "dian-qr") {
  await cargarScript(CONFIG.QR_LIB_URL);
  const qr = window.qrcode(0, "M");
  qr.addData(texto);
  qr.make();
  return h("img", { src: qr.createDataURL(6, 2), alt, class: clase });
}
