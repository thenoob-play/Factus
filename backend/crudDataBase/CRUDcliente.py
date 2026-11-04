from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

COLUMNAS = """
    idcliente, identification_document_code, identification, dv, legal_organization_code,
    tribute_code, names, company, trade_name, email, phone, address, municipality_code,
    estado, creado_en, actualizado_en, creado_por, actualizado_por
"""
_CAMPOS = (
    "identification_document_code", "identification", "dv", "legal_organization_code",
    "tribute_code", "names", "company", "trade_name", "email", "phone", "address",
    "municipality_code", "estado",
)


def buscar_por_id(db: Session, idcliente: int, *, bloquear: bool = False) -> dict[str, Any] | None:
    sufijo = " FOR UPDATE" if bloquear else ""
    fila = db.execute(
        text(f"SELECT {COLUMNAS} FROM cliente WHERE idcliente = :id AND eliminado_en IS NULL{sufijo}"),
        {"id": idcliente},
    ).mappings().first()
    return dict(fila) if fila else None


def existe_documento(
    db: Session, tipo: str, identificacion: str, excluir_id: int | None = None
) -> bool:
    return db.execute(
        text(
            """
            SELECT 1 FROM cliente
            WHERE identification_document_code = :tipo AND identification = :ident
              AND eliminado_en IS NULL AND (:excluir IS NULL OR idcliente <> :excluir)
            LIMIT 1
            """
        ),
        {"tipo": tipo, "ident": identificacion, "excluir": excluir_id},
    ).first() is not None


def crear(db: Session, datos: dict[str, Any], idautor: int) -> int:
    columnas = ", ".join(_CAMPOS)
    valores = ", ".join(f":{c}" for c in _CAMPOS)
    resultado = db.execute(
        text(
            f"INSERT INTO cliente ({columnas}, creado_por, actualizado_por) "
            f"VALUES ({valores}, :autor, :autor)"
        ),
        {**{c: datos.get(c) for c in _CAMPOS}, "autor": idautor},
    )
    return int(resultado.lastrowid)


def actualizar(db: Session, idcliente: int, datos: dict[str, Any], idautor: int) -> None:
    asignaciones = ", ".join(f"{c} = :{c}" for c in _CAMPOS)
    db.execute(
        text(
            f"UPDATE cliente SET {asignaciones}, actualizado_por = :autor "
            "WHERE idcliente = :id AND eliminado_en IS NULL"
        ),
        {**{c: datos.get(c) for c in _CAMPOS}, "autor": idautor, "id": idcliente},
    )


def eliminar_logico(db: Session, idcliente: int, idautor: int) -> bool:
    resultado = db.execute(
        text(
            """
            UPDATE cliente SET eliminado_en = :ahora, estado = 'INACTIVO', actualizado_por = :autor
            WHERE idcliente = :id AND eliminado_en IS NULL
            """
        ),
        {"id": idcliente, "autor": idautor, "ahora": ahora_utc()},
    )
    return resultado.rowcount == 1


ORDENES = {  # lista blanca: el parámetro nunca se interpola tal cual en el SQL
    "nombre": "COALESCE(names, company)", "identification": "identification", "email": "email",
    "creado_en": "creado_en", "estado": "estado",
}


def listar(
    db: Session, buscar: str | None, estado: str | None, limite: int, offset: int,
    ordenar: str = "nombre", desc: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    filtros = """
        WHERE eliminado_en IS NULL
          AND (:estado IS NULL OR estado = :estado)
          AND (:buscar IS NULL OR names LIKE :like OR company LIKE :like
               OR trade_name LIKE :like OR identification LIKE :like OR email LIKE :like)
    """
    params = {"buscar": buscar, "like": f"%{buscar}%" if buscar else None, "estado": estado}
    total = db.execute(text(f"SELECT COUNT(*) FROM cliente {filtros}"), params).scalar_one()
    filas = db.execute(
        text(
            f"SELECT {COLUMNAS} FROM cliente {filtros} "
            f"ORDER BY {ORDENES.get(ordenar, ORDENES['nombre'])} {'DESC' if desc else 'ASC'}, idcliente "
            "LIMIT :limite OFFSET :offset"
        ),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)
