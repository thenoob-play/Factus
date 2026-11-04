"""Consultas de solo lectura para el dashboard, reportes y catálogos en caché."""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_VENDIDAS = "('PAGADA','FACTURADA','FACTURA_FALLIDA')"


def totales_ventas(db: Session, desde: datetime, hasta: datetime) -> dict[str, Any]:
    fila = db.execute(
        text(
            f"""
            SELECT COUNT(*) AS cantidad, COALESCE(SUM(total), 0) AS total
            FROM venta WHERE estado IN {_VENDIDAS} AND pagada_en >= :desde AND pagada_en < :hasta
            """
        ),
        {"desde": desde, "hasta": hasta},
    ).mappings().one()
    return dict(fila)


def totales_por_metodo(db: Session, desde: datetime, hasta: datetime) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            f"""
            SELECT metodo_pago, COUNT(*) AS cantidad, COALESCE(SUM(total), 0) AS total
            FROM venta WHERE estado IN {_VENDIDAS} AND pagada_en >= :desde AND pagada_en < :hasta
            GROUP BY metodo_pago ORDER BY total DESC
            """
        ),
        {"desde": desde, "hasta": hasta},
    ).mappings().all()
    return [dict(f) for f in filas]


def ventas_por_dia(db: Session, desde: datetime, hasta: datetime) -> list[dict[str, Any]]:
    """Ventas pagadas agrupadas por día calendario de Colombia (UTC-5)."""
    filas = db.execute(
        text(
            f"""
            SELECT DATE(CONVERT_TZ(pagada_en, '+00:00', '-05:00')) AS dia,
                   COUNT(*) AS cantidad, COALESCE(SUM(total), 0) AS total
            FROM venta WHERE estado IN {_VENDIDAS} AND pagada_en >= :desde AND pagada_en < :hasta
            GROUP BY dia ORDER BY dia
            """
        ),
        {"desde": desde, "hasta": hasta},
    ).mappings().all()
    return [dict(f) for f in filas]


def facturas_por_estado(db: Session, desde: datetime, hasta: datetime) -> dict[str, int]:
    filas = db.execute(
        text(
            "SELECT estado, COUNT(*) AS n FROM factura_electronica "
            "WHERE creado_en >= :desde AND creado_en < :hasta GROUP BY estado"
        ),
        {"desde": desde, "hasta": hasta},
    ).all()
    return {str(f[0]): int(f[1]) for f in filas}


def productos_mas_vendidos(db: Session, desde: datetime, hasta: datetime, limite: int = 10) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            f"""
            SELECT d.idproducto, MAX(d.nombre) AS nombre, SUM(d.cantidad) AS unidades,
                   SUM(d.total) AS total
            FROM venta_detalle d JOIN venta v ON v.idventa = d.idventa
            WHERE v.estado IN {_VENDIDAS} AND v.pagada_en >= :desde AND v.pagada_en < :hasta
            GROUP BY d.idproducto ORDER BY unidades DESC LIMIT :limite
            """
        ),
        {"desde": desde, "hasta": hasta, "limite": limite},
    ).mappings().all()
    return [dict(f) for f in filas]


def productos_stock_bajo(db: Session, limite: int = 50) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT idproductos AS idproducto, codigo_interno AS code_reference, nombre,
                   cantidad AS stock, stock_reservado, (cantidad - stock_reservado) AS stock_disponible,
                   stock_minimo
            FROM productos
            WHERE eliminado_en IS NULL AND estado = 'ACTIVO' AND (cantidad - stock_reservado) <= stock_minimo
            ORDER BY (cantidad - stock_reservado) - stock_minimo LIMIT :limite
            """
        ),
        {"limite": limite},
    ).mappings().all()
    return [dict(f) for f in filas]


def facturas_fallidas(db: Session) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT f.idfactura, f.idventa, f.reference_code, f.mensaje, f.intentos, f.actualizado_en
            FROM factura_electronica f WHERE f.estado = 'FALLIDA' ORDER BY f.actualizado_en DESC
            """
        )
    ).mappings().all()
    return [dict(f) for f in filas]


def reporte_ventas(db: Session, desde: datetime, hasta: datetime) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT v.idventa, v.referencia, v.creado_en, v.pagada_en, v.estado, v.metodo_pago,
                   c.identification AS cliente_documento, COALESCE(c.names, c.company) AS cliente,
                   t.nombre AS trabajador, v.subtotal, v.descuento_total, v.base_gravable,
                   v.iva_total, v.total, f.numero AS factura_numero, f.estado AS factura_estado
            FROM venta v
            JOIN cliente c ON c.idcliente = v.idcliente
            JOIN trabajador t ON t.idtrabajador = v.idtrabajador
            LEFT JOIN factura_electronica f ON f.idventa = v.idventa
            WHERE v.creado_en >= :desde AND v.creado_en < :hasta
            ORDER BY v.idventa
            """
        ),
        {"desde": desde, "hasta": hasta},
    ).mappings().all()
    return [dict(f) for f in filas]


def reporte_facturas(db: Session, desde: datetime, hasta: datetime) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT f.idfactura, f.numero, f.prefijo, f.cufe, f.estado, f.is_validated, f.validated_at,
                   f.creado_en, v.referencia AS venta_referencia, v.metodo_pago, f.payment_method_code,
                   c.identification AS cliente_documento, COALESCE(c.names, c.company) AS cliente,
                   t.nombre AS trabajador, v.subtotal, v.descuento_total, v.iva_total, f.total
            FROM factura_electronica f
            JOIN venta v ON v.idventa = f.idventa
            JOIN cliente c ON c.idcliente = f.idcliente
            JOIN trabajador t ON t.idtrabajador = f.idtrabajador
            WHERE f.creado_en >= :desde AND f.creado_en < :hasta
            ORDER BY f.idfactura
            """
        ),
        {"desde": desde, "hasta": hasta},
    ).mappings().all()
    return [dict(f) for f in filas]


# --------------------------------------------------------- catálogos en caché
def guardar_catalogo(db: Session, tipo: str, datos: Any, ahora: datetime) -> None:
    db.execute(
        text(
            """
            INSERT INTO factus_catalogo (tipo, datos, actualizado_en)
            VALUES (:tipo, CAST(:datos AS JSON), :ahora)
            ON DUPLICATE KEY UPDATE datos = VALUES(datos), actualizado_en = VALUES(actualizado_en)
            """
        ),
        {"tipo": tipo, "datos": json.dumps(datos, ensure_ascii=False), "ahora": ahora},
    )


def leer_catalogo(db: Session, tipo: str) -> dict[str, Any] | None:
    fila = db.execute(
        text("SELECT tipo, datos, actualizado_en FROM factus_catalogo WHERE tipo = :tipo"), {"tipo": tipo}
    ).mappings().first()
    if not fila:
        return None
    datos = dict(fila)
    if isinstance(datos["datos"], str):
        datos["datos"] = json.loads(datos["datos"])
    return datos


def listar_catalogos(db: Session) -> list[dict[str, Any]]:
    filas = db.execute(
        text("SELECT tipo, JSON_LENGTH(datos) AS registros, actualizado_en FROM factus_catalogo ORDER BY tipo")
    ).mappings().all()
    return [dict(f) for f in filas]
