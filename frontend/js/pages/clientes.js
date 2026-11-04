/** Clientes: listado con búsqueda y orden, formulario alineado con Factus y detalle con facturas. */
import { get, post, put, del } from "../api.js";
import { CATALOGOS } from "../config.js";
import { h, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { tablaDatos } from "../components/table.js";
import { combobox } from "../components/combobox.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { badge, confirmar, encabezado, vacio, cargando, tarjeta } from "../components/ui.js";
import { exito, error as toastError } from "../components/toast.js";
import { cop, fecha } from "../utils/format.js";
import { debounce, dvNit, validar } from "../utils/helpers.js";
import { fijarQuery } from "../router.js";

const nombreTipoDoc = (codigo) => CATALOGOS.tiposDocumento.find(([c]) => c === codigo)?.[1] ?? codigo;
export const nombreCliente = (c) => c.names || c.company || "—";
export const documentoCliente = (c) => `${c.identification}${c.dv ? `-${c.dv}` : ""}`;

/** Busca municipios en el catálogo sincronizado del backend. */
async function buscarMunicipios(texto, signal) {
  const r = await get("/catalogos/factus/municipios", { buscar: texto }, { signal });
  return r.datos.slice(0, 30).map((m) => ({
    valor: m.code,
    etiqueta: m.name,
    sub: [typeof m.department === "object" ? m.department?.name : m.department, `Código ${m.code}`].filter(Boolean).join(" · "),
  }));
}

/**
 * Formulario de cliente en un modal. Devuelve el cliente guardado o null.
 * @param {any} [cliente] para editar
 * @returns {Promise<any|null>}
 */
export function abrirFormularioCliente(cliente = null) {
  const editando = Boolean(cliente);
  const c = cliente ?? { identification_document_code: "13", legal_organization_code: "2", tribute_code: "ZZ", estado: "ACTIVO" };

  const tipoDoc = campo({ nombre: "identification_document_code", etiqueta: "Tipo de documento", tipo: "select", requerido: true, valor: c.identification_document_code, opciones: CATALOGOS.tiposDocumento });
  const ident = campo({ nombre: "identification", etiqueta: "Número de documento", requerido: true, valor: c.identification, mono: true, attrs: { inputmode: "text", maxlength: "20", autocomplete: "off" } });
  const dv = campo({ nombre: "dv", etiqueta: "DV", valor: c.dv, mono: true, attrs: { readonly: true, tabindex: "-1", title: "Dígito de verificación, calculado automáticamente" } });

  const radioOrg = (valor, texto) => h("label", null, h("input", { type: "radio", name: "legal_organization_code", value: valor, checked: c.legal_organization_code === valor }), texto);
  const org = h("div", { class: "field full", dataset: { campo: "legal_organization_code" } },
    h("span", { class: "field__label", id: "lbl-org" }, "Tipo de persona"),
    h("div", { class: "segmented", role: "radiogroup", "aria-labelledby": "lbl-org" }, radioOrg("2", "Persona natural"), radioOrg("1", "Persona jurídica")),
    h("p", { class: "field__error" }));

  const names = campo({ nombre: "names", etiqueta: "Nombres y apellidos", requerido: true, valor: c.names, completo: true, attrs: { maxlength: "150", autocomplete: "name" } });
  const company = campo({ nombre: "company", etiqueta: "Razón social", requerido: true, valor: c.company, attrs: { maxlength: "150", autocomplete: "organization" } });
  const tradeName = campo({ nombre: "trade_name", etiqueta: "Nombre comercial", valor: c.trade_name, attrs: { maxlength: "150" } });

  const muni = combobox({
    nombre: "municipality_code", placeholder: "Escribe el municipio…", buscar: buscarMunicipios, minimo: 2,
    inicial: c.municipality_code ? { valor: c.municipality_code, etiqueta: `Código ${c.municipality_code}` } : null,
    vacioTexto: "Sin resultados. Si el catálogo está vacío, un administrador debe sincronizarlo en Reportes.",
  });

  const form = h("form", { class: "form", novalidate: true, id: "form-cliente" },
    h("div", { class: "form-grid" },
      tipoDoc, h("div", { class: "doc-grid" }, ident, dv),
      org, names, company, tradeName,
      campo({ nombre: "tribute_code", etiqueta: "Responsabilidad tributaria", tipo: "select", valor: c.tribute_code, opciones: CATALOGOS.tributos }),
      campo({ nombre: "email", etiqueta: "Correo electrónico", tipo: "email", valor: c.email, ayuda: "Allí llega la factura electrónica.", attrs: { autocomplete: "email" } }),
      campo({ nombre: "phone", etiqueta: "Teléfono", tipo: "tel", valor: c.phone, attrs: { autocomplete: "tel" } }),
      campo({ nombre: "address", etiqueta: "Dirección", valor: c.address, attrs: { autocomplete: "street-address" } }),
      campo({ nombre: "municipality_code", etiqueta: "Municipio", control: muni.el, completo: true }),
      editando && campo({ nombre: "estado", etiqueta: "Estado", tipo: "select", valor: c.estado, opciones: [["ACTIVO", "Activo"], ["INACTIVO", "Inactivo"]] })));

  const inputTipo = /** @type {HTMLSelectElement} */ (tipoDoc.querySelector("select"));
  const inputIdent = /** @type {HTMLInputElement} */ (ident.querySelector("input"));
  const inputDv = /** @type {HTMLInputElement} */ (dv.querySelector("input"));

  function actualizar() {
    const esNit = inputTipo.value === "31";
    dv.hidden = !esNit;
    inputDv.value = esNit ? (dvNit(inputIdent.value) ?? "") : "";
    const juridica = form.querySelector("input[name=legal_organization_code]:checked")?.value === "1";
    names.hidden = juridica;
    company.hidden = !juridica;
    tradeName.hidden = !juridica;
    names.querySelector("input").disabled = juridica;
    company.querySelector("input").disabled = !juridica;
    tradeName.querySelector("input").disabled = !juridica;
  }
  inputTipo.addEventListener("change", () => {
    // NIT suele ser persona jurídica: se sugiere, pero el usuario puede cambiarlo.
    if (inputTipo.value === "31") /** @type {HTMLInputElement} */ (form.querySelector("input[name=legal_organization_code][value='1']")).checked = true;
    actualizar();
  });
  inputIdent.addEventListener("input", actualizar);
  form.addEventListener("change", (e) => { if (/** @type {HTMLInputElement} */ (e.target).name === "legal_organization_code") actualizar(); });
  actualizar();

  const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-cliente" }, icon("check", { size: 16 }), editando ? "Guardar cambios" : "Crear cliente");
  const modal = abrirModal({ titulo: editando ? "Editar cliente" : "Nuevo cliente", contenido: form, acciones: [guardar], tamano: "lg" });
  let resultado = null;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const v = valores(form);
    const errores = {};
    if (!v.identification) errores.identification = "Escribe el número de documento.";
    else if (v.identification_document_code === "31" && !/^\d{3,15}$/.test(v.identification)) errores.identification = "El NIT lleva solo dígitos, sin DV ni guion.";
    if (v.legal_organization_code === "2" && !v.names) errores.names = "Escribe el nombre.";
    if (v.legal_organization_code === "1" && !v.company) errores.company = "Escribe la razón social.";
    if (!validar.email(v.email)) errores.email = "El correo no es válido.";
    if (!validar.telefono(v.phone)) errores.phone = "Usa solo dígitos (7 a 20).";
    if (v.address && v.address.length < 5) errores.address = "La dirección es muy corta.";
    if (mostrarErrores(form, errores)) return;

    const cuerpo = {
      identification_document_code: v.identification_document_code,
      identification: v.identification,
      dv: v.identification_document_code === "31" ? v.dv : null,
      legal_organization_code: v.legal_organization_code,
      tribute_code: v.tribute_code,
      names: v.legal_organization_code === "2" ? v.names : null,
      company: v.legal_organization_code === "1" ? v.company : null,
      trade_name: v.legal_organization_code === "1" ? v.trade_name : null,
      email: v.email, phone: v.phone, address: v.address,
      municipality_code: muni.valor,
      estado: v.estado ?? "ACTIVO",
    };
    conBotonOcupado(guardar, async () => {
      try {
        resultado = editando ? await put(`/clientes/${cliente.idcliente}`, cuerpo) : await post("/clientes", cuerpo);
        exito(editando ? "Cliente actualizado." : "Cliente creado.");
        modal.cerrar(resultado);
      } catch (err) {
        mostrarErrorApi(form, err);
      }
    });
  });
  return modal.cerrado.then(() => resultado);
}

/** Detalle del cliente con sus últimas facturas. */
function verCliente(cliente, alEditar) {
  const facturas = h("div", null, cargando("Cargando facturas…"));
  const modal = abrirModal({
    titulo: nombreCliente(cliente), tamano: "lg",
    contenido: h("div", { class: "stack" },
      h("dl", { class: "dl" },
        h("dt", null, "Documento"), h("dd", null, `${nombreTipoDoc(cliente.identification_document_code)} · `, h("span", { class: "mono" }, documentoCliente(cliente))),
        h("dt", null, "Tipo"), h("dd", null, cliente.legal_organization_code === "1" ? "Persona jurídica" : "Persona natural"),
        cliente.trade_name && [h("dt", null, "Nombre comercial"), h("dd", null, cliente.trade_name)],
        h("dt", null, "Correo"), h("dd", null, cliente.email || "—"),
        h("dt", null, "Teléfono"), h("dd", null, cliente.phone || "—"),
        h("dt", null, "Dirección"), h("dd", null, cliente.address || "—"),
        h("dt", null, "Municipio"), h("dd", null, cliente.municipality_code ? h("span", { class: "mono" }, cliente.municipality_code) : "—"),
        h("dt", null, "Estado"), h("dd", null, badge(cliente.estado))),
      h("h3", null, "Facturas recientes"), facturas),
    acciones: [
      h("a", { class: "btn", href: `#/facturas?idcliente=${cliente.idcliente}` }, icon("invoice", { size: 16 }), "Ver todas las facturas"),
      h("button", { type: "button", class: "btn btn--primary", onclick: () => { modal.cerrar(); alEditar(cliente); } }, icon("edit", { size: 16 }), "Editar"),
    ],
  });
  get(`/facturas/cliente/${cliente.idcliente}`, { page_size: 8 }).then((r) => {
    facturas.replaceChildren(r.items.length
      ? h("ul", { class: "list-plain card" }, r.items.map((f) => h("li", null,
        h("a", { href: `#/facturas/${f.idfactura}`, onclick: () => modal.cerrar() },
          h("div", { class: "cell-main mono" }, f.numero || f.reference_code),
          h("div", { class: "cell-sub" }, fecha(f.creado_en))),
        h("div", { class: "row" }, h("strong", null, cop(f.total)), badge(f.estado)))))
      : vacio({ icono: "invoice", titulo: "Sin facturas", texto: "Este cliente aún no tiene facturas." }));
  }).catch((e) => facturas.replaceChildren(h("p", { class: "muted" }, e.message)));
}

export default async function paginaClientes(ctx) {
  const filtros = { buscar: ctx.query.get("buscar") ?? "", estado: "" };

  const buscar = h("input", { type: "search", class: "input", placeholder: "Nombre, documento o email", value: filtros.buscar, "aria-label": "Buscar clientes" });
  const estado = h("select", { class: "select", "aria-label": "Estado" },
    h("option", { value: "" }, "Todos los estados"), h("option", { value: "ACTIVO" }, "Activos"), h("option", { value: "INACTIVO" }, "Inactivos"));

  const tabla = tablaDatos({
    etiqueta: "Clientes",
    clave: (f) => f.idcliente,
    orden: { clave: "nombre", desc: false },
    columnas: [
      { clave: "nombre", titulo: "Cliente", ordenable: true, render: (f) => h("div", null,
        h("div", { class: "cell-main" }, nombreCliente(f)),
        h("div", { class: "cell-sub" }, f.legal_organization_code === "1" ? "Persona jurídica" : "Persona natural")) },
      { clave: "identification", titulo: "Documento", ordenable: true, render: (f) => h("div", null,
        h("div", { class: "mono" }, documentoCliente(f)), h("div", { class: "cell-sub" }, nombreTipoDoc(f.identification_document_code))) },
      { clave: "email", titulo: "Correo", ordenable: true, render: (f) => f.email || "—" },
      { clave: "phone", titulo: "Teléfono", render: (f) => f.phone || "—" },
      { clave: "estado", titulo: "Estado", ordenable: true, render: (f) => badge(f.estado) },
    ],
    acciones: [
      { accion: "ver", icono: "eye", etiqueta: "Ver detalle" },
      { accion: "editar", icono: "edit", etiqueta: "Editar" },
      { accion: "eliminar", icono: "trash", etiqueta: "Eliminar" },
    ],
    cargar: (p, signal) => get("/clientes", { ...p, buscar: filtros.buscar, estado: filtros.estado }, { signal }),
    alClic: (f) => verCliente(f, editar),
    alAccion: (accion, f) => ({ ver: () => verCliente(f, editar), editar: () => editar(f), eliminar: () => eliminar(f) })[accion](),
    vacio: () => vacio({
      icono: "users", titulo: filtros.buscar ? "Sin coincidencias" : "Aún no hay clientes",
      texto: filtros.buscar ? "Prueba con otro nombre, documento o correo." : "Crea tu primer cliente para poder facturar.",
      accion: h("button", { type: "button", class: "btn btn--primary", onclick: () => nuevo() }, icon("plus", { size: 16 }), "Nuevo cliente"),
    }),
  });

  async function nuevo() { if (await abrirFormularioCliente()) tabla.recargar(); }
  async function editar(f) { if (await abrirFormularioCliente(f)) tabla.recargar(); }
  async function eliminar(f) {
    const ok = await confirmar({
      titulo: "Eliminar cliente", peligro: true, textoConfirmar: "Eliminar",
      mensaje: `${nombreCliente(f)} dejará de aparecer en las búsquedas. Sus ventas y facturas se conservan.`,
    });
    if (!ok) return;
    try {
      await del(`/clientes/${f.idcliente}`);
      exito("Cliente eliminado.");
      tabla.recargar();
    } catch (e) { toastError(e); }
  }

  const aplicar = debounce(() => {
    filtros.buscar = buscar.value.trim();
    filtros.estado = estado.value;
    fijarQuery({ buscar: filtros.buscar });
    tabla.recargar({ reiniciar: true });
  }, 300);
  buscar.addEventListener("input", aplicar);
  estado.addEventListener("change", aplicar);
  ctx.alSalir(() => { aplicar.cancel(); tabla.abortar(); });

  ctx.root.append(
    encabezado("Clientes", "Datos de facturación electrónica de tus clientes.",
      h("button", { type: "button", class: "btn btn--primary", onclick: nuevo }, icon("plus", { size: 16 }), "Nuevo cliente")),
    tarjeta({ flush: true, cuerpo: [
      h("div", { class: "table-toolbar" },
        h("div", { class: "field grow" }, h("div", { class: "input-icon" }, icon("search", { size: 17 }), buscar)),
        h("div", { class: "field" }, estado)),
      tabla.el,
    ] }));
  tabla.recargar();
}
