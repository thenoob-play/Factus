// Configuración central del frontend.
// Modo demostración: abre cualquier página con ?demo=1 (datos de ejemplo, sin backend),
// ?demo=error (simula API caída), ?demo=vacio (simula sin datos) o ?demo=off para salir.
const CLAVE_DEMO = 'factus_demo';
const MODOS = ['ok', 'error', 'vacio'];

function leerModoDemo() {
    try {
        const valor = new URLSearchParams(window.location.search).get('demo');
        if (valor === 'off') sessionStorage.removeItem(CLAVE_DEMO);
        else if (valor !== null) sessionStorage.setItem(CLAVE_DEMO, MODOS.includes(valor) ? valor : 'ok');
        return sessionStorage.getItem(CLAVE_DEMO);
    } catch {
        return null;
    }
}

export const CONFIG = Object.freeze({
    // Flask sirve frontend y API en el mismo origen: dejar vacío.
    // Con Live Server (5500) pon aquí la URL de Flask y habilita CORS en el backend.
    apiBase: '',
    timeoutMs: 10000,
    demo: leerModoDemo(),
});
