from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ConflictoError, NoEncontradoError
from backend.core.seguridad import Usuario
from backend.core.utilidades import desde_centavos, dinero, paginar, respuesta_paginada
from backend.crudDataBase import CRUDcaja
from backend.crudDataBase.CRUDauditoria import registrar_auditoria


def _con_resumen(db: Session, caja: dict[str, Any]) -> dict[str, Any]:
    ventas = CRUDcaja.total_efectivo(db, caja["idcaja"])
    caja["ventas_efectivo"] = ventas
    caja["efectivo_esperado_actual"] = dinero(caja["base_inicial"]) + ventas
    caja["movimientos"] = [
        {
            "idpago": m["idpago"], "idventa": m["idventa"], "referencia": m["referencia"],
            "monto": desde_centavos(m["monto_esperado_centavos"]),
            "recibido": desde_centavos(m["monto_recibido_centavos"] or m["monto_esperado_centavos"]),
            "cambio": desde_centavos(m["cambio_centavos"] or 0),
            "fecha": m["verificado_en"],
        }
        for m in CRUDcaja.movimientos(db, caja["idcaja"])
    ]
    return caja


def abrir(db: Session, usuario: Usuario, base_inicial: Any) -> dict[str, Any]:
    with db.begin():
        if CRUDcaja.caja_abierta(db, usuario.idtrabajador, bloquear=True):
            raise ConflictoError("Ya tienes una caja abierta.", codigo="CAJA_ABIERTA")
        idcaja = CRUDcaja.abrir(db, usuario.idtrabajador, dinero(base_inicial))
        registrar_auditoria(db, "caja", idcaja, "ABRIR", usuario.idtrabajador, {"base_inicial": str(base_inicial)})
        return _con_resumen(db, CRUDcaja.buscar_por_id(db, idcaja))


def actual(db: Session, usuario: Usuario) -> dict[str, Any] | None:
    """Caja abierta del trabajador, o None si está cerrada (estado normal, no un error)."""
    with db.begin():
        caja = CRUDcaja.caja_abierta(db, usuario.idtrabajador)
        return _con_resumen(db, caja) if caja else None


def cerrar(db: Session, usuario: Usuario, efectivo_contado: Any, observacion: str | None) -> dict[str, Any]:
    """Arqueo: esperado = base inicial + ventas en efectivo aprobadas; diferencia = contado - esperado."""
    with db.begin():
        caja = CRUDcaja.caja_abierta(db, usuario.idtrabajador, bloquear=True)
        if not caja:
            raise NoEncontradoError("No tienes una caja abierta.", codigo="CAJA_CERRADA")
        esperado = dinero(caja["base_inicial"]) + CRUDcaja.total_efectivo(db, caja["idcaja"])
        contado = dinero(efectivo_contado)
        CRUDcaja.cerrar(db, caja["idcaja"], esperado, contado, observacion)
        registrar_auditoria(db, "caja", caja["idcaja"], "CERRAR", usuario.idtrabajador,
                            {"esperado": str(esperado), "contado": str(contado), "diferencia": str(contado - esperado)})
        return _con_resumen(db, CRUDcaja.buscar_por_id(db, caja["idcaja"]))


def listar(db: Session, usuario: Usuario, idtrabajador: int | None, page: int, page_size: int) -> dict[str, Any]:
    if not usuario.es_admin:
        idtrabajador = usuario.idtrabajador
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDcaja.listar(db, idtrabajador, limite, offset)
    return respuesta_paginada(items, total, page, limite)
