"""Acceso a `pago`, `pago_intento` y `webhook_evento`.

Los campos inmutables (monto, moneda, referencia, firma, expiración) solo se escriben
en el INSERT; los UPDATE de este módulo nunca los tocan y, además, un trigger de
MySQL rechaza cualquier intento de cambiarlos.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

COLUMNAS = """
    idpago, idventa, metodo, canal, monto_esperado_centavos, moneda, referencia,
    firma_integridad, estado, expira_en, checkout_url, qr_payload, qr_png_base64,
    proveedor_transaccion_id, proveedor_estado, proveedor_metodo,
    comprobante_numero, comprobante_banco, comprobante_fecha, comprobante_monto_centavos,
    comprobante_imagen, comprobante_registrado_en,
    tarjeta_franquicia, tarjeta_ultimos4, tarjeta_tipo, codigo_autorizacion, recibo_numero,
    monto_recibido_centavos, cambio_centavos, idcaja, verificado_por, verificado_en,
    motivo_rechazo, sospechoso, creado_por, creado_en
"""

# Campos que se pueden actualizar. Monto, moneda, referencia, firma, expiración,
# venta y método NO están aquí a propósito.
_ACTUALIZABLES = {
    "estado", "checkout_url", "qr_payload", "qr_png_base64", "proveedor_transaccion_id",
    "proveedor_estado", "proveedor_metodo", "comprobante_numero", "comprobante_banco",
    "comprobante_fecha", "comprobante_monto_centavos", "comprobante_imagen",
    "comprobante_registrado_en", "tarjeta_franquicia", "tarjeta_ultimos4", "tarjeta_tipo",
    "codigo_autorizacion", "recibo_numero", "monto_recibido_centavos", "cambio_centavos",
    "idcaja", "verificado_por", "verificado_en", "motivo_rechazo", "sospechoso",
}


def crear(db: Session, datos: dict[str, Any]) -> int:
    resultado = db.execute(
        text(
            """
            INSERT INTO pago (idventa, metodo, canal, monto_esperado_centavos, moneda, referencia,
                              firma_integridad, estado, expira_en, creado_por, creado_en)
            VALUES (:idventa, :metodo, :canal, :monto_esperado_centavos, :moneda, :referencia,
                    :firma_integridad, 'PENDIENTE', :expira_en, :creado_por, :creado_en)
            """
        ),
        {**datos, "creado_en": ahora_utc()},
    )
    return int(resultado.lastrowid)


def actualizar(db: Session, idpago: int, cambios: dict[str, Any]) -> None:
    invalidos = set(cambios) - _ACTUALIZABLES
    if invalidos:
        raise ValueError(f"Campos de pago no modificables: {sorted(invalidos)}")
    if not cambios:
        return
    asignaciones = ", ".join(f"{c} = :{c}" for c in cambios)
    db.execute(text(f"UPDATE pago SET {asignaciones} WHERE idpago = :id"), {**cambios, "id": idpago})


def buscar_por_id(db: Session, idpago: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS} FROM pago WHERE idpago = :id{sufijo}"), {"id": idpago}
    ).mappings().first()
    return dict(fila) if fila else None


def buscar_por_referencia(db: Session, referencia: str, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS} FROM pago WHERE referencia = :ref{sufijo}"), {"ref": referencia}
    ).mappings().first()
    return dict(fila) if fila else None


def pago_vigente_de_venta(db: Session, idventa: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    """Último pago PENDIENTE o APROBADO de la venta."""
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(
            f"SELECT {COLUMNAS} FROM pago WHERE idventa = :id AND estado IN ('PENDIENTE','APROBADO') "
            f"ORDER BY idpago DESC LIMIT 1{sufijo}"
        ),
        {"id": idventa},
    ).mappings().first()
    return dict(fila) if fila else None


def pagos_de_venta(db: Session, idventa: int) -> list[dict[str, Any]]:
    filas = db.execute(
        text(f"SELECT {COLUMNAS} FROM pago WHERE idventa = :id ORDER BY idpago"), {"id": idventa}
    ).mappings().all()
    return [dict(f) for f in filas]


def existe_valor_unico(db: Session, campo: str, valor: str) -> bool:
    if campo not in {"comprobante_numero", "recibo_numero", "proveedor_transaccion_id"}:
        raise ValueError("Campo no permitido.")
    return db.execute(
        text(f"SELECT 1 FROM pago WHERE {campo} = :v LIMIT 1"), {"v": valor}
    ).first() is not None


def pendientes_vencidos(db: Session, limite: int = 200) -> list[dict[str, Any]]:
    """Pagos pendientes vencidos sin comprobante registrado a tiempo."""
    filas = db.execute(
        text(
            """
            SELECT idpago, idventa FROM pago
            WHERE estado = 'PENDIENTE' AND expira_en < :ahora
              AND (comprobante_registrado_en IS NULL OR comprobante_registrado_en > expira_en)
            ORDER BY expira_en LIMIT :limite
            """
        ),
        {"ahora": ahora_utc(), "limite": limite},
    ).mappings().all()
    return [dict(f) for f in filas]


def comprobantes_por_verificar(db: Session, limite: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    filtro = "WHERE estado = 'PENDIENTE' AND comprobante_registrado_en IS NOT NULL"
    total = db.execute(text(f"SELECT COUNT(*) FROM pago {filtro}")).scalar_one()
    filas = db.execute(
        text(f"SELECT {COLUMNAS} FROM pago {filtro} ORDER BY comprobante_registrado_en LIMIT :l OFFSET :o"),
        {"l": limite, "o": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)


def registrar_intento(
    db: Session, *, idpago: int | None, origen: str, resultado: str,
    monto_recibido_centavos: int | None = None, moneda: str | None = None,
    firma_valida: bool | None = None, monto_valido: bool | None = None,
    sospechoso: bool = False, detalle: dict[str, Any] | None = None,
    idtrabajador: int | None = None, ip: str | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO pago_intento (idpago, origen, monto_recibido_centavos, moneda, firma_valida,
                monto_valido, resultado, sospechoso, detalle, idtrabajador, ip, creado_en)
            VALUES (:idpago, :origen, :monto, :moneda, :firma, :monto_ok, :resultado, :sospechoso,
                CAST(:detalle AS JSON), :idtrabajador, :ip, :ahora)
            """
        ),
        {
            "idpago": idpago, "origen": origen, "monto": monto_recibido_centavos, "moneda": moneda,
            "firma": None if firma_valida is None else int(firma_valida),
            "monto_ok": None if monto_valido is None else int(monto_valido),
            "resultado": resultado, "sospechoso": int(sospechoso),
            "detalle": json.dumps(detalle, ensure_ascii=False, default=str) if detalle else None,
            "idtrabajador": idtrabajador, "ip": ip, "ahora": ahora_utc(),
        },
    )


def intentos_sospechosos(db: Session, limite: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    total = db.execute(text("SELECT COUNT(*) FROM pago_intento WHERE sospechoso = 1")).scalar_one()
    filas = db.execute(
        text(
            """
            SELECT idintento, idpago, origen, monto_recibido_centavos, moneda, firma_valida,
                   monto_valido, resultado, detalle, idtrabajador, ip, creado_en
            FROM pago_intento WHERE sospechoso = 1 ORDER BY idintento DESC LIMIT :l OFFSET :o
            """
        ),
        {"l": limite, "o": offset},
    ).mappings().all()
    items = []
    for fila in filas:
        item = dict(fila)
        if isinstance(item.get("detalle"), str):
            item["detalle"] = json.loads(item["detalle"])
        items.append(item)
    return items, int(total)


def registrar_evento_webhook(
    db: Session, proveedor: str, evento_hash: str, tipo: str | None, referencia: str | None,
    transaccion_id: str | None, payload: dict[str, Any],
) -> bool:
    """Registra el evento. Devuelve False si ya se había recibido (duplicado)."""
    try:
        with db.begin_nested():
            db.execute(
                text(
                    """
                    INSERT INTO webhook_evento (proveedor, evento_hash, tipo, referencia,
                                                transaccion_id, payload, creado_en)
                    VALUES (:p, :h, :tipo, :ref, :tx, CAST(:payload AS JSON), :ahora)
                    """
                ),
                {"p": proveedor, "h": evento_hash, "tipo": tipo, "ref": referencia, "tx": transaccion_id,
                 "payload": json.dumps(payload, ensure_ascii=False), "ahora": ahora_utc()},
            )
        return True
    except IntegrityError:
        return False


def resultado_evento_webhook(db: Session, proveedor: str, evento_hash: str, resultado: str) -> None:
    db.execute(
        text("UPDATE webhook_evento SET resultado = :r WHERE proveedor = :p AND evento_hash = :h"),
        {"r": resultado, "p": proveedor, "h": evento_hash},
    )
