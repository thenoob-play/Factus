import { obtenerProductos, mensajeDe } from '../api.js';
import { tarjetaProducto, esqueletoTarjetas, mostrarEstado, ocultarEstado } from '../ui.js';
import { refrescarBuscador } from '../buscador.js';

async function cargar() {
    const catalogo = document.getElementById('catalogo');
    const estado = document.getElementById('estado-productos');
    const ancla = document.getElementById('sin-resultados');
    const limpiar = () => catalogo.querySelectorAll('[data-buscable], [data-esqueleto]').forEach((el) => el.remove());

    ocultarEstado(estado);
    limpiar();
    catalogo.setAttribute('aria-busy', 'true');
    ancla.insertAdjacentHTML('beforebegin', esqueletoTarjetas());
    refrescarBuscador();

    try {
        const productos = await obtenerProductos();
        limpiar();
        if (productos.length === 0) {
            mostrarEstado(estado, { titulo: 'Aún no hay productos', mensaje: 'Cuando registres el primero aparecerá aquí.' });
        } else {
            ancla.insertAdjacentHTML('beforebegin', productos.map(tarjetaProducto).join(''));
        }
    } catch (error) {
        limpiar();
        mostrarEstado(estado, { esError: true, titulo: 'No pudimos cargar los productos', mensaje: mensajeDe(error), alReintentar: cargar });
    } finally {
        catalogo.removeAttribute('aria-busy');
        refrescarBuscador();
    }
}

export const iniciar = cargar;
