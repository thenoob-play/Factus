from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

COLUMNAS = """
    v.idventa, v.referencia, v.idcliente, v.idtrabajador, v.metodo_pago, v.estado, v.moneda,
    v.subtotal, v.descuento_total, v.base_gravable, v.iva_total, v.total,
    v.creado_en, v.actualizado_en, v.pagada_en, v.facturada_en
"""


def crear(db: Session, datos: dict[str, Any]) -> int:
    resultado = db.execute(
        text(
            """
            INSERT INTO venta (referencia, idcliente, idtrabajador, metodo_pago, estado, moneda,
                               subtotal, descuento_total, base_gravable, iva_total, total,
                               idempotency_key, request_hash, creado_en)
            VALUES (:referencia, :idcliente, :idtrabajador, :metodo_pago, 'PENDIENTE_PAGO', :moneda,
                    :subtotal, :descuento_total, :base_gravable, :iva_total, :total,
                    :idempotency_key, :request_hash, :creado_en)
            """
        ),
        {**datos, "creado_en": ahora_utc()},
    )
    return int(resultado.lastrowid)


def crear_detalles(db: Session, idventa: int, lineas: list[dict[str, Any]]) -> None:
    db.execute(
        text(
            """
            INSERT INTO venta_detalle (idventa, idproducto, code_reference, nombre, unit_measure_code,
                standard_code, cantidad, precio_unitario, discount_rate, descuento, base_gravable,
                tax_code, tax_rate, is_excluded, iva, total)
            VALUES (:idventa, :idproducto, :code_reference, :nombre, :unit_measure_code,
                :standard_code, :cantidad, :precio_unitario, :discount_rate, :descuento, :base_gravable,
                :tax_code, :tax_rate, :is_excluded, :iva, :total)
            """
        ),
        [{**linea, "idventa": idventa, "is_excluded": int(linea["is_excluded"])} for linea in lineas],
    )


def buscar_por_id(db: Session, idventa: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS} FROM venta v WHERE v.idventa = :id{sufijo}"), {"id": idventa}
    ).mappings().first()
    return dict(fila) if fila else None


def buscar_por_idempotencia(db: Session, idtrabajador: int, clave: str) -> dict[str, Any] | None:
    fila = db.execute(
        text(
            f"SELECT {COLUMNAS}, v.request_hash FROM venta v "
            "WHERE v.idtrabajador = :t AND v.idempotency_key = :k FOR UPDATE"
        ),
        {"t": idtrabajador, "k": clave},
    ).mappings().first()
    return dict(fila) if fila else None


def detalles(db: Session, idventa: int) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT iddetalle, idproducto, code_reference, nombre, unit_measure_code, standard_code,
                   cantidad, precio_unitario, discount_rate, descuento, base_gravable, tax_code,
                   tax_rate, is_excluded, iva, total
            FROM venta_detalle WHERE idventa = :id ORDER BY iddetalle
            """
        ),
        {"id": idventa},
    ).mappings().all()
    return [dict(f) for f in filas]


def cambiar_estado(
    db: Session, idventa: int, anterior: str | None, nuevo: str, motivo: str | None,
    idtrabajador: int | None,
) -> None:
    ahora = ahora_utc()
    extra = ""
    if nuevo == "PAGADA":
        extra = ", pagada_en = :ahora"
    elif nuevo == "FACTURADA":
        extra = ", facturada_en = :ahora"
    db.execute(
        text(f"UPDATE venta SET estado = :nuevo{extra} WHERE idventa = :id"),
        {"nuevo": nuevo, "id": idventa, "ahora": ahora},
    )
    registrar_historial(db, idventa, anterior, nuevo, motivo, idtrabajador)


def registrar_historial(
    db: Session, idventa: int, anterior: str | None, nuevo: str, motivo: str | None,
    idtrabajador: int | None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO venta_estado_historial (idventa, estado_anterior, estado_nuevo, motivo,
                                                idtrabajador, creado_en)
            VALUES (:id, :anterior, :nuevo, :motivo, :t, :ahora)
            """
        ),
        {"id": idventa, "anterior": anterior, "nuevo": nuevo, "motivo": motivo,
         "t": idtrabajador, "ahora": ahora_utc()},
    )


def historial(db: Session, idventa: int) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            """
            SELECT estado_anterior, estado_nuevo, motivo, idtrabajador, creado_en
            FROM venta_estado_historial WHERE idventa = :id ORDER BY idhistorial
            """
        ),
        {"id": idventa},
    ).mappings().all()
    return [dict(f) for f in filas]


def pendientes_sin_pago_vigente(db: Session, ahora: Any, limite: int = 200) -> list[int]:
    """Ventas PENDIENTE_PAGO sin pago PENDIENTE/APROBADO cuyo último pago ya venció."""
    filas = db.execute(
        text(
            """
            SELECT v.idventa FROM venta v
            WHERE v.estado = 'PENDIENTE_PAGO'
              AND NOT EXISTS (SELECT 1 FROM pago p WHERE p.idventa = v.idventa
                              AND p.estado IN ('PENDIENTE','APROBADO'))
              AND (SELECT MAX(p.expira_en) FROM pago p WHERE p.idventa = v.idventa) < :ahora
            ORDER BY v.idventa LIMIT :limite
            """
        ),
        {"ahora": ahora, "limite": limite},
    ).all()
    return [int(f[0]) for f in filas]


def contar_pagos(db: Session, idventa: int) -> int:
    return int(db.execute(text("SELECT COUNT(*) FROM pago WHERE idventa = :id"), {"id": idventa}).scalar_one())


def actualizar_metodo(db: Session, idventa: int, metodo: str) -> None:
    db.execute(text("UPDATE venta SET metodo_pago = :m WHERE idventa = :id"), {"m": metodo, "id": idventa})


def listar(
    db: Session, filtros: dict[str, Any], limite: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    condiciones = """
        WHERE (:estado IS NULL OR v.estado = :estado)
          AND (:metodo IS NULL OR v.metodo_pago = :metodo)
          AND (:idcliente IS NULL OR v.idcliente = :idcliente)
          AND (:idtrabajador IS NULL OR v.idtrabajador = :idtrabajador)
          AND (:desde IS NULL OR v.creado_en >= :desde)
          AND (:hasta IS NULL OR v.creado_en < :hasta)
          AND (:buscar IS NULL OR v.referencia LIKE :like OR c.names LIKE :like
               OR c.company LIKE :like OR c.identification LIKE :like)
    """
    filtros = {**filtros, "buscar": filtros.get("buscar"),
               "like": f"%{filtros['buscar']}%" if filtros.get("buscar") else None}
    total = db.execute(
        text(f"SELECT COUNT(*) FROM venta v JOIN cliente c ON c.idcliente = v.idcliente {condiciones}"), filtros
    ).scalar_one()
    filas = db.execute(
        text(
            f"""
            SELECT {COLUMNAS}, COALESCE(c.names, c.company) AS cliente_nombre,
                   t.nombre AS trabajador_nombre
            FROM venta v
            JOIN cliente c ON c.idcliente = v.idcliente
            JOIN trabajador t ON t.idtrabajador = v.idtrabajador
            {condiciones}
            ORDER BY v.idventa DESC LIMIT :limite OFFSET :offset
            """
        ),
        {**filtros, "limite": limite, "offset": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)
