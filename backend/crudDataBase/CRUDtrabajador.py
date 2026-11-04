from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc

_COLUMNAS = """
    idtrabajador, nombre, tipo_documento, documento, email, telefono, rol, estado,
    ultimo_login_en, creado_en, actualizado_en, creado_por, actualizado_por
"""


def buscar_por_email(db: Session, email: str) -> dict[str, Any] | None:
    fila = db.execute(
        text(
            f"SELECT {_COLUMNAS}, password_hash FROM trabajador "
            "WHERE email = :email AND eliminado_en IS NULL"
        ),
        {"email": email},
    ).mappings().first()
    return dict(fila) if fila else None


def buscar_por_id(db: Session, idtrabajador: int) -> dict[str, Any] | None:
    fila = db.execute(
        text(f"SELECT {_COLUMNAS} FROM trabajador WHERE idtrabajador = :id AND eliminado_en IS NULL"),
        {"id": idtrabajador},
    ).mappings().first()
    return dict(fila) if fila else None


def existe_duplicado(
    db: Session, email: str, tipo_documento: str, documento: str, excluir_id: int | None = None
) -> str | None:
    fila = db.execute(
        text(
            """
            SELECT email, tipo_documento, documento FROM trabajador
            WHERE (email = :email OR (tipo_documento = :tipo AND documento = :doc))
              AND (:excluir IS NULL OR idtrabajador <> :excluir)
            LIMIT 1
            """
        ),
        {"email": email, "tipo": tipo_documento, "doc": documento, "excluir": excluir_id},
    ).mappings().first()
    if not fila:
        return None
    return "email" if fila["email"] == email else "documento"


def crear(db: Session, datos: dict[str, Any], idautor: int | None) -> int:
    resultado = db.execute(
        text(
            """
            INSERT INTO trabajador (nombre, tipo_documento, documento, email, telefono, rol,
                                    password_hash, estado, creado_por, actualizado_por)
            VALUES (:nombre, :tipo_documento, :documento, :email, :telefono, :rol,
                    :password_hash, :estado, :autor, :autor)
            """
        ),
        {**datos, "autor": idautor},
    )
    return int(resultado.lastrowid)


def actualizar(db: Session, idtrabajador: int, cambios: dict[str, Any], idautor: int) -> None:
    permitidos = {"nombre", "tipo_documento", "documento", "email", "telefono", "rol",
                  "estado", "password_hash"}
    campos = {k: v for k, v in cambios.items() if k in permitidos}
    if not campos:
        return
    asignaciones = ", ".join(f"{campo} = :{campo}" for campo in campos)
    db.execute(
        text(
            f"UPDATE trabajador SET {asignaciones}, actualizado_por = :autor "
            "WHERE idtrabajador = :id AND eliminado_en IS NULL"
        ),
        {**campos, "autor": idautor, "id": idtrabajador},
    )


def eliminar_logico(db: Session, idtrabajador: int, idautor: int) -> bool:
    resultado = db.execute(
        text(
            """
            UPDATE trabajador SET eliminado_en = :ahora, estado = 'INACTIVO', actualizado_por = :autor
            WHERE idtrabajador = :id AND eliminado_en IS NULL
            """
        ),
        {"id": idtrabajador, "autor": idautor, "ahora": ahora_utc()},
    )
    return resultado.rowcount == 1


def registrar_login(db: Session, idtrabajador: int) -> None:
    db.execute(
        text("UPDATE trabajador SET ultimo_login_en = :ahora WHERE idtrabajador = :id"),
        {"id": idtrabajador, "ahora": ahora_utc()},
    )


def listar(
    db: Session, buscar: str | None, rol: str | None, estado: str | None, limite: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    filtros = """
        WHERE eliminado_en IS NULL
          AND (:buscar IS NULL OR nombre LIKE :like OR documento LIKE :like OR email LIKE :like)
          AND (:rol IS NULL OR rol = :rol)
          AND (:estado IS NULL OR estado = :estado)
    """
    params = {"buscar": buscar, "like": f"%{buscar}%" if buscar else None, "rol": rol, "estado": estado}
    total = db.execute(text(f"SELECT COUNT(*) FROM trabajador {filtros}"), params).scalar_one()
    filas = db.execute(
        text(f"SELECT {_COLUMNAS} FROM trabajador {filtros} ORDER BY nombre LIMIT :limite OFFSET :offset"),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()
    return [dict(f) for f in filas], int(total)


def contar_admins_activos(db: Session) -> int:
    return int(
        db.execute(
            text("SELECT COUNT(*) FROM trabajador WHERE rol = 'ADMIN' AND estado = 'ACTIVO' AND eliminado_en IS NULL")
        ).scalar_one()
    )
