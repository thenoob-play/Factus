from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ConflictoError, NoEncontradoError, ValidacionError
from backend.core.seguridad import Usuario
from backend.core.utilidades import paginar, respuesta_paginada
from backend.crudDataBase import CRUDproducto
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.services.factus import catalogos


def _preparar(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    datos = dict(datos)
    if hasattr(datos.get("estado"), "value"):
        datos["estado"] = datos["estado"].value
    datos["code_reference"] = datos["code_reference"].upper()
    if datos.get("is_excluded"):
        datos["tax_rate"] = 0
    unidad = datos["unit_measure_code"]
    if catalogos.codigo_en_catalogo(db, "unidades_medida", unidad) is False:
        raise ValidacionError(f"unit_measure_code '{unidad}' no existe en el catálogo de unidades de Factus.")
    return datos


def _con_alerta(producto: dict[str, Any]) -> dict[str, Any]:
    producto["stock_bajo"] = int(producto["stock_disponible"]) <= int(producto["stock_minimo"])
    producto["is_excluded"] = bool(producto["is_excluded"])
    return producto


def crear(db: Session, autor: Usuario, datos: dict[str, Any]) -> dict[str, Any]:
    with db.begin():
        datos = _preparar(db, datos)
        if CRUDproducto.existe_codigo(db, datos["code_reference"]):
            raise ConflictoError("Ya existe un producto con ese code_reference.", codigo="DUPLICADO")
        idproducto = CRUDproducto.crear(db, datos, autor.idtrabajador)
        registrar_auditoria(db, "producto", idproducto, "CREAR", autor.idtrabajador, datos)
    return obtener(db, idproducto)


def obtener(db: Session, idproducto: int) -> dict[str, Any]:
    with db.begin():
        producto = CRUDproducto.buscar_por_id(db, idproducto)
    if not producto:
        raise NoEncontradoError("El producto no existe.")
    return _con_alerta(producto)


def actualizar(db: Session, autor: Usuario, idproducto: int, datos: dict[str, Any]) -> dict[str, Any]:
    datos.pop("stock", None)  # el stock solo cambia con ajustes auditados o ventas
    with db.begin():
        actual = CRUDproducto.buscar_por_id(db, idproducto, bloquear=True)
        if not actual:
            raise NoEncontradoError("El producto no existe.")
        datos = _preparar(db, datos)
        if CRUDproducto.existe_codigo(db, datos["code_reference"], excluir_id=idproducto):
            raise ConflictoError("Ya existe otro producto con ese code_reference.", codigo="DUPLICADO")
        CRUDproducto.actualizar(db, idproducto, datos, autor.idtrabajador)
        cambios = {k: str(v) for k, v in datos.items() if str(actual.get(k)) != str(v)}
        registrar_auditoria(db, "producto", idproducto, "ACTUALIZAR", autor.idtrabajador, cambios)
    return obtener(db, idproducto)


def ajustar_stock(db: Session, autor: Usuario, idproducto: int, delta: int, motivo: str) -> dict[str, Any]:
    with db.begin():
        actual = CRUDproducto.buscar_por_id(db, idproducto, bloquear=True)
        if not actual:
            raise NoEncontradoError("El producto no existe.")
        if not CRUDproducto.ajustar_stock(db, idproducto, delta, autor.idtrabajador):
            raise ConflictoError(
                "El ajuste dejaría el stock por debajo de las unidades reservadas o en negativo.",
                codigo="STOCK_INSUFICIENTE",
                detalles={"stock": actual["stock"], "reservado": actual["stock_reservado"]},
            )
        registrar_auditoria(db, "producto", idproducto, "AJUSTE_STOCK", autor.idtrabajador,
                            {"delta": delta, "motivo": motivo, "stock_anterior": actual["stock"]})
    return obtener(db, idproducto)


def eliminar(db: Session, autor: Usuario, idproducto: int) -> None:
    with db.begin():
        actual = CRUDproducto.buscar_por_id(db, idproducto, bloquear=True)
        if not actual:
            raise NoEncontradoError("El producto no existe.")
        if int(actual["stock_reservado"]) > 0:
            raise ConflictoError("El producto tiene unidades reservadas en ventas pendientes de pago.")
        CRUDproducto.eliminar_logico(db, idproducto, autor.idtrabajador)
        registrar_auditoria(db, "producto", idproducto, "ELIMINAR", autor.idtrabajador)


def listar(db: Session, buscar: str | None, estado: str | None, stock_bajo: bool,
           page: int, page_size: int, ordenar: str = "nombre", desc: bool = False) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDproducto.listar(db, buscar, estado, stock_bajo, limite, offset, ordenar, desc)
    return respuesta_paginada([_con_alerta(i) for i in items], total, page, limite)
