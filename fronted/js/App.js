// Filtro de búsqueda compartido por todas las páginas.
// Filtra cualquier elemento con el atributo data-buscable (tarjetas o filas de tabla).
const buscador = document.getElementById('buscador');
const elementos = Array.from(document.querySelectorAll('[data-buscable]'));
const mensajeVacio = document.getElementById('sin-resultados');
const estadoResultados = document.getElementById('resultados-info');

// Ignora tildes y mayúsculas: "cafe" encuentra "Café"
function normalizarTexto(texto) {
    return texto
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLocaleLowerCase('es');
}

function filtrar() {
    const consulta = normalizarTexto(buscador.value.trim());
    let visibles = 0;

    elementos.forEach((el) => {
        const coincide = normalizarTexto(el.textContent).includes(consulta);
        el.hidden = !coincide;
        if (coincide) visibles += 1;
    });

    if (mensajeVacio) mensajeVacio.hidden = visibles > 0;

    if (estadoResultados) {
        const { singular, plural } = buscador.dataset;
        estadoResultados.textContent = `${visibles} ${visibles === 1 ? singular : plural}.`;
    }
}

if (buscador) {
    buscador.addEventListener('input', filtrar);
    filtrar();
}