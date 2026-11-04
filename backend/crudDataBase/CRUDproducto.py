"""Acceso a la tabla `productos`.

Los nombres de columnas heredados se exponen con los nombres de la API:
codigo_interno → code_reference, cantidad → stock, tarifa_iva → tax_rate,
descuento → discount_rate (porcentaje 0..100).
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

SELECT = """
    SELECT idproductos AS idproducto, codigo_interno AS code_reference, nombre, descripcion,
           precio_unitario, cantidad AS stock, stock_reservado,
           (cantidad - stock_reservado) AS stock_disponible, stock_minimo,
           tarifa_iva AS tax_rate, is_excluded, tax_code, unit_measure_code, standard_code,
           codigo_UNSPSC AS codigo_unspsc, descuento AS discount_rate, estado, idcategoria,
           URL_imagen AS url_imagen, creado_en, actualizado_en, creado_por, actualizado_por
    FROM productos
"""

_UNIDAD_LEGADA = {"94": "unidad", "KGM": "kilos", "GRM": "gramos", "LTR": "litros",
                  "MTR": "metros", "HUR": "horas", "MON": "mes"}


def _a_columnas(datos: dict[str, Any]) -> dict[str, Any]:
    return {
        "codigo_interno": datos["code_reference"],
        "nombre": datos["nombre"],
        "descripcion": datos.get("descripcion"),
        "precio_unitario": datos["precio_unitario"],
        "stock_minimo": datos.get("stock_minimo", 0),
        "tarifa_iva": datos["tax_rate"],
        "is_excluded": int(bool(datos.get("is_excluded"))),
        "tax_code": datos.get("tax_code", "01"),
        "unit_measure_code": datos["unit_measure_code"],
        "Uni_medida": _UNIDAD_LEGADA.get(datos["unit_measure_code"], "otro"),
        "standard_code": datos.get("standard_code", "999"),
        "codigo_UNSPSC": datos.get("codigo_unspsc") or "",
        "descuento": datos.get("discount_rate", 0),
        "estado": datos.get("estado", "ACTIVO"),
        "idcategoria": datos.get("idcategoria"),
        "URL_imagen": datos.get("url_imagen"),
    }


def buscar_por_id(db: Session, idproducto: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"{SELECT} WHERE idproductos = :id AND eliminado_en IS NULL{sufijo}"),
        {"id": idproducto},
    ).mappings().first()
    return dict(fila) if fila else None


def existe_codigo(db: Session, code_reference: str, excluir_id: int | None = None) -> bool:
    # Incluye eliminados: el índice único de codigo_interno también los cubre.
    return db.execute(
        text(
            "SELECT 1 FROM productos WHERE codigo_interno = :codigo "
            "AND (:excluir IS NULL OR idproductos <> :excluir) LIMIT 1"
        ),
        {"codigo": code_reference, "excluir": excluir_id},
    ).first() is not None


def crear(db: Session, datos: dict[str, Any], idautor: int) -> int:
    columnas = _a_columnas(datos)
    columnas["cantidad"] = datos.get("stock", 0)
    nombres = ", ".join(columnas)
    valores = ", ".join(f":{c}" for c in columnas)
    resultado = db.execute(
        text(f"INSERT INTO productos ({nombres}, creado_por, actualizado_por) VALUES ({valores}, :autor, :autor)"),
        {**columnas, "autor": idautor},
    )
    return int(resultado.lastrowid)


def actualizar(db: Session, idproducto: int, datos: dict[str, Any], idautor: int) -> None:
    columnas = _a_columnas(datos)
    asignaciones = ", ".join(f"{c} = :{c}" for c in columnas)
    db.execute(
        text(
            f"UPDATE productos SET {asignaciones}, actualizado_por = :autor "
            "WHERE idproductos = :id AND eliminado_en IS NULL"
        ),
        {**columnas, "autor": idautor, "id": idproducto},
    )


def ajustar_stock(db: Session, idproducto: int, delta: int, idautor: int) -> bool:
    """Suma (o resta) unidades físicas sin bajar del stock reservado."""
    resultado = db.execute(
        text(
            """
            UPDATE productos SET cantidad = cantidad + :delta, actualizado_por = :autor
            WHERE idproductos = :id AND eliminado_en IS NULL
              AND cantidad + :delta >= stock_reservado
            """
        ),
        {"delta": delta, "id": idproducto, "autor": idautor},
    )
    return resultado.rowcount == 1


def eliminar_logico(db: Session, idproducto: int, idautor: int) -> bool:
    resultado = db.execute(
        text(
            """
            UPDATE productos SET eliminado_en = :ahora, estado = 'INACTIVO', actualizado_por = :autor
            WHERE idproductos = :id AND eliminado_en IS NULL
            """
        ),
        {"id": idproducto, "autor": idautor, "ahora": ahora_utc()},
    )
    return resultado.rowcount == 1


ORDENES = {  # lista blanca: el parámetro nunca se interpola tal cual en el SQL
    "nombre": "nombre", "code_reference": "codigo_interno", "precio_unitario": "precio_unitario",
    "stock": "(cantidad - stock_reservado)", "tax_rate": "tarifa_iva", "estado": "estado",
}


def listar(
    db: Session, buscar: str | None, estado: str | None, solo_stock_bajo: bool,
    limite: int, offset: int, ordenar: str = "nombre", desc: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    filtros = """
        WHERE eliminado_en IS NULL
          AND (:estado IS NULL OR estado = :estado)
          AND (:buscar IS NULL OR nombre LIKE :like OR codigo_interno LIKE :like
               OR descripcion LIKE :like)
          AND (:bajo = 0 OR (cantidad - stock_reservado) <= stock_minimo)
    """
    params = {"buscar": buscar, "like": f"%{buscar}%" if buscar else None,
              "estado": estado, "bajo": int(solo_stock_bajo)}
    total = db.execute(text(f"SELECT COUNT(*) FROM productos {filtros}"), params).scalar_one()
    filas = db.execute(
        text(
            f"{SELECT} {filtros} ORDER BY {ORDENES.get(ordenar, 'nombre')} {'DESC' if desc else 'ASC'}, "
            "idproductos LIMIT :limite OFFSET :offset"
        ),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)


# ----------------------------------------------------------- reservas de stock
def reservar(db: Session, idproducto: int, cantidad: int) -> bool:
    resultado = db.execute(
        text(
            """
            UPDATE productos SET stock_reservado = stock_reservado + :cantidad
            WHERE idproductos = :id AND (cantidad - stock_reservado) >= :cantidad
            """
        ),
        {"id": idproducto, "cantidad": cantidad},
    )
    return resultado.rowcount == 1


def liberar_reserva(db: Session, idproducto: int, cantidad: int) -> bool:
    resultado = db.execute(
        text(
            """
            UPDATE productos SET stock_reservado = stock_reservado - :cantidad
            WHERE idproductos = :id AND stock_reservado >= :cantidad
            """
        ),
        {"id": idproducto, "cantidad": cantidad},
    )
    return resultado.rowcount == 1


def confirmar_reserva(db: Session, idproducto: int, cantidad: int) -> bool:
    """Descuenta definitivamente las unidades reservadas (al aprobar el pago)."""
    resultado = db.execute(
        text(
            """
            UPDATE productos
            SET cantidad = cantidad - :cantidad, stock_reservado = stock_reservado - :cantidad
            WHERE idproductos = :id AND stock_reservado >= :cantidad AND cantidad >= :cantidad
            """
        ),
        {"id": idproducto, "cantidad": cantidad},
    )
    return resultado.rowcount == 1


def devolver_stock(db: Session, idproducto: int, cantidad: int) -> None:
    db.execute(
        text("UPDATE productos SET cantidad = cantidad + :cantidad WHERE idproductos = :id"),
        {"id": idproducto, "cantidad": cantidad},
    )
