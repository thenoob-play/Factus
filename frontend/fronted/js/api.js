// Capa de acceso a la API. Ninguna página usa fetch() directamente.
import { CONFIG } from './config.js';

export class ApiError extends Error {
    constructor(mensaje, { estado = 0, detalle = null } = {}) {
        super(mensaje);
        this.name = 'ApiError';
        this.estado = estado;
        this.detalle = detalle;
    }
}

const mensajePorEstado = (estado) => {
    if (estado === 400) return 'La solicitud no es válida.';
    if (estado === 404) return 'No se encontró el recurso solicitado.';
    if (estado >= 500) return 'El servidor tuvo un problema. Inténtalo de nuevo en unos minutos.';
    return `Respuesta inesperada del servidor (${estado}).`;
};

// Mensaje seguro para mostrar al usuario.
export const mensajeDe = (error) =>
    error instanceof ApiError ? error.message : 'Recibimos datos con un formato inesperado.';

async function solicitar(ruta, parametros = {}) {
    if (CONFIG.demo) {
        const { responderDemo } = await import('./demo-data.js');
        return responderDemo(CONFIG.demo, ruta, parametros);
    }

    const url = new URL(CONFIG.apiBase + ruta, window.location.origin);
    Object.entries(parametros).forEach(([clave, valor]) => {
        if (valor !== undefined && valor !== null) url.searchParams.set(clave, valor);
    });

    const controlador = new AbortController();
    const temporizador = setTimeout(() => controlador.abort(), CONFIG.timeoutMs);
    try {
        const respuesta = await fetch(url, { headers: { Accept: 'application/json' }, signal: controlador.signal });
        const esJson = (respuesta.headers.get('content-type') || '').includes('application/json');
        const datos = esJson ? await respuesta.json().catch(() => null) : null;
        if (!respuesta.ok) {
            throw new ApiError(datos?.error || mensajePorEstado(respuesta.status), { estado: respuesta.status, detalle: datos });
        }
        if (datos === null) throw new ApiError('La respuesta del servidor no tiene el formato esperado.', { estado: respuesta.status });
        return datos;
    } catch (error) {
        if (error instanceof ApiError) throw error;
        if (error.name === 'AbortError') throw new ApiError('El servidor tardó demasiado en responder.');
        throw new ApiError('No se pudo conectar con el servidor.');
    } finally {
        clearTimeout(temporizador);
    }
}

const comoLista = (datos) => {
    if (!Array.isArray(datos)) throw new ApiError('La respuesta del servidor no tiene el formato esperado.');
    return datos;
};

export const obtenerProductos = async () => comoLista(await solicitar('/api/productos'));
export const obtenerFacturas = async ({ limite } = {}) => comoLista(await solicitar('/api/facturas', { limite }));
export const obtenerResumen = () => solicitar('/api/resumen');
