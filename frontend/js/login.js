/** Pantalla de inicio de sesión (index.html). */
import { configurarApi } from "./api.js";
import { iniciarSesion, sesion } from "./auth.js";
import { conBotonOcupado, h } from "./components/dom.js";
import { icon } from "./components/icons.js";
import { callout } from "./components/ui.js";
import { iniciarTema, botonTema } from "./theme.js";
import { validar } from "./utils/helpers.js";

iniciarTema();
configurarApi({ token: () => null });

// Con sesión válida, directo a la app.
if (sesion()) window.location.replace("app.html#/");

const form = /** @type {HTMLFormElement} */ (document.getElementById("form-login"));
const email = /** @type {HTMLInputElement} */ (document.getElementById("email"));
const password = /** @type {HTMLInputElement} */ (document.getElementById("password"));
const verPassword = /** @type {HTMLButtonElement} */ (document.getElementById("ver-password"));
const boton = /** @type {HTMLButtonElement} */ (document.getElementById("entrar"));
const aviso = /** @type {HTMLElement} */ (document.getElementById("aviso"));

document.getElementById("tema").append(botonTema());
document.getElementById("logo-marca").append(icon("logo", { size: 20 }));
for (const [id, nombre] of [["f1", "key"], ["f2", "wallet"], ["f3", "invoice"]]) {
  document.getElementById(id).prepend(icon(nombre));
}

const motivo = new URLSearchParams(window.location.search).get("motivo");
if (motivo === "expirada") {
  aviso.append(callout("warning", "Tu sesión terminó", "Inicia sesión de nuevo para continuar."));
}

verPassword.append(icon("eye"));
verPassword.addEventListener("click", () => {
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  verPassword.replaceChildren(icon(visible ? "eye" : "eyeOff"));
  verPassword.setAttribute("aria-pressed", String(!visible));
  verPassword.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
});

function marcar(input, mensaje) {
  const campo = input.closest(".field");
  campo.classList.toggle("field--invalid", Boolean(mensaje));
  campo.querySelector(".field__error").textContent = mensaje || "";
  if (mensaje) input.setAttribute("aria-invalid", "true");
  else input.removeAttribute("aria-invalid");
}

const validarEmail = () => {
  const v = email.value.trim();
  marcar(email, !v ? "Escribe tu correo." : !validar.email(v) ? "El correo no es válido." : "");
  return Boolean(v) && validar.email(v);
};
const validarPassword = () => {
  marcar(password, password.value ? "" : "Escribe tu contraseña.");
  return Boolean(password.value);
};

// Validación en vivo después del primer intento o al salir del campo.
email.addEventListener("blur", () => { if (email.value) validarEmail(); });
email.addEventListener("input", () => { if (email.getAttribute("aria-invalid")) validarEmail(); });
password.addEventListener("input", () => { if (password.getAttribute("aria-invalid")) validarPassword(); });

form.addEventListener("submit", (e) => {
  e.preventDefault();
  aviso.replaceChildren();
  const ok = [validarEmail(), validarPassword()].every(Boolean);
  if (!ok) {
    (email.getAttribute("aria-invalid") ? email : password).focus();
    return;
  }
  conBotonOcupado(boton, async () => {
    try {
      await iniciarSesion(email.value.trim().toLowerCase(), password.value);
      window.location.replace("app.html#/");
    } catch (err) {
      const mensaje = err?.status === 401 ? "Correo o contraseña incorrectos."
        : err?.status === 429 ? "Demasiados intentos. Espera un minuto e inténtalo de nuevo."
          : err?.message || "No se pudo iniciar sesión.";
      aviso.replaceChildren(callout("danger", null, h("span", null, mensaje)));
      password.select();
      password.focus();
    }
  });
});
