/** Trabajadores (solo ADMIN): CRUD con rol, estado y cambio de contraseña. */
import { get, post, put, del } from "../api.js";
import { usuario } from "../auth.js";
import { h, conBotonOcupado } from "../components/dom.js";
import { icon } from "../components/icons.js";
import { abrirModal } from "../components/modal.js";
import { tablaDatos } from "../components/table.js";
import { campo, valores, limpiarErrores, mostrarErrores, mostrarErrorApi } from "../components/form.js";
import { badge, confirmar, encabezado, vacio, tarjeta } from "../components/ui.js";
import { exito, error as toastError } from "../components/toast.js";
import { fechaHora } from "../utils/format.js";
import { debounce, validar } from "../utils/helpers.js";

const TIPOS_DOC = [["13", "Cédula de ciudadanía"], ["22", "Cédula de extranjería"], ["41", "Pasaporte"], ["48", "PPT"], ["12", "Tarjeta de identidad"]];

function abrirFormulario(trabajador = null) {
  const editando = Boolean(trabajador);
  const t = trabajador ?? { tipo_documento: "13", rol: "TRABAJADOR", estado: "ACTIVO" };
  const form = h("form", { class: "form", novalidate: true, id: "form-trabajador" },
    h("div", { class: "form-grid" },
      campo({ nombre: "nombre", etiqueta: "Nombre completo", requerido: true, valor: t.nombre, completo: true, attrs: { maxlength: "120", autocomplete: "off" } }),
      campo({ nombre: "tipo_documento", etiqueta: "Tipo de documento", tipo: "select", valor: t.tipo_documento, opciones: TIPOS_DOC }),
      campo({ nombre: "documento", etiqueta: "Documento", requerido: true, valor: t.documento, mono: true, attrs: { maxlength: "20" } }),
      campo({ nombre: "email", etiqueta: "Correo (usuario de acceso)", tipo: "email", requerido: true, valor: t.email, attrs: { autocomplete: "off" } }),
      campo({ nombre: "telefono", etiqueta: "Teléfono", tipo: "tel", valor: t.telefono }),
      campo({ nombre: "rol", etiqueta: "Rol", tipo: "select", valor: t.rol, opciones: [["TRABAJADOR", "Trabajador"], ["ADMIN", "Administrador"]] }),
      campo({ nombre: "estado", etiqueta: "Estado", tipo: "select", valor: t.estado, opciones: [["ACTIVO", "Activo"], ["INACTIVO", "Inactivo"]] }),
      campo({ nombre: "password", etiqueta: editando ? "Nueva contraseña (opcional)" : "Contraseña", tipo: "password", requerido: !editando,
        ayuda: editando ? "Déjala vacía para no cambiarla. Mínimo 10 caracteres." : "Mínimo 10 caracteres.",
        attrs: { autocomplete: "new-password", minlength: "10", maxlength: "72" } }),
      campo({ nombre: "confirmar", etiqueta: "Confirmar contraseña", tipo: "password", requerido: !editando, attrs: { autocomplete: "new-password" } })));
  const guardar = h("button", { type: "submit", class: "btn btn--primary", form: "form-trabajador" }, icon("check", { size: 16 }), editando ? "Guardar cambios" : "Crear trabajador");
  const modal = abrirModal({ titulo: editando ? "Editar trabajador" : "Nuevo trabajador", contenido: form, acciones: [guardar], tamano: "lg" });
  let resultado = null;

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    limpiarErrores(form);
    const v = valores(form);
    const errores = {};
    if (!v.nombre || v.nombre.length < 3) errores.nombre = "Escribe el nombre completo.";
    if (!v.documento || !/^[0-9A-Za-z]{5,20}$/.test(v.documento)) errores.documento = "5 a 20 letras o dígitos.";
    if (!v.email || !validar.email(v.email)) errores.email = "Correo no válido.";
    if (!validar.telefono(v.telefono)) errores.telefono = "Solo dígitos (7 a 20).";
    if ((!editando || v.password) && (!v.password || v.password.length < 10)) errores.password = "Mínimo 10 caracteres.";
    if ((v.password || "") !== (v.confirmar || "")) errores.confirmar = "Las contraseñas no coinciden.";
    if (mostrarErrores(form, errores)) return;

    const { confirmar: _c, ...cuerpo } = v;
    if (editando && !cuerpo.password) delete cuerpo.password;
    conBotonOcupado(guardar, async () => {
      try {
        resultado = editando ? await put(`/trabajadores/${trabajador.idtrabajador}`, cuerpo) : await post("/trabajadores", cuerpo);
        exito(editando ? "Trabajador actualizado." : "Trabajador creado.");
        modal.cerrar();
      } catch (err) { mostrarErrorApi(form, err); }
    });
  });
  return modal.cerrado.then(() => resultado);
}

export default async function paginaTrabajadores(ctx) {
  const filtros = { buscar: "", rol: "", estado: "" };
  const yo = usuario();
  const buscar = h("input", { type: "search", class: "input", placeholder: "Nombre, documento o correo", "aria-label": "Buscar trabajadores" });
  const rol = h("select", { class: "select", "aria-label": "Rol" },
    h("option", { value: "" }, "Todos los roles"), h("option", { value: "ADMIN" }, "Administradores"), h("option", { value: "TRABAJADOR" }, "Trabajadores"));
  const estado = h("select", { class: "select", "aria-label": "Estado" },
    h("option", { value: "" }, "Todos los estados"), h("option", { value: "ACTIVO" }, "Activos"), h("option", { value: "INACTIVO" }, "Inactivos"));

  const tabla = tablaDatos({
    etiqueta: "Trabajadores",
    clave: (f) => f.idtrabajador,
    columnas: [
      { clave: "nombre", titulo: "Nombre", render: (f) => h("div", null, h("div", { class: "cell-main" }, f.nombre, f.idtrabajador === yo.idtrabajador && h("span", { class: "muted" }, " (tú)")), h("div", { class: "cell-sub" }, f.email)) },
      { clave: "documento", titulo: "Documento", render: (f) => h("span", { class: "mono" }, f.documento) },
      { clave: "telefono", titulo: "Teléfono", render: (f) => f.telefono || "—" },
      { clave: "rol", titulo: "Rol", render: (f) => badge(f.rol) },
      { clave: "estado", titulo: "Estado", render: (f) => badge(f.estado) },
      { clave: "ultimo_login_en", titulo: "Último ingreso", render: (f) => fechaHora(f.ultimo_login_en) },
    ],
    acciones: [
      { accion: "editar", icono: "edit", etiqueta: "Editar o cambiar contraseña" },
      { accion: "eliminar", icono: "trash", etiqueta: "Eliminar", visible: (f) => f.idtrabajador !== yo.idtrabajador },
    ],
    cargar: (p, signal) => get("/trabajadores", { page: p.page, page_size: p.page_size, ...filtros }, { signal }),
    alClic: (f) => editar(f),
    alAccion: (accion, f) => (accion === "editar" ? editar(f) : eliminar(f)),
    vacio: () => vacio({ icono: "badge", titulo: "Sin trabajadores", texto: "No hay trabajadores con esos filtros." }),
  });

  async function nuevo() { if (await abrirFormulario()) tabla.recargar(); }
  async function editar(f) { if (await abrirFormulario(f)) tabla.recargar(); }
  async function eliminar(f) {
    const ok = await confirmar({ titulo: "Eliminar trabajador", peligro: true, textoConfirmar: "Eliminar",
      mensaje: `${f.nombre} ya no podrá iniciar sesión. Sus ventas se conservan en el historial.` });
    if (!ok) return;
    try { await del(`/trabajadores/${f.idtrabajador}`); exito("Trabajador eliminado."); tabla.recargar(); } catch (e) { toastError(e); }
  }

  const aplicar = debounce(() => {
    Object.assign(filtros, { buscar: buscar.value.trim(), rol: rol.value, estado: estado.value });
    tabla.recargar({ reiniciar: true });
  }, 300);
  buscar.addEventListener("input", aplicar);
  rol.addEventListener("change", aplicar);
  estado.addEventListener("change", aplicar);
  ctx.alSalir(() => { aplicar.cancel(); tabla.abortar(); });

  ctx.root.append(
    encabezado("Trabajadores", "Cuentas de acceso y permisos.",
      h("button", { type: "button", class: "btn btn--primary", onclick: nuevo }, icon("plus", { size: 16 }), "Nuevo trabajador")),
    tarjeta({ flush: true, cuerpo: [
      h("div", { class: "table-toolbar" },
        h("div", { class: "field grow" }, h("div", { class: "input-icon" }, icon("search", { size: 17 }), buscar)),
        h("div", { class: "field" }, rol), h("div", { class: "field" }, estado)),
      tabla.el,
    ] }));
  tabla.recargar();
}
