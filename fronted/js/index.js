const buscador = document.getElementById('buscador');
const tarjetas = Array.from(document.querySelectorAll('#tarjetas .card'));
const mensajeVacio = document.getElementById('sin-resultados');
const estadoResultados = document.getElementById('resultados-info');

function normalizarTexto(texto) {
    return texto
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLocaleLowerCase('es');
}

function filtrarProductos() {
    const consulta = normalizarTexto(buscador.value.trim());
    let cantidadVisible = 0;

    tarjetas.forEach((tarjeta) => {
        const coincide = normalizarTexto(tarjeta.textContent).includes(consulta);
        tarjeta.hidden = !coincide;

        if (coincide) {
            cantidadVisible += 1;
        }
    });

    mensajeVacio.hidden = cantidadVisible > 0;
    estadoResultados.textContent = `${cantidadVisible} ${cantidadVisible === 1 ? 'producto encontrado' : 'productos encontrados'}.`;
}

buscador.addEventListener('input', filtrarProductos);
filtrarProductos();
