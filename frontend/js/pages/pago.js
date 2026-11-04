/**
 * Flujo de pago de una venta (#/ventas/:id/pago).
 * EFECTIVO (caja abierta) · TRANSFERENCIA Bre-B manual o Wompi · TARJETA Wompi o datáfono.
 * Al aprobarse: comprobante con datos de verificación y estado de la factura en vivo.
 * Nunca se piden datos completos de tarjeta.
 */
import { get, post } from "../api.js";
import { CONFIG, METODOS, CANALES } from "../config.js";
import { h, montar, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { qrDesdeBase64 } from "../components/qr.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { badge, callout, confirmar, copiable, encabezado, skeleton, tarjeta, vacio } from "../components/ui.js";
import { exito, error as toastError, aviso } from "../components/toast.js";
import { cop, duracion, fechaHora, isoLocalMinutos, parseFecha, numero } from "../utils/format.js";
import { leerComoDataURL } from "../utils/helpers.js";
import { descargarDocumento, enviarPorEmail, reintentarFactura, listaErrores, verPdf } from "./acciones-factura.js";

const BILLETES = [10000, 20000, 50000, 100000];
const ESTADOS_PAGADOS = new Set(["PAGADA", "FACTURADA", "FACTURA_FALLIDA"]);

export default async function paginaPago(ctx) {
  const idventa = ctx.params.id;
  const temporizadores = new Set();
  const cada = (fn, ms) => { const t = setInterval(fn, ms); temporizadores.add(t); return () => { clearInterval(t); temporizadores.delete(t); }; };
  const detenerTodo = () => { temporizadores.forEach(clearInterval); temporizadores.clear(); };
  ctx.alSalir(detenerTodo);

  let venta;
  const panel = h("div");
  const resumen = h("div");
  const cabecera = h("div");
  ctx.root.append(cabecera, h("div", { class: "pay" }, panel, resumen));

  async function cargar() {
    venta = await get(`/ventas/${idventa}`, null, { signal: ctx.signal });
    return venta;
  }

  function huella(v) {
    return JSON.stringify([v.estado, v.pago?.idpago, v.pago?.estado, v.pago?.comprobante_registrado_en, v.factura?.estado]);
  }

  /** Repinta la vista; los errores (salvo cancelaciones al salir) se muestran en el panel. */
  function pintar() {
    return pintarVista().catch((e) => {
      if (e?.codigo === "CANCELADO" || ctx.signal.aborted) return;
      montar(panel, tarjeta({ cuerpo: vacio({ icono: "alert", titulo: "No se pudo cargar el pago", texto: e?.message,
        accion: h("button", { type: "button", class: "btn", onclick: () => cargar().then(pintar).catch(() => {}) }, icon("refresh", { size: 16 }), "Reintentar") }) }));
    });
  }

  async function pintarVista() {
    detenerTodo();
    montar(cabecera, encabezado(`Cobro · ${venta.referencia}`, `${METODOS[venta.metodo_pago]} · creada ${fechaHora(venta.creado_en)}`,
      badge(venta.estado),
      venta.estado === "PENDIENTE_PAGO" && h("button", { type: "button", class: "btn", onclick: cambiarMetodo }, icon("refresh", { size: 16 }), "Cambiar método"),
      venta.estado === "PENDIENTE_PAGO" && h("button", { type: "button", class: "btn", onclick: cancelar }, icon("ban", { size: 16 }), "Cancelar venta"),
      h("a", { class: "btn btn--ghost", href: `#/ventas/${venta.idventa}` }, "Ver detalle")));
    pintarResumen();
    if (ESTADOS_PAGADOS.has(venta.estado)) return vistaExito();
    if (venta.estado !== "PENDIENTE_PAGO") return vistaCerrada();
    return vistaPendiente();
  }

  /** Recarga periódica: re-pinta solo si cambió algo relevante. */
  function vigilar(ms = CONFIG.POLL_PAGO_MS) {
    const antes = huella(venta);
    cada(async () => {
      if (document.hidden) return;
      try {
        const v = await get(`/ventas/${idventa}`, null, { signal: ctx.signal });
        if (huella(v) !== antes) { venta = v; pintar(); }
      } catch (e) { if (e?.codigo !== "CANCELADO") console.warn(e); }
    }, ms);
  }

  // ------------------------------------------------------------ resumen lateral
  function pintarResumen() {
    montar(resumen, tarjeta({
      titulo: "Resumen de la venta",
      cuerpo: h("div", { class: "stack" },
        h("ul", { class: "list-plain" }, venta.items.map((it) => h("li", { class: "nowrap" },
          h("div", null, h("div", { class: "cell-main" }, it.nombre), h("div", { class: "cell-sub" }, `${numero(it.cantidad)} × ${cop(it.precio_unitario)}`)),
          h("strong", null, cop(it.total))))),
        h("div", { class: "totals" },
          h("div", { class: "totals__row" }, h("span", null, "Subtotal"), h("span", null, cop(venta.subtotal))),
          Number(venta.descuento_total) > 0 && h("div", { class: "totals__row" }, h("span", null, "Descuentos"), h("span", null, `− ${cop(venta.descuento_total)}`)),
          venta.impuestos.filter((g) => Number(g.impuesto) > 0).map((g) => h("div", { class: "totals__row" },
            h("span", null, `IVA ${Number(g.tax_rate)} % sobre ${cop(g.base)}`), h("span", null, cop(g.impuesto)))),
          h("div", { class: "totals__row totals__row--total" }, h("span", null, "Total"), h("span", null, cop(venta.total))))),
    }));
  }

  // ------------------------------------------------------------ pendiente
  function vistaPendiente() {
    const pago = venta.pago;
    if (!pago || pago.estado !== "PENDIENTE") {
      const ultimo = venta.pagos.at(-1);
      montar(panel, tarjeta({ cuerpo: h("div", { class: "stack" },
        callout(ultimo?.estado === "RECHAZADO" ? "danger" : "warning",
          ultimo?.estado === "RECHAZADO" ? "El pago fue rechazado" : "El pago ya no está vigente",
          ultimo?.motivo_rechazo || "Genera un nuevo pago para continuar con esta venta."),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn--primary", onclick: cambiarMetodo }, icon("refresh", { size: 16 }), "Generar nuevo pago"))) }));
      return;
    }
    const expira = parseFecha(pago.expira_en);
    const contador = h("span", { class: "countdown", role: "timer", "aria-live": "off" });
    const tic = () => {
      const s = (expira.getTime() - Date.now()) / 1000;
      contador.replaceChildren(icon("clock", { size: 15 }), s > 0 ? `Expira en ${duracion(s)}` : "Expirado");
      contador.className = `countdown${s <= 0 ? " countdown--over" : s < 300 ? " countdown--low" : ""}`;
      if (s <= 0) { detenerTodo(); alExpirar(); }
    };
    cada(tic, 1000);
    tic();

    const canal = pago.canal;
    const paneles = { EFECTIVO: panelEfectivo, BREB_MANUAL: panelBreB, WOMPI: panelWompi, DATAFONO: panelDatafono };
    Promise.resolve(paneles[canal]?.(pago, contador)).catch((e) => {
      if (e?.codigo === "CANCELADO") return;
      montar(panel, tarjeta({ cuerpo: vacio({ icono: "alert", titulo: "No se pudo preparar el pago", texto: e?.message,
        accion: h("button", { type: "button", class: "btn", onclick: () => pintar() }, icon("refresh", { size: 16 }), "Reintentar") }) }));
    });
    // Siempre se vigila: otro trabajador o el webhook pueden aprobar el pago.
    vigilar(canal === "EFECTIVO" || canal === "DATAFONO" ? 15000 : CONFIG.POLL_PAGO_MS);
  }

  function alExpirar() {
    montar(panel, tarjeta({ cuerpo: h("div", { class: "stack" },
      callout("warning", "El tiempo para pagar terminó", "El stock reservado se liberará. Puedes generar un nuevo pago si el cliente sigue interesado."),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn btn--primary", onclick: cambiarMetodo }, icon("refresh", { size: 16 }), "Generar nuevo pago"),
        h("a", { class: "btn", href: `#/ventas/nueva?repetir=${venta.idventa}` }, "Nueva venta con estos productos"))) }));
  }

  /** Tras una confirmación: recarga y pinta el resultado. */
  async function trasConfirmar(resultado) {
    if (resultado && resultado.aprobado === false) {
      toastError({ message: resultado.motivo || "El pago fue rechazado." }, resultado.sospechoso ? "Pago rechazado por verificación" : "Pago rechazado");
    } else if (resultado?.aprobado) {
      exito("Pago aprobado. Emitiendo la factura electrónica…");
    }
    await cargar();
    pintar();
  }

  // ----- EFECTIVO
  async function panelEfectivo(pago, contador) {
    montar(panel, tarjeta({ cuerpo: skeleton(4) }));
    const caja = await get("/cajas/actual", null, { signal: ctx.signal });

    if (!caja) {
      const base = h("input", { type: "number", class: "input", min: "0", step: "100", value: "0", id: "base-caja", inputmode: "decimal" });
      const abrir = h("button", { type: "button", class: "btn btn--primary" }, icon("wallet", { size: 16 }), "Abrir caja");
      abrir.addEventListener("click", () => conBotonOcupado(abrir, async () => {
        try {
          await post("/cajas/abrir", { base_inicial: Number(base.value || 0).toFixed(2) });
          exito("Caja abierta.");
          panelEfectivo(pago, contador);
        } catch (e) { toastError(e); }
      }));
      montar(panel, tarjeta({ titulo: "Pago en efectivo", cuerpo: h("div", { class: "stack" },
        callout("warning", "Tu caja está cerrada", "Para recibir efectivo abre tu caja con la base inicial."),
        h("div", { class: "field" }, h("label", { class: "field__label", for: "base-caja" }, "Base inicial"), base),
        h("div", null, abrir)) }));
      base.focus();
      return;
    }

    const total = Number(venta.total);
    const recibido = /** @type {HTMLInputElement} */ (h("input", {
      type: "number", class: "input input--lg num", min: "0", step: "50", inputmode: "decimal", id: "recibido", "aria-describedby": "cambio",
    }));
    const cambio = h("div", { class: "change-box", id: "cambio", "aria-live": "polite" });
    const confirmarBtn = h("button", { type: "button", class: "btn btn--primary btn--lg btn--block", disabled: true }, icon("check", { size: 18 }), "Registrar pago");

    const actualizar = () => {
      const r = Number(recibido.value);
      const ok = Number.isFinite(r) && r >= total;
      confirmarBtn.disabled = !ok;
      cambio.className = `change-box ${recibido.value === "" ? "" : ok ? "change-box--ok" : "change-box--bad"}`;
      montar(cambio, h("span", null, ok || recibido.value === "" ? "Cambio" : "Falta"),
        h("span", { class: "change-box__value" }, recibido.value === "" ? "—" : cop(Math.abs(r - total))));
    };
    const billetes = h("div", { class: "bills" },
      BILLETES.filter((b) => b >= total * 0.2).map((b) => h("button", { type: "button", class: "btn", dataset: { valor: String(b) } }, cop(b))),
      h("button", { type: "button", class: "btn btn--soft", dataset: { valor: String(total) } }, "Exacto"));
    billetes.addEventListener("click", (e) => {
      const b = /** @type {HTMLElement} */ (e.target).closest("[data-valor]");
      if (!b) return;
      recibido.value = b.dataset.valor;
      actualizar();
      confirmarBtn.focus();
    });
    recibido.addEventListener("input", actualizar);
    recibido.addEventListener("keydown", (e) => { if (e.key === "Enter" && !confirmarBtn.disabled) confirmarBtn.click(); });
    confirmarBtn.addEventListener("click", () => conBotonOcupado(confirmarBtn, async () => {
      try {
        const r = await post(`/ventas/${idventa}/pagos/efectivo`, { monto_recibido: Number(recibido.value).toFixed(2) });
        await trasConfirmar(r);
      } catch (e) { toastError(e, "No se registró el pago"); }
    }));

    montar(panel, tarjeta({ titulo: "Pago en efectivo", acciones: contador, cuerpo: h("div", { class: "stack" },
      h("div", { class: "amount-hero" }, h("div", { class: "amount-hero__label" }, "Total a cobrar"), h("div", { class: "amount-hero__value" }, cop(total))),
      h("div", { class: "field" }, h("label", { class: "field__label", for: "recibido" }, "Monto recibido"), recibido),
      billetes, cambio, confirmarBtn,
      h("p", { class: "cell-sub" }, `Caja abierta desde ${fechaHora(caja.abierta_en)}.`)) }));
    actualizar();
    recibido.focus();
  }

  // ----- TRANSFERENCIA BRE-B (manual)
  async function panelBreB(pago, contador) {
    montar(panel, tarjeta({ cuerpo: skeleton(6) }));
    const qr = await get(`/ventas/${idventa}/qr`, null, { signal: ctx.signal });
    let datosQr = {};
    try { datosQr = JSON.parse(qr.qr_payload); } catch { /* payload no JSON */ }

    const bloqueQr = h("div", { class: "qr-panel" },
      qrDesdeBase64(qr.qr_png_base64, `Código QR para pagar ${cop(qr.monto)} con referencia ${qr.referencia}`),
      contador,
      h("div", { class: "amount-hero__value" }, cop(qr.monto)),
      h("dl", { class: "dl" },
        h("dt", null, "Referencia"), h("dd", null, copiable(qr.referencia, { etiqueta: "Copiar referencia" })),
        datosQr.llave && [h("dt", null, "Llave Bre-B"), h("dd", null, copiable(datosQr.llave, { etiqueta: "Copiar llave" }))],
        datosQr.comercio && [h("dt", null, "Comercio"), h("dd", null, datosQr.comercio)]));

    const pasos = h("ol", { class: "steps" },
      h("li", null, "El cliente abre la app de su banco y elige transferir con llave Bre-B."),
      h("li", null, `Transfiere exactamente ${cop(qr.monto)} y escribe la referencia en la descripción.`),
      h("li", null, "Registra aquí el comprobante (número o CUS, banco, fecha y monto)."),
      h("li", null, "Un trabajador verifica en el extracto del banco y aprueba el pago."));

    const zona = pago.comprobante_registrado_en ? verificacionManual(pago) : formularioComprobante(pago);
    montar(panel, h("div", { class: "stack" },
      tarjeta({ titulo: "Transferencia Bre-B", cuerpo: h("div", { class: "grid grid--2" }, bloqueQr, h("div", { class: "stack" }, h("h3", null, "Instrucciones"), pasos)) }),
      zona));
  }

  function formularioComprobante(pago) {
    const imagen = /** @type {HTMLInputElement} */ (h("input", { type: "file", accept: "image/png,image/jpeg", class: "input", name: "imagen" }));
    const vista = h("div");
    let imagenBase64 = null;
    imagen.addEventListener("change", async () => {
      vista.replaceChildren();
      imagenBase64 = null;
      const archivo = imagen.files?.[0];
      if (!archivo) return;
      if (archivo.size > 2_000_000) { toastError({ message: "La imagen supera 2 MB." }); imagen.value = ""; return; }
      imagenBase64 = await leerComoDataURL(archivo);
      vista.append(h("img", { src: imagenBase64, alt: "Vista previa del comprobante", class: "preview-img" }));
    });
    const form = h("form", { class: "form", novalidate: true, id: "form-comprobante" },
      h("div", { class: "form-grid" },
        campo({ nombre: "banco_origen", etiqueta: "Banco de origen", requerido: true, attrs: { maxlength: "80", list: "bancos" } }),
        campo({ nombre: "numero_comprobante", etiqueta: "Número de comprobante o CUS", requerido: true, mono: true, attrs: { maxlength: "64", autocomplete: "off" } }),
        campo({ nombre: "fecha_hora", etiqueta: "Fecha y hora de la transferencia", tipo: "datetime-local", requerido: true, valor: isoLocalMinutos() }),
        campo({ nombre: "monto", etiqueta: "Monto transferido", tipo: "number", requerido: true, valor: Number(venta.total), attrs: { step: "0.01", min: "0.01" } }),
        campo({ nombre: "imagen", etiqueta: "Imagen del comprobante (opcional)", control: imagen, completo: true, ayuda: "PNG o JPG, máximo 2 MB." }),
        h("div", { class: "full" }, vista)),
      h("datalist", { id: "bancos" }, ["Bancolombia", "Nequi", "Daviplata", "Banco de Bogotá", "Davivienda", "BBVA", "Banco de Occidente", "Banco Popular", "Scotiabank Colpatria", "Banco Caja Social", "Nu"].map((b) => h("option", { value: b }))));
    const enviar = h("button", { type: "submit", class: "btn btn--primary", form: "form-comprobante" }, icon("upload", { size: 16 }), "Registrar comprobante");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      limpiarErrores(form);
      const v = valores(form);
      const errores = {};
      if (!v.banco_origen) errores.banco_origen = "Indica el banco.";
      if (!v.numero_comprobante || !/^[A-Za-z0-9-]{4,64}$/.test(v.numero_comprobante)) errores.numero_comprobante = "4 a 64 letras, dígitos o guiones.";
      if (!v.fecha_hora) errores.fecha_hora = "Indica la fecha y hora.";
      if (!(Number(v.monto) > 0)) errores.monto = "Monto no válido.";
      else if (Number(v.monto) !== Number(venta.total)) errores.monto = `Debe ser exactamente ${cop(venta.total)}; un monto distinto rechaza el pago.`;
      if (mostrarErrores(form, errores)) return;
      conBotonOcupado(enviar, async () => {
        try {
          const r = await post(`/ventas/${idventa}/pagos/comprobante`, {
            banco_origen: v.banco_origen, numero_comprobante: v.numero_comprobante, fecha_hora: v.fecha_hora,
            monto: Number(v.monto).toFixed(2), imagen_base64: imagenBase64,
          });
          if (r.estado === "RECHAZADO") await trasConfirmar(r);
          else { exito("Comprobante registrado. Falta la verificación."); await trasConfirmar(null); }
        } catch (err) { mostrarErrorApi(form, err); }
      });
    });
    return tarjeta({ titulo: "Comprobante de la transferencia", cuerpo: form, pie: enviar });
  }

  function verificacionManual(pago) {
    const monto = h("input", { type: "number", class: "input", step: "0.01", min: "0.01", id: "monto-verificado", value: String(Number(pago.comprobante_monto ?? venta.total)) });
    const aprobar = h("button", { type: "button", class: "btn btn--primary" }, icon("check", { size: 16 }), "Aprobar pago");
    const rechazar = h("button", { type: "button", class: "btn btn--danger" }, icon("x", { size: 16 }), "Rechazar");
    aprobar.addEventListener("click", () => conBotonOcupado(aprobar, async () => {
      if (!(Number(monto.value) > 0)) { toastError({ message: "Escribe el monto que ves en el banco." }); monto.focus(); return; }
      try {
        const r = await post(`/pagos/${pago.idpago}/verificar`, { aprobar: true, monto_verificado: Number(monto.value).toFixed(2) });
        await trasConfirmar(r);
      } catch (e) { toastError(e); }
    }));
    rechazar.addEventListener("click", async () => {
      const motivo = await confirmar({ titulo: "Rechazar comprobante", mensaje: "El pago quedará rechazado y deberás generar uno nuevo.", textoConfirmar: "Rechazar", peligro: true, pedirMotivo: true });
      if (!motivo) return;
      await conBotonOcupado(rechazar, async () => {
        try { await trasConfirmar(await post(`/pagos/${pago.idpago}/verificar`, { aprobar: false, motivo })); } catch (e) { toastError(e); }
      });
    });
    return tarjeta({
      titulo: "Verificar transferencia",
      cuerpo: h("div", { class: "stack" },
        callout("info", "Comprobante pendiente de verificación", "Confirma en el extracto o la app del banco que el dinero llegó antes de aprobar."),
        h("dl", { class: "dl" },
          h("dt", null, "Banco"), h("dd", null, pago.comprobante_banco),
          h("dt", null, "Comprobante / CUS"), h("dd", null, copiable(pago.comprobante_numero)),
          h("dt", null, "Fecha"), h("dd", null, fechaHora(pago.comprobante_fecha)),
          h("dt", null, "Monto declarado"), h("dd", null, cop(pago.comprobante_monto)),
          h("dt", null, "Registrado"), h("dd", null, fechaHora(pago.comprobante_registrado_en))),
        h("div", { class: "field" }, h("label", { class: "field__label", for: "monto-verificado" }, "Monto que ves en el banco"), monto,
          h("p", { class: "field__hint" }, "Si no coincide con el monto del pago, el sistema lo rechaza y lo marca como sospechoso.")),
        h("div", { class: "waiting" }, h("span", { class: "pulse" }), "Esperando verificación…")),
      pie: [rechazar, aprobar],
    });
  }

  // ----- WOMPI (transferencia o tarjeta)
  async function panelWompi(pago, contador) {
    montar(panel, tarjeta({ cuerpo: skeleton(6) }));
    const qr = await get(`/ventas/${idventa}/qr`, null, { signal: ctx.signal });
    const abrirPasarela = h("a", { class: "btn btn--primary btn--lg", href: qr.checkout_url, target: "_blank", rel: "noopener noreferrer" },
      icon("external", { size: 18 }), venta.metodo_pago === "TARJETA" ? "Pagar con tarjeta" : "Abrir pasarela de pago");
    montar(panel, tarjeta({
      titulo: venta.metodo_pago === "TARJETA" ? "Pago con tarjeta (Wompi)" : "Transferencia (Wompi)",
      cuerpo: h("div", { class: "grid grid--2" },
        h("div", { class: "qr-panel" }, qrDesdeBase64(qr.qr_png_base64, `Código QR de la pasarela de pago por ${cop(qr.monto)}`),
          contador, h("div", { class: "amount-hero__value" }, cop(qr.monto)), copiable(qr.referencia, { etiqueta: "Copiar referencia" })),
        h("div", { class: "stack" },
          h("ol", { class: "steps" },
            h("li", null, "El cliente escanea el QR con su celular o abres la pasarela en esta pantalla."),
            h("li", null, venta.metodo_pago === "TARJETA"
              ? "Los datos de la tarjeta se escriben solo en la pasarela segura de Wompi; nunca en este sistema."
              : "Elige Nequi, PSE, Bancolombia o Bre-B y confirma el pago."),
            h("li", null, "La confirmación llega sola: esta pantalla se actualiza al aprobarse.")),
          abrirPasarela,
          h("div", { class: "waiting", role: "status" }, h("span", { class: "pulse" }), "Esperando confirmación del banco…"))),
    }));
  }

  // ----- DATÁFONO
  function panelDatafono(pago, contador) {
    const form = h("form", { class: "form", novalidate: true, id: "form-datafono" },
      callout("info", null, "Registra los datos del voucher. Nunca escribas el número completo de la tarjeta ni el código de seguridad."),
      h("div", { class: "form-grid" },
        campo({ nombre: "codigo_autorizacion", etiqueta: "Código de aprobación", requerido: true, mono: true, attrs: { maxlength: "12", autocomplete: "off" } }),
        campo({ nombre: "ultimos4", etiqueta: "Últimos 4 dígitos", requerido: true, mono: true, attrs: { maxlength: "4", inputmode: "numeric", pattern: "\\d{4}", autocomplete: "off" } }),
        campo({ nombre: "franquicia", etiqueta: "Franquicia", tipo: "select", opciones: [["VISA", "Visa"], ["MASTERCARD", "Mastercard"], ["AMEX", "American Express"], ["DINERS", "Diners"], ["OTRA", "Otra"]] }),
        campo({ nombre: "tipo_tarjeta", etiqueta: "Tipo de tarjeta", tipo: "select", opciones: [["CREDITO", "Crédito"], ["DEBITO", "Débito"]] }),
        campo({ nombre: "recibo_numero", etiqueta: "Número de recibo", requerido: true, mono: true, attrs: { maxlength: "64", autocomplete: "off" } }),
        campo({ nombre: "monto", etiqueta: "Monto del voucher", tipo: "number", requerido: true, valor: Number(venta.total), attrs: { step: "0.01", min: "0.01" } })));
    const enviar = h("button", { type: "submit", class: "btn btn--primary btn--lg", form: "form-datafono" }, icon("check", { size: 18 }), "Registrar pago");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      limpiarErrores(form);
      const v = valores(form);
      const errores = {};
      if (!v.codigo_autorizacion || !/^[A-Za-z0-9]{4,12}$/.test(v.codigo_autorizacion)) errores.codigo_autorizacion = "4 a 12 letras o dígitos.";
      if (!/^\d{4}$/.test(v.ultimos4 ?? "")) errores.ultimos4 = "Exactamente 4 dígitos.";
      if (!v.recibo_numero || !/^[A-Za-z0-9-]{3,64}$/.test(v.recibo_numero)) errores.recibo_numero = "3 a 64 letras, dígitos o guiones.";
      if (!(Number(v.monto) > 0)) errores.monto = "Monto no válido.";
      if (mostrarErrores(form, errores)) return;
      conBotonOcupado(enviar, async () => {
        try {
          const r = await post(`/ventas/${idventa}/pagos/datafono`, { ...v, monto: Number(v.monto).toFixed(2) });
          await trasConfirmar(r);
        } catch (err) { mostrarErrorApi(form, err); }
      });
    });
    montar(panel, tarjeta({ titulo: "Pago con datáfono", acciones: contador, cuerpo: h("div", { class: "stack" },
      h("div", { class: "amount-hero" }, h("div", { class: "amount-hero__label" }, "Cobrar en el datáfono"), h("div", { class: "amount-hero__value" }, cop(venta.total))),
      form), pie: enviar }));
  }

  // ------------------------------------------------------------ éxito
  async function vistaExito() {
    montar(panel, tarjeta({ cuerpo: skeleton(8) }));
    const comprobante = await get(`/ventas/${idventa}/comprobante`, null, { signal: ctx.signal });
    const estadoFactura = h("div", { "aria-live": "polite" });
    const v = comprobante.verificacion;
    const filasVerificacion = [
      ["ID de transacción", v.proveedor_transaccion_id], ["Comprobante / CUS", v.comprobante_numero], ["Banco", v.comprobante_banco],
      ["Código de aprobación", v.codigo_autorizacion], ["Recibo", v.recibo_numero], ["Franquicia", v.tarjeta_franquicia],
      ["Tarjeta", v.tarjeta_ultimos4 && `•••• ${v.tarjeta_ultimos4}${v.tarjeta_tipo ? ` (${v.tarjeta_tipo.toLowerCase()})` : ""}`],
      ["Recibido", v.monto_recibido && cop(v.monto_recibido)], ["Cambio", v.cambio !== undefined && cop(v.cambio)],
    ].filter(([, valor]) => valor);

    const recibo = h("section", { class: "card print-area" },
      h("div", { class: "card__body stack" },
        h("div", { class: "no-print" }, h("div", { class: "success-mark", "aria-hidden": "true" }, icon("check", { size: 30 }))),
        h("div", { class: "amount-hero" },
          h("div", { class: "amount-hero__label" }, "Pago aprobado"),
          h("div", { class: "amount-hero__value" }, cop(comprobante.monto)),
          h("p", { class: "muted" }, comprobante.canal === "EFECTIVO"
            ? METODOS[comprobante.metodo_pago]
            : `${METODOS[comprobante.metodo_pago]} · ${CANALES[comprobante.canal] ?? comprobante.canal}`)),
        h("dl", { class: "dl" },
          h("dt", null, "Referencia de venta"), h("dd", null, copiable(comprobante.referencia)),
          h("dt", null, "Referencia de pago"), h("dd", null, h("span", { class: "mono" }, comprobante.referencia_pago)),
          h("dt", null, "Fecha y hora"), h("dd", null, fechaHora(comprobante.aprobado_en)),
          filasVerificacion.map(([k, valor]) => [h("dt", null, k), h("dd", null, valor)]),
          h("dt", null, "Verificado por"), h("dd", null, comprobante.verificado_por),
          h("dt", null, "Atendió"), h("dd", null, comprobante.trabajador?.nombre ?? "—"),
          h("dt", null, "Cliente"), h("dd", null, `${comprobante.cliente.names || comprobante.cliente.company} · `,
            h("span", { class: "mono" }, `${comprobante.cliente.identification}${comprobante.cliente.dv ? `-${comprobante.cliente.dv}` : ""}`))),
        h("hr", { class: "divider" }),
        h("div", { class: "table-wrap" }, h("table", { class: "table" },
          h("thead", null, h("tr", null, h("th", null, "Producto"), h("th", { class: "num" }, "Cant."), h("th", { class: "num" }, "Precio"), h("th", { class: "num" }, "IVA"), h("th", { class: "num" }, "Total"))),
          h("tbody", null, comprobante.items.map((it) => h("tr", null,
            h("td", null, it.nombre), h("td", { class: "num" }, numero(it.cantidad)), h("td", { class: "num" }, cop(it.precio_unitario)),
            h("td", { class: "num" }, it.is_excluded ? "Excl." : `${Number(it.tax_rate)} %`), h("td", { class: "num" }, cop(it.total))))))),
        h("div", { class: "totals" },
          h("div", { class: "totals__row" }, h("span", null, "Subtotal"), h("span", null, cop(comprobante.totales.subtotal))),
          Number(comprobante.totales.descuento_total) > 0 && h("div", { class: "totals__row" }, h("span", null, "Descuentos"), h("span", null, `− ${cop(comprobante.totales.descuento_total)}`)),
          comprobante.impuestos.filter((g) => Number(g.impuesto) > 0).map((g) => h("div", { class: "totals__row" }, h("span", null, `IVA ${Number(g.tax_rate)} %`), h("span", null, cop(g.impuesto)))),
          h("div", { class: "totals__row totals__row--total" }, h("span", null, "Total"), h("span", null, cop(comprobante.totales.total)))),
        estadoFactura),
      h("div", { class: "card__footer no-print" },
        h("button", { type: "button", class: "btn", onclick: () => window.print() }, icon("printer", { size: 16 }), "Imprimir comprobante"),
        h("a", { class: "btn btn--primary", href: "#/ventas/nueva" }, icon("plus", { size: 16 }), "Nueva venta")));
    montar(panel, recibo);
    pintarFactura(estadoFactura, comprobante.cliente);
  }

  async function pintarFactura(zona, cliente) {
    const emailCliente = cliente?.email;
    const f = venta.factura;
    if (!f || f.estado === "PENDIENTE" || f.estado === "PROCESANDO") {
      montar(zona, h("div", { class: "invoice-status" }, h("div", { class: "spinner" }),
        h("div", null, h("strong", null, "Emitiendo factura electrónica…"), h("p", { class: "cell-sub" }, "Factus la está validando ante la DIAN."))));
      let intentos = 0;
      const parar = cada(async () => {
        intentos += 1;
        try {
          const v = await get(`/ventas/${idventa}`, null, { signal: ctx.signal });
          venta = v;
          if (v.factura && !["PENDIENTE", "PROCESANDO"].includes(v.factura.estado)) { parar(); pintar(); }
          else if (intentos >= 40) {
            parar();
            const emitir = h("button", { type: "button", class: "btn btn--primary" }, icon("send", { size: 16 }), "Emitir factura");
            emitir.addEventListener("click", () => conBotonOcupado(emitir, async () => {
              try { await post(`/facturas/ventas/${idventa}/emitir`, {}, { timeout: CONFIG.TIMEOUT_FACTUS_MS }); await cargar(); pintar(); } catch (e) { toastError(e); }
            }));
            montar(zona, h("div", { class: "stack" }, callout("warning", "La factura aún no aparece", "Puede que la emisión automática no se haya iniciado. Emítela manualmente."), h("div", null, emitir)));
          }
        } catch (e) { if (e?.codigo !== "CANCELADO") console.warn(e); }
      }, CONFIG.POLL_FACTURA_MS);
      return;
    }
    if (f.estado === "EMITIDA" || f.estado === "ANULADA") {
      const pdf = h("button", { type: "button", class: "btn" }, icon("download", { size: 16 }), "Descargar PDF");
      pdf.addEventListener("click", () => descargarDocumento(f.idfactura, "pdf", pdf));
      const verBtn = h("button", { type: "button", class: "btn" }, icon("eye", { size: 16 }), "Ver PDF");
      verBtn.addEventListener("click", () => verPdf(f.idfactura, verBtn));
      montar(zona, h("div", { class: "stack" },
        callout("success", `Factura ${f.numero} emitida`, h("span", { class: "cufe" }, f.cufe)),
        h("div", { class: "row no-print" }, verBtn, pdf,
          h("button", { type: "button", class: "btn", onclick: () => enviarPorEmail(f.idfactura, emailCliente) }, icon("mail", { size: 16 }), "Enviar por email"),
          h("a", { class: "btn btn--ghost", href: `#/facturas/${f.idfactura}` }, "Ver factura"))));
      return;
    }
    // FALLIDA
    let errores = null;
    try { errores = (await get(`/facturas/${f.idfactura}`, null, { signal: ctx.signal })).errores; } catch { /* se muestra solo el mensaje */ }
    const reintentar = h("button", { type: "button", class: "btn btn--primary" }, icon("refresh", { size: 16 }), "Reintentar emisión");
    reintentar.addEventListener("click", async () => {
      const r = await reintentarFactura(f.idfactura, reintentar);
      if (r) { await cargar(); pintar(); }
    });
    montar(zona, h("div", { class: "stack" },
      callout("danger", "Factus/DIAN rechazó la factura", f.mensaje || "Revisa los datos del cliente y vuelve a intentarlo.", listaErrores(errores)),
      h("div", { class: "row no-print" }, reintentar,
        cliente && h("a", { class: "btn", href: `#/clientes?buscar=${encodeURIComponent(cliente.identification)}` }, "Revisar datos del cliente"))));
  }

  // ------------------------------------------------------------ cerrada
  function vistaCerrada() {
    const ultimo = venta.historial.at(-1);
    montar(panel, tarjeta({ cuerpo: vacio({
      icono: venta.estado === "CANCELADA" ? "ban" : "clock",
      titulo: venta.estado === "CANCELADA" ? "Venta cancelada" : "Venta expirada",
      texto: ultimo?.motivo || "El stock reservado ya se liberó.",
      accion: h("a", { class: "btn btn--primary", href: `#/ventas/nueva?repetir=${venta.idventa}` }, icon("refresh", { size: 16 }), "Nueva venta con estos productos"),
    }) }));
  }

  // ------------------------------------------------------------ acciones
  function cambiarMetodo() {
    const metodo = h("div", { class: "method-cards", role: "radiogroup", "aria-label": "Método de pago" },
      Object.entries(METODOS).map(([valor, texto]) => h("label", { class: "method-card" },
        h("input", { type: "radio", name: "metodo", value: valor, checked: venta.metodo_pago === valor }),
        icon({ EFECTIVO: "cash", TRANSFERENCIA: "bank", TARJETA: "card" }[valor], { size: 22 }), texto)));
    const canal = h("select", { class: "select", id: "regen-canal" });
    const opcionesCanal = { EFECTIVO: [], TRANSFERENCIA: [["", "Automático"], ["BREB_MANUAL", "Bre-B con comprobante"], ["WOMPI", "Pasarela Wompi"]], TARJETA: [["", "Automático"], ["DATAFONO", "Datáfono"], ["WOMPI", "Pasarela Wompi"]] };
    const zonaCanal = h("div", { class: "field" }, h("label", { class: "field__label", for: "regen-canal" }, "Canal"), canal);
    const pintarCanal = () => {
      const m = /** @type {HTMLInputElement} */ (metodo.querySelector("input:checked")).value;
      montar(canal, opcionesCanal[m].map(([v, t]) => h("option", { value: v }, t)));
      zonaCanal.hidden = !opcionesCanal[m].length;
    };
    metodo.addEventListener("change", pintarCanal);
    pintarCanal();
    const motivo = h("textarea", { class: "textarea", id: "regen-motivo", maxlength: "255" }, "El cliente cambió de método de pago");
    const form = h("form", { class: "form", id: "form-regen", novalidate: true },
      callout("info", null, "El pago actual se anula y se crea uno nuevo con referencia y firma nuevas. El total no cambia."),
      metodo, zonaCanal,
      h("div", { class: "field", dataset: { campo: "motivo" } }, h("label", { class: "field__label", for: "regen-motivo" }, "Motivo"), motivo, h("p", { class: "field__error" })));
    const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-regen" }, "Generar nuevo pago");
    const modal = abrirModal({ titulo: "Nuevo pago", contenido: form, acciones: [guardar] });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      limpiarErrores(form);
      const texto = motivo.value.trim();
      if (mostrarErrores(form, texto.length < 3 ? { motivo: "Escribe el motivo." } : {})) return;
      const m = /** @type {HTMLInputElement} */ (metodo.querySelector("input:checked")).value;
      conBotonOcupado(guardar, async () => {
        try {
          venta = await post(`/ventas/${idventa}/pagos/regenerar`, { metodoPago: m, canal: canal.value || null, motivo: texto });
          modal.cerrar();
          exito("Se generó un nuevo pago.");
          pintar();
        } catch (err) { mostrarErrorApi(form, err); }
      });
    });
  }

  async function cancelar() {
    const motivo = await confirmar({ titulo: "Cancelar venta", mensaje: "La venta se cancela, el pago pendiente se anula y el stock reservado se libera.", textoConfirmar: "Cancelar venta", peligro: true, pedirMotivo: true });
    if (!motivo) return;
    try {
      venta = await post(`/ventas/${idventa}/cancelar`, { motivo });
      aviso("Venta cancelada.");
      pintar();
    } catch (e) { toastError(e); }
  }

  await cargar();
  await pintar();
}
