import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc


def registrar_auditoria(
    db: Session,
    entidad: str,
    entidad_id: Any,
    accion: str,
    idtrabajador: int | None,
    datos: dict[str, Any] | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO auditoria (entidad, entidad_id, accion, idtrabajador, datos, creado_en)
            VALUES (:entidad, :entidad_id, :accion, :idtrabajador, CAST(:datos AS JSON), :ahora)
            """
        ),
        {
            "entidad": entidad,
            "entidad_id": str(entidad_id),
            "accion": accion,
            "idtrabajador": idtrabajador,
            "datos": json.dumps(datos, ensure_ascii=False, default=str) if datos else None,
            "ahora": ahora_utc(),
        },
    )


def listar_auditoria(
    db: Session, entidad: str | None, entidad_id: str | None, limite: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    filtros = "WHERE (:entidad IS NULL OR entidad = :entidad) AND (:eid IS NULL OR entidad_id = :eid)"
    params = {"entidad": entidad, "eid": entidad_id}
    total = db.execute(text(f"SELECT COUNT(*) FROM auditoria {filtros}"), params).scalar_one()
    filas = db.execute(
        text(
            f"""
            SELECT idauditoria, entidad, entidad_id, accion, idtrabajador, datos, creado_en
            FROM auditoria {filtros}
            ORDER BY idauditoria DESC LIMIT :limite OFFSET :offset
            """
        ),
        {**params, "limite": limite, "offset": offset},
    ).mappings().all()
    items = []
    for fila in filas:
        item = dict(fila)
        if isinstance(item.get("datos"), str):
            item["datos"] = json.loads(item["datos"])
        items.append(item)
    return items, int(total)
