from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

COLUMNAS = """
    idcaja, idtrabajador, estado, base_inicial, abierta_en, cerrada_en,
    efectivo_esperado, efectivo_contado, diferencia, observacion
"""


def caja_abierta(db: Session, idtrabajador: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS} FROM caja WHERE idtrabajador = :t AND estado = 'ABIERTA'{sufijo}"),
        {"t": idtrabajador},
    ).mappings().first()
    return dict(fila) if fila else None


def buscar_por_id(db: Session, idcaja: int) -> dict[str, Any] | None:
    fila = db.execute(text(f"SELECT {COLUMNAS} FROM caja WHERE idcaja = :id"), {"id": idcaja}).mappings().first()
    return dict(fila) if fila else None


def abrir(db: Session, idtrabajador: int, base_inicial: Decimal) -> int:
    resultado = db.execute(
        text(
            "INSERT INTO caja (idtrabajador, estado, base_inicial, abierta_en) "
            "VALUES (:t, 'ABIERTA', :base, :ahora)"
        ),
        {"t": idtrabajador, "base": base_inicial, "ahora": ahora_utc()},
    )
    return int(resultado.lastrowid)


def total_efectivo(db: Session, idcaja: int) -> Decimal:
    """Suma de ventas en efectivo aprobadas en la caja (monto de la venta, no lo recibido)."""
    centavos = db.execute(
        text(
            "SELECT COALESCE(SUM(monto_esperado_centavos), 0) FROM pago "
            "WHERE idcaja = :id AND metodo = 'EFECTIVO' AND estado = 'APROBADO'"
        ),
        {"id": idcaja},
    ).scalar_one()
    return (Decimal(int(centavos)) / 100).quantize(Decimal("0.01"))


def movimientos(db: Session, idcaja: int) -> list[dict[str, Any]]:
    """Pagos en efectivo aprobados en la caja (montos en centavos)."""
    filas = db.execute(
        text(
            """
            SELECT p.idpago, p.idventa, v.referencia, p.monto_esperado_centavos,
                   p.monto_recibido_centavos, p.cambio_centavos, p.verificado_en
            FROM pago p JOIN venta v ON v.idventa = p.idventa
            WHERE p.idcaja = :id AND p.metodo = 'EFECTIVO' AND p.estado = 'APROBADO'
            ORDER BY p.verificado_en DESC
            """
        ),
        {"id": idcaja},
    ).mappings().all()
    return [dict(f) for f in filas]


def cerrar(db: Session, idcaja: int, esperado: Decimal, contado: Decimal, observacion: str | None) -> None:
    db.execute(
        text(
            """
            UPDATE caja SET estado = 'CERRADA', cerrada_en = :ahora, efectivo_esperado = :esperado,
                   efectivo_contado = :contado, diferencia = :diferencia, observacion = :obs
            WHERE idcaja = :id AND estado = 'ABIERTA'
            """
        ),
        {"id": idcaja, "ahora": ahora_utc(), "esperado": esperado, "contado": contado,
         "diferencia": contado - esperado, "obs": observacion},
    )


def listar(db: Session, idtrabajador: int | None, limite: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    filtro = "WHERE (:t IS NULL OR idtrabajador = :t)"
    total = db.execute(text(f"SELECT COUNT(*) FROM caja {filtro}"), {"t": idtrabajador}).scalar_one()
    filas = db.execute(
        text(f"SELECT {COLUMNAS} FROM caja {filtro} ORDER BY idcaja DESC LIMIT :l OFFSET :o"),
        {"t": idtrabajador, "l": limite, "o": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)
