// Punto de entrada común: activa el buscador y carga el módulo de la página actual.
import { CONFIG } from './config.js';
import { iniciarBuscador } from './buscador.js';

const paginas = {
    inicio: () => import('./paginas/inicio.js'),
    productos: () => import('./paginas/productos.js'),
    facturas: () => import('./paginas/facturas.js'),
};

function mostrarAvisoDemo() {
    const aviso = document.createElement('div');
    aviso.className = 'banner-demo';
    aviso.setAttribute('role', 'note');
    aviso.innerHTML = `Modo demostración (${CONFIG.demo}) · datos de ejemplo <a href="?demo=off">Salir</a>`;
    document.body.append(aviso);
}

async function arrancar() {
    if (CONFIG.demo) mostrarAvisoDemo();
    iniciarBuscador();
    try {
        const cargar = paginas[document.body.dataset.pagina];
        if (cargar) (await cargar()).iniciar();
    } catch (error) {
        console.error('No se pudo iniciar la página:', error);
    }
}

arrancar();
