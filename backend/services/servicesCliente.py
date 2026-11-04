from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ConflictoError, NoEncontradoError, ValidacionError
from backend.core.seguridad import Usuario
from backend.core.utilidades import paginar, respuesta_paginada
from backend.crudDataBase import CRUDcliente
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.services.factus import catalogos
from backend.services.factus.mapeo import calcular_dv_nit


def _preparar(db: Session, datos: dict[str, Any]) -> dict[str, Any]:
    """Normaliza y valida contra los catálogos de Factus para no fallar al facturar."""
    datos = dict(datos)
    if hasattr(datos.get("estado"), "value"):
        datos["estado"] = datos["estado"].value
    tipo = datos["identification_document_code"]
    if tipo not in catalogos.codigos("tipos_documento"):
        raise ValidacionError(f"identification_document_code '{tipo}' no existe en el catálogo de Factus.")
    if tipo == "31":
        dv = calcular_dv_nit(datos["identification"])
        if datos.get("dv") and datos["dv"] != dv:
            raise ValidacionError(f"El dígito de verificación no es válido para ese NIT (debe ser {dv}).")
        datos["dv"] = dv
    else:
        datos["dv"] = None
    if datos["legal_organization_code"] == "1":
        datos["names"] = None
    else:
        datos["company"] = None
    if datos.get("email"):
        datos["email"] = str(datos["email"]).lower()
    municipio = datos.get("municipality_code")
    if municipio and catalogos.codigo_en_catalogo(db, "municipios", municipio) is False:
        raise ValidacionError(f"municipality_code '{municipio}' no existe en el catálogo de municipios de Factus.")
    return datos


def crear(db: Session, autor: Usuario, datos: dict[str, Any]) -> dict[str, Any]:
    with db.begin():
        datos = _preparar(db, datos)
        if CRUDcliente.existe_documento(db, datos["identification_document_code"], datos["identification"]):
            raise ConflictoError("Ya existe un cliente con ese tipo y número de documento.", codigo="DUPLICADO")
        idcliente = CRUDcliente.crear(db, datos, autor.idtrabajador)
        registrar_auditoria(db, "cliente", idcliente, "CREAR", autor.idtrabajador, datos)
    return obtener(db, idcliente)


def obtener(db: Session, idcliente: int) -> dict[str, Any]:
    with db.begin():
        cliente = CRUDcliente.buscar_por_id(db, idcliente)
    if not cliente:
        raise NoEncontradoError("El cliente no existe.")
    return cliente


def actualizar(db: Session, autor: Usuario, idcliente: int, datos: dict[str, Any]) -> dict[str, Any]:
    with db.begin():
        actual = CRUDcliente.buscar_por_id(db, idcliente, bloquear=True)
        if not actual:
            raise NoEncontradoError("El cliente no existe.")
        datos = _preparar(db, datos)
        if CRUDcliente.existe_documento(db, datos["identification_document_code"], datos["identification"],
                                        excluir_id=idcliente):
            raise ConflictoError("Ya existe otro cliente con ese tipo y número de documento.", codigo="DUPLICADO")
        CRUDcliente.actualizar(db, idcliente, datos, autor.idtrabajador)
        cambios = {k: v for k, v in datos.items() if actual.get(k) != v}
        registrar_auditoria(db, "cliente", idcliente, "ACTUALIZAR", autor.idtrabajador, cambios)
    return obtener(db, idcliente)


def eliminar(db: Session, autor: Usuario, idcliente: int) -> None:
    with db.begin():
        if not CRUDcliente.eliminar_logico(db, idcliente, autor.idtrabajador):
            raise NoEncontradoError("El cliente no existe.")
        registrar_auditoria(db, "cliente", idcliente, "ELIMINAR", autor.idtrabajador)


def listar(db: Session, buscar: str | None, estado: str | None, page: int, page_size: int,
           ordenar: str = "nombre", desc: bool = False) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDcliente.listar(db, buscar, estado, limite, offset, ordenar, desc)
    return respuesta_paginada(items, total, page, limite)
