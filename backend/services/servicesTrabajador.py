from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ConflictoError, NoEncontradoError, ValidacionError
from backend.core.seguridad import Usuario, hash_password
from backend.core.utilidades import paginar, respuesta_paginada
from backend.crudDataBase import CRUDtrabajador
from backend.crudDataBase.CRUDauditoria import registrar_auditoria


def _normalizar(datos: dict[str, Any]) -> dict[str, Any]:
    datos = dict(datos)
    datos["email"] = str(datos["email"]).lower()
    for clave in ("rol", "estado"):
        if hasattr(datos.get(clave), "value"):
            datos[clave] = datos[clave].value
    return datos


def crear(db: Session, autor: Usuario, datos: dict[str, Any]) -> dict[str, Any]:
    datos = _normalizar(datos)
    with db.begin():
        duplicado = CRUDtrabajador.existe_duplicado(db, datos["email"], datos["tipo_documento"], datos["documento"])
        if duplicado:
            raise ConflictoError(f"Ya existe un trabajador con ese {duplicado}.", codigo="DUPLICADO")
        datos["password_hash"] = hash_password(datos.pop("password"))
        idtrabajador = CRUDtrabajador.crear(db, datos, autor.idtrabajador)
        registrar_auditoria(db, "trabajador", idtrabajador, "CREAR", autor.idtrabajador,
                            {k: v for k, v in datos.items() if k != "password_hash"})
    return obtener(db, idtrabajador)


def obtener(db: Session, idtrabajador: int) -> dict[str, Any]:
    with db.begin():
        trabajador = CRUDtrabajador.buscar_por_id(db, idtrabajador)
    if not trabajador:
        raise NoEncontradoError("El trabajador no existe.")
    return trabajador


def actualizar(db: Session, autor: Usuario, idtrabajador: int, datos: dict[str, Any]) -> dict[str, Any]:
    datos = _normalizar(datos)
    with db.begin():
        actual = CRUDtrabajador.buscar_por_id(db, idtrabajador)
        if not actual:
            raise NoEncontradoError("El trabajador no existe.")
        duplicado = CRUDtrabajador.existe_duplicado(
            db, datos["email"], datos["tipo_documento"], datos["documento"], excluir_id=idtrabajador
        )
        if duplicado:
            raise ConflictoError(f"Ya existe un trabajador con ese {duplicado}.", codigo="DUPLICADO")
        quita_admin = actual["rol"] == "ADMIN" and (datos["rol"] != "ADMIN" or datos["estado"] != "ACTIVO")
        if quita_admin and CRUDtrabajador.contar_admins_activos(db) <= 1:
            raise ValidacionError("No puedes quitar o desactivar al único administrador activo.")
        password = datos.pop("password", None)
        if password:
            datos["password_hash"] = hash_password(password)
        CRUDtrabajador.actualizar(db, idtrabajador, datos, autor.idtrabajador)
        cambios = {k: v for k, v in datos.items() if k != "password_hash" and actual.get(k) != v}
        if password:
            cambios["password"] = "actualizada"
        registrar_auditoria(db, "trabajador", idtrabajador, "ACTUALIZAR", autor.idtrabajador, cambios)
    return obtener(db, idtrabajador)


def eliminar(db: Session, autor: Usuario, idtrabajador: int) -> None:
    if idtrabajador == autor.idtrabajador:
        raise ValidacionError("No puedes eliminar tu propia cuenta.")
    with db.begin():
        actual = CRUDtrabajador.buscar_por_id(db, idtrabajador)
        if not actual:
            raise NoEncontradoError("El trabajador no existe.")
        if actual["rol"] == "ADMIN" and CRUDtrabajador.contar_admins_activos(db) <= 1:
            raise ValidacionError("No puedes eliminar al único administrador activo.")
        CRUDtrabajador.eliminar_logico(db, idtrabajador, autor.idtrabajador)
        registrar_auditoria(db, "trabajador", idtrabajador, "ELIMINAR", autor.idtrabajador)


def listar(db: Session, buscar: str | None, rol: str | None, estado: str | None,
           page: int, page_size: int) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDtrabajador.listar(db, buscar, rol, estado, limite, offset)
    return respuesta_paginada(items, total, page, limite)
