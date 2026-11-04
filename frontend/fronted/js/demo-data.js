// Datos de ejemplo para trabajar el frontend sin backend (solo se carga en modo demo).
import { ApiError } from './api.js';

const PAUSA_MS = 450;
const dia = (atras) =>
    new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Bogota' }).format(new Date(Date.now() - atras * 86400000));

const PRODUCTOS = [
    ['1001', 'Arroz Diana 500 g', 2800, 48], ['1002', 'Aceite de girasol 1 L', 13500, 32],
    ['1003', 'Leche entera 1 L', 4600, 6], ['1004', 'Panela redonda', 3200, 60],
    ['1005', 'Huevos AA x 30', 21000, 15], ['1006', 'Café molido 250 g', 8900, 0],
    ['1007', 'Jabón en barra x 3', 7400, 27], ['1008', 'Sal refisal 500 g', 1500, 4],
].map(([referencia, nombre, precio, stock]) => ({ referencia, nombre, precio, stock }));

const FACTURAS = [
    ['FE-0108', 'Distribuidora La Sabana', 0, 1250000, 'pagada'], ['FE-0107', 'Tienda El Vecino', 0, 386500, 'pendiente'],
    ['FE-0106', 'Supermercado Los Pinos', 1, 2140000, 'pagada'], ['FE-0105', 'María Fernanda Ortiz', 2, 98700, 'pagada'],
    ['FE-0104', 'Restaurante Sabor Sinuano', 7, 742300, 'vencida'], ['FE-0103', 'Panadería Central', 10, 215000, 'pagada'],
    ['FE-0102', 'Carlos Andrés Pérez', 15, 64900, 'vencida'], ['FE-0101', 'Almacén Don Jorge', 17, 530000, 'pagada'],
].map(([codigo, cliente, atras, total, estado]) => ({ codigo, cliente, fecha: dia(atras), total, estado }));

function resumen(facturas, productos) {
    const suma = (lista) => lista.reduce((acc, f) => acc + f.total, 0);
    const deHoy = facturas.filter((f) => f.fecha === dia(0));
    const porCobrar = facturas.filter((f) => f.estado !== 'pagada');
    const bajos = productos.filter((p) => p.stock <= 10);
    return {
        ventas_hoy: { total: suma(deHoy), facturas: deHoy.length },
        por_cobrar: { total: suma(porCobrar), facturas: porCobrar.length, vencidas: porCobrar.filter((f) => f.estado === 'vencida').length },
        clientes_nuevos_mes: facturas.length ? 5 : 0,
        stock_bajo: { productos: bajos.length, agotados: bajos.filter((p) => p.stock === 0).length },
    };
}

export async function responderDemo(modo, ruta, parametros = {}) {
    await new Promise((resolver) => setTimeout(resolver, PAUSA_MS));
    if (modo === 'error') throw new ApiError('No se pudo conectar con el servidor (modo demostración).');
    const productos = modo === 'vacio' ? [] : PRODUCTOS;
    const facturas = modo === 'vacio' ? [] : FACTURAS;
    if (ruta === '/api/productos') return productos;
    if (ruta === '/api/facturas') return parametros.limite ? facturas.slice(0, Number(parametros.limite)) : facturas;
    if (ruta === '/api/resumen') return resumen(facturas, productos);
    throw new ApiError('Ruta no encontrada.', { estado: 404 });
}
