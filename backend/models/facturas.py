"""Facturas electrónicas, notas crédito, catálogos Factus, dashboard, reportes y auditoría."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.core.seguridad import SoloAdmin, UsuarioActual
from backend.core.utilidades import ZONA_COLOMBIA, a_utc, paginar, respuesta_paginada
from backend.crudDataBase import CRUDreportes
from backend.crudDataBase.CRUDauditoria import listar_auditoria
from backend.crudDataBase.configDataBase.dataBase import get_db
from backend.services import servicesFacturacion, servicesReportes
from backend.services.factus import catalogos
from backend.services.factus.cliente import obtener_cliente_factus
from backend.schemas.esquemas import EnviarEmailIn, NotaCreditoIn, RefrescarCatalogosIn

DB = Annotated[Session, Depends(get_db)]
Pagina = Annotated[int, Query(ge=1)]
Tamano = Annotated[int, Query(ge=1, le=100)]


def _filtros(estado, metodo_pago, idtrabajador, idcliente, desde, hasta, buscar) -> dict:
    return {
        "estado": estado, "metodo": metodo_pago, "idtrabajador": idtrabajador, "idcliente": idcliente,
        "desde": a_utc(datetime.combine(desde, time.min, ZONA_COLOMBIA)) if desde else None,
        "hasta": a_utc(datetime.combine(hasta, time.min, ZONA_COLOMBIA) + timedelta(days=1)) if hasta else None,
        "buscar": buscar,
    }


# --------------------------------------------------------------------- facturas
facturas = APIRouter(prefix="/facturas", tags=["Facturas"])
EstadoFactura = Literal["PENDIENTE", "PROCESANDO", "EMITIDA", "FALLIDA", "ANULADA"]
Metodo = Literal["EFECTIVO", "TRANSFERENCIA", "TARJETA"]


@facturas.get("", summary="Listar facturas con filtros (fecha, estado, método de pago, trabajador)")
def listar(_: UsuarioActual, db: DB, estado: EstadoFactura | None = None, metodo_pago: Metodo | None = None,
           idtrabajador: int | None = None, desde: date | None = None, hasta: date | None = None,
           buscar: Annotated[str | None, Query(max_length=100, description="Documento, nombre o número")] = None,
           page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesFacturacion.listar(db, _filtros(estado, metodo_pago, idtrabajador, None, desde, hasta, buscar),
                                      page, page_size)


@facturas.get("/cliente/{idcliente}", summary="Facturas de un cliente")
def por_cliente(idcliente: int, _: UsuarioActual, db: DB, page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesFacturacion.listar(db, _filtros(None, None, None, idcliente, None, None, None), page, page_size)


@facturas.get("/{idfactura}", summary="Detalle completo (payload enviado, respuesta de Factus, notas crédito)")
def detalle(idfactura: int, _: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.obtener_factura(db, idfactura, completo=True)


@facturas.get("/{idfactura}/pdf", summary="Descargar PDF (copia local en caché)",
              response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def pdf(idfactura: int, _: UsuarioActual, db: DB) -> Response:
    contenido, nombre = servicesFacturacion.descargar(db, idfactura, "pdf")
    return Response(contenido, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@facturas.get("/{idfactura}/xml", summary="Descargar XML",
              response_class=Response, responses={200: {"content": {"application/xml": {}}}})
def xml(idfactura: int, _: UsuarioActual, db: DB) -> Response:
    contenido, nombre = servicesFacturacion.descargar(db, idfactura, "xml")
    return Response(contenido, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@facturas.post("/{idfactura}/enviar-email", summary="Reenviar la factura al correo del cliente")
def enviar_email(idfactura: int, datos: EnviarEmailIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.enviar_email(db, usuario, idfactura, datos.email)


@facturas.post("/{idfactura}/reintentar", summary="Reintentar una emisión fallida")
def reintentar(idfactura: int, usuario: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.reintentar(db, usuario, idfactura)


@facturas.post("/ventas/{idventa}/emitir", summary="Emitir manualmente la factura de una venta pagada")
def emitir(idventa: int, usuario: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.emitir_factura(db, idventa, usuario.idtrabajador)


@facturas.post("/{idfactura}/nota-credito", summary="Nota crédito para anular o devolver (restaura stock)")
def nota_credito(idfactura: int, datos: NotaCreditoIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.crear_nota_credito(db, usuario, idfactura, datos.model_dump())


@facturas.post("/notas-credito/{idnota}/reintentar", summary="Reintentar una nota crédito pendiente")
def reintentar_nota(idnota: int, usuario: UsuarioActual, db: DB) -> dict:
    return servicesFacturacion.reintentar_nota_credito(db, usuario, idnota)


# -------------------------------------------------------------------- catálogos
catalogos_router = APIRouter(prefix="/catalogos/factus", tags=["Catálogos Factus"])


@catalogos_router.get("", summary="Catálogos disponibles y su última sincronización")
def listar_catalogos(_: UsuarioActual, db: DB) -> dict:
    with db.begin():
        sincronizados = CRUDreportes.listar_catalogos(db)
    return {"tipos": list(catalogos.TIPOS), "sincronizados": sincronizados}


@catalogos_router.get("/{tipo}", summary="Ver un catálogo")
def ver_catalogo(tipo: Literal[catalogos.TIPOS], _: UsuarioActual, db: DB,  # type: ignore[valid-type]
                 buscar: Annotated[str | None, Query(max_length=60)] = None) -> dict:
    with db.begin():
        datos = catalogos.leer(db, tipo) or []
    if buscar:
        b = buscar.lower()
        datos = [d for d in datos if b in str(d.get("name", "")).lower() or b == str(d.get("code", "")).lower()]
    return {"tipo": tipo, "registros": len(datos), "datos": datos[:500]}


@catalogos_router.post("/refrescar", summary="Sincronizar catálogos desde Factus (ADMIN)")
def refrescar(datos: RefrescarCatalogosIn, _: SoloAdmin, db: DB) -> dict:
    return catalogos.refrescar(db, obtener_cliente_factus(), datos.tipos)


# ------------------------------------------------------ dashboard y reportes
reportes = APIRouter(tags=["Dashboard y reportes (ADMIN)"])


@reportes.get("/dashboard", summary="Ventas del día/mes, métodos de pago, top productos, alertas")
def dashboard(_: SoloAdmin, db: DB) -> dict:
    return servicesReportes.dashboard(db)


@reportes.get("/reportes/resumen", summary="Totales por rango de fechas y por método de pago")
def resumen(_: SoloAdmin, db: DB, desde: date, hasta: date) -> dict:
    return servicesReportes.resumen(db, desde, hasta)


@reportes.get("/reportes/{tipo}.csv", summary="Exportar ventas o facturas (CSV compatible con Excel)",
              response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def exportar(tipo: Literal["ventas", "facturas"], _: SoloAdmin, db: DB, desde: date, hasta: date) -> Response:
    contenido = servicesReportes.csv_reporte(db, tipo, desde, hasta)
    return Response(contenido, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{tipo}_{desde}_{hasta}.csv"'})


@reportes.get("/auditoria", summary="Registro de auditoría")
def auditoria(_: SoloAdmin, db: DB, entidad: str | None = None, entidad_id: str | None = None,
              page: Pagina = 1, page_size: Tamano = 50) -> dict:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = listar_auditoria(db, entidad, entidad_id, limite, offset)
    return respuesta_paginada(items, total, page, limite)
