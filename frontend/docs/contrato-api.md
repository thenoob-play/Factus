# Contrato de la API que consume el frontend

Todas las respuestas son JSON. Errores: código HTTP correcto (400, 404, 500) y cuerpo `{"error": "mensaje claro"}`.
Fechas en ISO (`"2026-11-04"` o `"2026-11-04T21:28:04"`), nunca en formato RFC 822 de `jsonify` con `datetime`: usa `.isoformat()`.
Dinero como número (los `DECIMAL` de MySQL conviértelos a `float`/`int`).

| Ruta | Respuesta |
|---|---|
| `GET /api/productos` | `[{"referencia": "1001", "nombre": "Arroz Diana 500 g", "precio": 2800, "stock": 48}]` |
| `GET /api/facturas?limite=5` | `[{"codigo": "FE-0108", "cliente": "Distribuidora La Sabana", "fecha": "2026-11-04", "total": 1250000, "estado": "pagada"}]` (más recientes primero; `limite` opcional; estado: `pagada`, `pendiente` o `vencida`) |
| `GET /api/resumen` | `{"ventas_hoy": {"total": 0, "facturas": 0}, "por_cobrar": {"total": 0, "facturas": 0, "vencidas": 0}, "clientes_nuevos_mes": 0, "stock_bajo": {"productos": 0, "agotados": 0}}` |

Notas:
- `por_cobrar` incluye pendientes y vencidas; `stock_bajo.productos` cuenta productos con `stock <= 10` (los agotados incluidos).
- El estado de cada producto (agotado / stock bajo / disponible) lo calcula el frontend desde `stock`.
- Sugerencia de mapeo a tu base: `codigo` ← `factura.numero_factura`, `cliente` ← `usuario.nombre` (vía `compra.idusuario`), `fecha` ← `factura.fecha_emision`, `total` ← `factura.total_bruto` (o el neto si lo tienes), `referencia` ← `productos.codigo_interno`.

Probar sin backend: abre `html/inicio.html` desde el servidor con `?demo=1` (también `?demo=error` y `?demo=vacio`; `?demo=off` para salir).
