import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

COLUMNAS = """
    f.idfactura, f.idventa, f.idcliente, f.idtrabajador, f.reference_code, f.estado, f.numero,
    f.prefijo, f.cufe, f.qr_url, f.public_url, f.is_validated, f.validated_at,
    f.payment_method_code, f.total, f.mensaje, f.errores, f.intentos, f.procesando_desde,
    f.pdf_path, f.xml_path, f.email_enviado_en, f.creado_en, f.actualizado_en
"""
_JSON = ("errores", "payload_enviado", "respuesta", "items")


def _fila(fila: Any) -> dict[str, Any] | None:
    if not fila:
        return None
    datos = dict(fila)
    for campo in _JSON:
        if isinstance(datos.get(campo), str):
            datos[campo] = json.loads(datos[campo])
    return datos


def _json(valor: Any) -> str | None:
    return None if valor is None else json.dumps(valor, ensure_ascii=False, default=str)


def crear(db: Session, datos: dict[str, Any]) -> int:
    resultado = db.execute(
        text(
            """
            INSERT INTO factura_electronica (idventa, idcliente, idtrabajador, reference_code,
                                             estado, total, creado_en)
            VALUES (:idventa, :idcliente, :idtrabajador, :reference_code, 'PENDIENTE', :total, :ahora)
            """
        ),
        {**datos, "ahora": ahora_utc()},
    )
    return int(resultado.lastrowid)


def buscar_por_id(db: Session, idfactura: int, *, bloquear: bool = False,
                  completo: bool = False) -> dict[str, Any] | None:
    extra = ", f.payload_enviado, f.respuesta" if completo else ""
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS}{extra} FROM factura_electronica f WHERE f.idfactura = :id{sufijo}"),
        {"id": idfactura},
    ).mappings().first()
    return _fila(fila)


def buscar_por_venta(db: Session, idventa: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS}, f.payload_enviado FROM factura_electronica f WHERE f.idventa = :id{sufijo}"),
        {"id": idventa},
    ).mappings().first()
    return _fila(fila)


def actualizar(db: Session, idfactura: int, cambios: dict[str, Any]) -> None:
    if not cambios:
        return
    params: dict[str, Any] = {"id": idfactura}
    asignaciones = []
    for campo, valor in cambios.items():
        if campo in ("errores", "payload_enviado", "respuesta"):
            asignaciones.append(f"{campo} = CAST(:{campo} AS JSON)")
            params[campo] = _json(valor)
        elif campo == "intentos_mas_uno":
            asignaciones.append("intentos = intentos + 1")
        else:
            asignaciones.append(f"{campo} = :{campo}")
            params[campo] = valor
    db.execute(
        text(f"UPDATE factura_electronica SET {', '.join(asignaciones)} WHERE idfactura = :id"), params
    )


def listar(db: Session, filtros: dict[str, Any], limite: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    condiciones = """
        WHERE (:estado IS NULL OR f.estado = :estado)
          AND (:metodo IS NULL OR v.metodo_pago = :metodo)
          AND (:idtrabajador IS NULL OR f.idtrabajador = :idtrabajador)
          AND (:idcliente IS NULL OR f.idcliente = :idcliente)
          AND (:desde IS NULL OR f.creado_en >= :desde)
          AND (:hasta IS NULL OR f.creado_en < :hasta)
          AND (:buscar IS NULL OR c.identification LIKE :like OR c.names LIKE :like
               OR c.company LIKE :like OR f.numero LIKE :like)
    """
    params = {**filtros, "like": f"%{filtros['buscar']}%" if filtros.get("buscar") else None}
    base = f"""
        FROM factura_electronica f
        JOIN venta v ON v.idventa = f.idventa
        JOIN cliente c ON c.idcliente = f.idcliente
        JOIN trabajador t ON t.idtrabajador = f.idtrabajador
        {condiciones}
    """
    total = db.execute(text(f"SELECT COUNT(*) {base}"), params).scalar_one()
    filas = db.execute(
        text(
            f"""
            SELECT {COLUMNAS}, v.referencia AS venta_referencia, v.metodo_pago,
                   c.identification AS cliente_identificacion,
                   COALESCE(c.names, c.company) AS cliente_nombre, t.nombre AS trabajador_nombre
            {base}
            ORDER BY f.idfactura DESC LIMIT :limite OFFSET :offset
            """
        ),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()
    return [_fila(f) for f in filas], int(total)


def procesando_vencidas(db: Session, antes_de: Any) -> list[int]:
    filas = db.execute(
        text("SELECT idfactura FROM factura_electronica WHERE estado = 'PROCESANDO' AND procesando_desde < :t"),
        {"t": antes_de},
    ).all()
    return [int(f[0]) for f in filas]


# ---------------------------------------------------------------- notas crédito
def crear_nota(db: Session, datos: dict[str, Any]) -> int:
    resultado = db.execute(
        text(
            """
            INSERT INTO nota_credito (idfactura, reference_code, correction_concept_code, motivo,
                                      estado, total, restaura_stock, items, idtrabajador, creado_en)
            VALUES (:idfactura, :reference_code, :correction_concept_code, :motivo, 'PENDIENTE',
                    :total, :restaura_stock, CAST(:items AS JSON), :idtrabajador, :ahora)
            """
        ),
        {**datos, "items": _json(datos["items"]), "restaura_stock": int(datos["restaura_stock"]),
         "ahora": ahora_utc()},
    )
    return int(resultado.lastrowid)


def buscar_nota(db: Session, idnota: int, *, bloquear: bool = False,
                con_payload: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    extra = ", payload_enviado" if con_payload else ""
    fila = db.execute(
        text(
            "SELECT idnota, idfactura, reference_code, correction_concept_code, motivo, estado, numero, "
            f"cufe, total, restaura_stock, stock_restaurado, items, errores, idtrabajador, creado_en{extra} "
            f"FROM nota_credito WHERE idnota = :id{sufijo}"
        ),
        {"id": idnota},
    ).mappings().first()
    return _fila(fila)


def actualizar_nota(db: Session, idnota: int, cambios: dict[str, Any]) -> None:
    params: dict[str, Any] = {"id": idnota}
    asignaciones = []
    for campo, valor in cambios.items():
        if campo in ("errores", "payload_enviado", "respuesta"):
            asignaciones.append(f"{campo} = CAST(:{campo} AS JSON)")
            params[campo] = _json(valor)
        else:
            asignaciones.append(f"{campo} = :{campo}")
            params[campo] = valor
    db.execute(text(f"UPDATE nota_credito SET {', '.join(asignaciones)} WHERE idnota = :id"), params)


def notas_de_factura(db: Session, idfactura: int) -> list[dict[str, Any]]:
    filas = db.execute(
        text(
            "SELECT idnota, reference_code, correction_concept_code, motivo, estado, numero, cufe, "
            "total, restaura_stock, stock_restaurado, items, errores, creado_en "
            "FROM nota_credito WHERE idfactura = :id ORDER BY idnota"
        ),
        {"id": idfactura},
    ).mappings().all()
    return [_fila(f) for f in filas]


def cantidades_devueltas(db: Session, idfactura: int) -> dict[int, int]:
    """Unidades ya incluidas en notas crédito emitidas o pendientes, por producto."""
    devueltas: dict[int, int] = {}
    for nota in notas_de_factura(db, idfactura):
        if nota["estado"] == "FALLIDA":
            continue
        for item in nota["items"] or []:
            devueltas[int(item["idproducto"])] = devueltas.get(int(item["idproducto"]), 0) + int(item["cantidad"])
    return devueltas
