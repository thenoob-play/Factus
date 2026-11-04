/** Productos: listado con filtros y alerta de stock bajo, formulario y ajuste de stock auditado. */
import { get, post, put, del } from "../api.js";
import { CATALOGOS } from "../config.js";
import { h, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { tablaDatos } from "../components/table.js";
import { combobox } from "../components/combobox.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { badge, confirmar, encabezado, vacio, tarjeta } from "../components/ui.js";
import { exito, error as toastError } from "../components/toast.js";
import { cop, numero } from "../utils/format.js";
import { debounce } from "../utils/helpers.js";
import { fijarQuery } from "../router.js";

/** Unidades: catálogo de Factus si está sincronizado; si no, las más comunes. */
async function buscarUnidades(texto, signal) {
  let lista = [];
  try {
    const r = await get("/catalogos/factus/unidades_medida", { buscar: texto }, { signal });
    lista = r.datos.map((u) => ({ valor: u.code, etiqueta: u.name, sub: `Código ${u.code}` }));
  } catch (e) {
    if (e?.codigo === "CANCELADO") throw e;
  }
  if (!lista.length) {
    const t = texto.toLowerCase();
    lista = CATALOGOS.unidadesComunes
      .filter(([c, n]) => !t || n.toLowerCase().includes(t) || c.toLowerCase() === t)
      .map(([c, n]) => ({ valor: c, etiqueta: n, sub: `Código ${c}` }));
  }
  return lista.slice(0, 30);
}

const nombreUnidad = (codigo) => CATALOGOS.unidadesComunes.find(([c]) => c === codigo)?.[1] ?? `Código ${codigo}`;

function abrirFormularioProducto(producto = null) {
  const editando = Boolean(producto);
  const p = producto ?? { tax_rate: "19", tax_code: "01", unit_measure_code: "94", standard_code: "999", discount_rate: "0", stock: 0, stock_minimo: 0, estado: "ACTIVO" };

  const unidad = combobox({
    nombre: "unit_measure_code", buscar: buscarUnidades, minimo: 0, placeholder: "Buscar unidad…",
    inicial: { valor: p.unit_measure_code, etiqueta: nombreUnidad(p.unit_measure_code) },
  });
  const excluido = h("input", { type: "checkbox", name: "is_excluded", checked: Boolean(p.is_excluded) });
  const iva = campo({ nombre: "tax_rate", etiqueta: "Tarifa de IVA", tipo: "select", valor: String(Number(p.tax_rate)),
    opciones: [["19", "19 %"], ["5", "5 %"], ["0", "0 %"]] });
  const estandar = campo({ nombre: "standard_code", etiqueta: "Estándar del código", tipo: "select", valor: p.standard_code,
    opciones: [["999", "Código propio"], ["001", "UNSPSC"], ["010", "GTIN (código de barras)"], ["020", "Partida arancelaria"]] });
  const unspsc = campo({ nombre: "codigo_unspsc", etiqueta: "Código UNSPSC", valor: p.codigo_unspsc || "", mono: true, requerido: true,
    ayuda: "8 dígitos, p. ej. 43211503.", attrs: { inputmode: "numeric", maxlength: "8" } });

  const form = h("form", { class: "form", novalidate: true, id: "form-producto" },
    h("div", { class: "form-grid" },
      campo({ nombre: "code_reference", etiqueta: "Código de referencia", requerido: true, valor: p.code_reference, mono: true, ayuda: "Único. Letras, números, punto, guion.", attrs: { maxlength: "50", autocomplete: "off" } }),
      campo({ nombre: "nombre", etiqueta: "Nombre", requerido: true, valor: p.nombre, attrs: { maxlength: "100" } }),
      campo({ nombre: "descripcion", etiqueta: "Descripción", tipo: "textarea", valor: p.descripcion, completo: true, attrs: { maxlength: "255" } }),
      campo({ nombre: "precio_unitario", etiqueta: "Precio unitario (sin IVA)", tipo: "number", requerido: true, valor: p.precio_unitario, ayuda: "Precio neto; el IVA se suma al facturar.", attrs: { min: "0.01", step: "0.01", inputmode: "decimal" } }),
      campo({ nombre: "discount_rate", etiqueta: "Descuento (%)", tipo: "number", valor: Number(p.discount_rate), attrs: { min: "0", max: "100", step: "0.01" } }),
      iva,
      campo({ nombre: "tax_code", etiqueta: "Tributo", tipo: "select", valor: p.tax_code, opciones: [["01", "IVA"], ["04", "INC (impuesto al consumo)"]] }),
      h("div", { class: "field full" }, h("label", { class: "check" }, excluido, "Excluido de IVA (bienes y servicios excluidos por ley)")),
      campo({ nombre: "unit_measure_code", etiqueta: "Unidad de medida", control: unidad.el }),
      estandar, unspsc,
      editando
        ? h("div", { class: "field" }, h("span", { class: "field__label" }, "Stock actual"), h("p", { class: "input" }, numero(p.stock)), h("p", { class: "field__hint" }, "Cámbialo con “Ajustar stock”."))
        : campo({ nombre: "stock", etiqueta: "Stock inicial", tipo: "number", valor: 0, attrs: { min: "0", step: "1" } }),
      campo({ nombre: "stock_minimo", etiqueta: "Stock mínimo (alerta)", tipo: "number", valor: p.stock_minimo, attrs: { min: "0", step: "1" } }),
      editando && campo({ nombre: "estado", etiqueta: "Estado", tipo: "select", valor: p.estado, opciones: [["ACTIVO", "Activo"], ["INACTIVO", "Inactivo"]] })));

  const selIva = /** @type {HTMLSelectElement} */ (iva.querySelector("select"));
  const selEstandar = /** @type {HTMLSelectElement} */ (estandar.querySelector("select"));
  const sincronizar = () => {
    if (excluido.checked) selIva.value = "0";
    selIva.disabled = excluido.checked;
    unspsc.hidden = selEstandar.value !== "001";
  };
  excluido.addEventListener("change", sincronizar);
  selEstandar.addEventListener("change", sincronizar);
  sincronizar();

  const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-producto" }, icon("check", { size: 16 }), editando ? "Guardar cambios" : "Crear producto");
  const modal = abrirModal({ titulo: editando ? "Editar producto" : "Nuevo producto", contenido: form, acciones: [guardar], tamano: "lg" });
  let resultado = null;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const v = valores(form);
    const errores = {};
    if (!v.code_reference || !/^[A-Za-z0-9._-]{2,50}$/.test(v.code_reference)) errores.code_reference = "2 a 50 caracteres: letras, números, punto o guion.";
    if (!v.nombre || v.nombre.length < 2) errores.nombre = "Escribe el nombre.";
    if (!(Number(v.precio_unitario) > 0)) errores.precio_unitario = "Debe ser mayor que 0.";
    const desc = Number(v.discount_rate ?? 0);
    if (!(desc >= 0 && desc <= 100)) errores.discount_rate = "Entre 0 y 100.";
    if (!unidad.valor) errores.unit_measure_code = "Elige la unidad de medida.";
    if (v.standard_code === "001" && !/^\d{8}$/.test(v.codigo_unspsc ?? "")) errores.codigo_unspsc = "Deben ser 8 dígitos.";
    if (mostrarErrores(form, errores)) return;

    const cuerpo = {
      code_reference: v.code_reference,
      nombre: v.nombre,
      descripcion: v.descripcion,
      precio_unitario: Number(v.precio_unitario).toFixed(2),
      stock: editando ? undefined : Number(v.stock ?? 0),
      stock_minimo: Number(v.stock_minimo ?? 0),
      tax_rate: excluido.checked ? 0 : Number(selIva.value),
      is_excluded: excluido.checked,
      tax_code: v.tax_code,
      unit_measure_code: unidad.valor,
      standard_code: v.standard_code,
      codigo_unspsc: v.standard_code === "001" ? v.codigo_unspsc : null,
      discount_rate: desc.toFixed(2),
      estado: v.estado ?? "ACTIVO",
      // Se conservan los campos que esta pantalla no edita.
      idcategoria: producto?.idcategoria ?? null,
      url_imagen: producto?.url_imagen ?? null,
    };
    conBotonOcupado(guardar, async () => {
      try {
        resultado = editando ? await put(`/productos/${producto.idproducto}`, cuerpo) : await post("/productos", cuerpo);
        exito(editando ? "Producto actualizado." : "Producto creado.");
        modal.cerrar();
      } catch (err) {
        mostrarErrorApi(form, err);
      }
    });
  });
  return modal.cerrado.then(() => resultado);
}

function ajustarStock(producto) {
  const form = h("form", { class: "form", novalidate: true, id: "form-stock" },
    h("p", { class: "text-2" }, `${producto.nombre} — stock actual `, h("strong", null, numero(producto.stock)),
      producto.stock_reservado > 0 ? `, ${numero(producto.stock_reservado)} reservadas en ventas pendientes.` : "."),
    campo({ nombre: "delta", etiqueta: "Unidades a sumar o restar", tipo: "number", requerido: true, ayuda: "Ej.: 20 para una entrada, -3 para una baja por daño.", attrs: { step: "1" } }),
    campo({ nombre: "motivo", etiqueta: "Motivo", requerido: true, tipo: "textarea", attrs: { maxlength: "255" } }));
  const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-stock" }, "Aplicar ajuste");
  const modal = abrirModal({ titulo: "Ajustar stock", contenido: form, acciones: [guardar] });
  let ok = false;
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const v = valores(form);
    const delta = Number(v.delta);
    const errores = {};
    if (!Number.isInteger(delta) || delta === 0) errores.delta = "Escribe un entero distinto de 0.";
    if (!v.motivo || v.motivo.length < 3) errores.motivo = "Explica el motivo del ajuste.";
    if (mostrarErrores(form, errores)) return;
    conBotonOcupado(guardar, async () => {
      try {
        await post(`/productos/${producto.idproducto}/stock`, { delta, motivo: v.motivo });
        ok = true;
        exito("Stock ajustado.");
        modal.cerrar();
      } catch (err) { mostrarErrorApi(form, err); }
    });
  });
  return modal.cerrado.then(() => ok);
}

export default async function paginaProductos(ctx) {
  const filtros = { buscar: ctx.query.get("buscar") ?? "", estado: "", stock_bajo: ctx.query.get("stock_bajo") === "1" };

  const buscar = h("input", { type: "search", class: "input", placeholder: "Nombre o código", value: filtros.buscar, "aria-label": "Buscar productos" });
  const estado = h("select", { class: "select", "aria-label": "Estado" },
    h("option", { value: "" }, "Todos los estados"), h("option", { value: "ACTIVO" }, "Activos"), h("option", { value: "INACTIVO" }, "Inactivos"));
  const bajo = h("input", { type: "checkbox", checked: filtros.stock_bajo });

  const tabla = tablaDatos({
    etiqueta: "Productos",
    clave: (f) => f.idproducto,
    orden: { clave: "nombre", desc: false },
    columnas: [
      { clave: "code_reference", titulo: "Código", ordenable: true, render: (f) => h("span", { class: "mono" }, f.code_reference) },
      { clave: "nombre", titulo: "Producto", ordenable: true, render: (f) => h("div", null,
        h("div", { class: "cell-main" }, f.nombre), f.descripcion && h("div", { class: "cell-sub" }, f.descripcion)) },
      { clave: "precio_unitario", titulo: "Precio", ordenable: true, num: true, render: (f) => cop(f.precio_unitario) },
      { clave: "tax_rate", titulo: "IVA", ordenable: true, render: (f) => (f.is_excluded ? badge(null, "Excluido") : `${Number(f.tax_rate)} %`) },
      { clave: "stock", titulo: "Disponible", ordenable: true, num: true, render: (f) => h("div", null,
        f.stock_bajo
          ? h("span", { class: "badge badge--warning", title: `Mínimo: ${numero(f.stock_minimo)}` }, `${numero(f.stock_disponible)} · bajo`)
          : numero(f.stock_disponible),
        f.stock_reservado > 0 && h("div", { class: "cell-sub" }, `${numero(f.stock_reservado)} reservadas`)) },
      { clave: "estado", titulo: "Estado", ordenable: true, render: (f) => badge(f.estado) },
    ],
    acciones: [
      { accion: "stock", icono: "stack", etiqueta: "Ajustar stock" },
      { accion: "editar", icono: "edit", etiqueta: "Editar" },
      { accion: "eliminar", icono: "trash", etiqueta: "Eliminar" },
    ],
    cargar: (p, signal) => get("/productos", { ...p, buscar: filtros.buscar, estado: filtros.estado, stock_bajo: filtros.stock_bajo || null }, { signal }),
    alClic: (f) => editar(f),
    alAccion: (accion, f) => ({ stock: async () => { if (await ajustarStock(f)) tabla.recargar(); }, editar: () => editar(f), eliminar: () => eliminar(f) })[accion](),
    vacio: () => vacio({
      icono: "box", titulo: filtros.buscar || filtros.stock_bajo ? "Sin coincidencias" : "Aún no hay productos",
      texto: filtros.stock_bajo ? "Ningún producto está por debajo de su stock mínimo." : "Registra productos para empezar a vender.",
      accion: h("button", { type: "button", class: "btn btn--primary", onclick: () => nuevo() }, icon("plus", { size: 16 }), "Nuevo producto"),
    }),
  });

  async function nuevo() { if (await abrirFormularioProducto()) tabla.recargar(); }
  async function editar(f) { if (await abrirFormularioProducto(f)) tabla.recargar(); }
  async function eliminar(f) {
    const ok = await confirmar({ titulo: "Eliminar producto", peligro: true, textoConfirmar: "Eliminar",
      mensaje: `“${f.nombre}” dejará de estar disponible para la venta. Las ventas anteriores no cambian.` });
    if (!ok) return;
    try {
      await del(`/productos/${f.idproducto}`);
      exito("Producto eliminado.");
      tabla.recargar();
    } catch (e) { toastError(e); }
  }

  const aplicar = debounce(() => {
    filtros.buscar = buscar.value.trim();
    filtros.estado = estado.value;
    filtros.stock_bajo = bajo.checked;
    fijarQuery({ buscar: filtros.buscar, stock_bajo: filtros.stock_bajo ? "1" : null });
    tabla.recargar({ reiniciar: true });
  }, 300);
  buscar.addEventListener("input", aplicar);
  estado.addEventListener("change", aplicar);
  bajo.addEventListener("change", aplicar);
  ctx.alSalir(() => { aplicar.cancel(); tabla.abortar(); });

  ctx.root.append(
    encabezado("Productos", "Precios, impuestos y existencias.",
      h("button", { type: "button", class: "btn btn--primary", onclick: nuevo }, icon("plus", { size: 16 }), "Nuevo producto")),
    tarjeta({ flush: true, cuerpo: [
      h("div", { class: "table-toolbar" },
        h("div", { class: "field grow" }, h("div", { class: "input-icon" }, icon("search", { size: 17 }), buscar)),
        h("div", { class: "field" }, estado),
        h("label", { class: "switch" }, bajo, "Solo stock bajo")),
      tabla.el,
    ] }));
  tabla.recargar();
}
