"""Ventas, pagos (efectivo, datáfono, transferencia manual, Wompi) y cajas."""

from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Request, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.core.errores import ValidacionError
from backend.core.rate_limit import LimitadorVentana, ip_cliente
from backend.core.seguridad import SoloAdmin, UsuarioActual
from backend.core.utilidades import ZONA_COLOMBIA, a_utc
from backend.crudDataBase.configDataBase.conf import settings
from backend.crudDataBase.configDataBase.dataBase import get_db
from backend.services import servicesCaja, servicesPago, servicesVenta
from backend.services.pagos.proveedores import obtener_wompi
from backend.services.servicesFacturacion import emitir_en_segundo_plano
from backend.shemas.esquemas import (
    AbrirCajaIn,
    CancelarVentaIn,
    CerrarCajaIn,
    ComprobanteIn,
    ComprobantePublicoIn,
    DatafonoIn,
    EfectivoIn,
    RegenerarPagoIn,
    VentaIn,
    VerificarComprobanteIn,
)

DB = Annotated[Session, Depends(get_db)]
Pagina = Annotated[int, Query(ge=1)]
Tamano = Annotated[int, Query(ge=1, le=100)]

limitador_webhooks = LimitadorVentana(settings.WEBHOOK_RATE_LIMIT, settings.WEBHOOK_RATE_WINDOW_SECONDS)


def _facturar_si_aprobado(resultado: dict[str, Any], tareas: BackgroundTasks) -> dict[str, Any]:
    """Al aprobar un pago se dispara la facturación automática (en segundo plano)."""
    if resultado.get("aprobado"):
        tareas.add_task(emitir_en_segundo_plano, resultado["idventa"])
        resultado["facturacion"] = "en_proceso"
    return resultado


# ---------------------------------------------------------------------- ventas
ventas = APIRouter(prefix="/ventas", tags=["Ventas"])


@ventas.post("", status_code=status.HTTP_201_CREATED, summary="Crear venta (reserva stock y genera el pago)")
def crear_venta(
    datos: VentaIn, usuario: UsuarioActual, db: DB,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=8, max_length=128)] = None,
) -> dict:
    return servicesVenta.crear_venta(db, usuario, datos.model_dump(), idempotency_key)


@ventas.get("", summary="Listar ventas (paginado)")
def listar_ventas(
    _: UsuarioActual, db: DB,
    estado: Literal["PENDIENTE_PAGO", "PAGADA", "FACTURADA", "EXPIRADA", "CANCELADA", "FACTURA_FALLIDA"] | None = None,
    metodo_pago: Literal["EFECTIVO", "TRANSFERENCIA", "TARJETA"] | None = None,
    idcliente: int | None = None, idtrabajador: int | None = None,
    desde: date | None = None, hasta: date | None = None,
    buscar: Annotated[str | None, Query(min_length=1, max_length=100,
                                        description="Referencia, documento o nombre del cliente")] = None,
    page: Pagina = 1, page_size: Tamano = 20,
) -> dict:
    filtros = {"estado": estado, "metodo": metodo_pago, "idcliente": idcliente, "idtrabajador": idtrabajador,
               "buscar": buscar, **_rango_fechas(desde, hasta)}
    return servicesVenta.listar_ventas(db, filtros, page, page_size)


@ventas.get("/{idventa}", summary="Detalle de la venta (ítems, impuestos, pagos, historial)")
def ver_venta(idventa: int, _: UsuarioActual, db: DB) -> dict:
    return servicesVenta.obtener_venta(db, idventa)


@ventas.get("/{idventa}/qr", summary="QR del pago pendiente (PNG base64, monto, referencia, expiración)")
def qr_venta(idventa: int, _: UsuarioActual, db: DB) -> dict:
    return servicesVenta.obtener_qr(db, idventa)


@ventas.get("/{idventa}/comprobante", summary="Comprobante del pago aprobado")
def comprobante(idventa: int, _: UsuarioActual, db: DB) -> dict:
    return servicesVenta.comprobante(db, idventa)


@ventas.post("/{idventa}/cancelar", summary="Cancelar venta pendiente (libera stock)")
def cancelar(idventa: int, datos: CancelarVentaIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesVenta.cancelar_venta(db, usuario, idventa, datos.motivo)


@ventas.post("/{idventa}/pagos/regenerar", summary="Anular el pago pendiente y generar uno nuevo")
def regenerar(idventa: int, datos: RegenerarPagoIn, usuario: UsuarioActual, db: DB) -> dict:
    metodo = datos.metodo_pago.value if datos.metodo_pago else None
    canal = datos.canal.value if datos.canal else None
    return servicesVenta.regenerar_pago(db, usuario, idventa, metodo, canal, datos.motivo)


@ventas.post("/{idventa}/pagos/efectivo", summary="Registrar pago en efectivo (requiere caja abierta)")
def pagar_efectivo(idventa: int, datos: EfectivoIn, usuario: UsuarioActual, db: DB,
                   tareas: BackgroundTasks) -> dict:
    return _facturar_si_aprobado(servicesPago.registrar_efectivo(db, usuario, idventa, datos.monto_recibido), tareas)


@ventas.post("/{idventa}/pagos/datafono", summary="Registrar pago con datáfono físico")
def pagar_datafono(idventa: int, datos: DatafonoIn, usuario: UsuarioActual, db: DB,
                   tareas: BackgroundTasks) -> dict:
    return _facturar_si_aprobado(servicesPago.registrar_datafono(db, usuario, idventa, datos.model_dump()), tareas)


@ventas.post("/{idventa}/pagos/comprobante", summary="Subir comprobante de transferencia (trabajador)")
def subir_comprobante(idventa: int, datos: ComprobanteIn, usuario: UsuarioActual, db: DB,
                      request: Request) -> dict:
    return servicesPago.registrar_comprobante(db, idventa, datos.model_dump(), usuario=usuario,
                                              ip=ip_cliente(request))


def _rango_fechas(desde: date | None, hasta: date | None) -> dict[str, datetime | None]:
    return {
        "desde": a_utc(datetime.combine(desde, time.min, ZONA_COLOMBIA)) if desde else None,
        "hasta": a_utc(datetime.combine(hasta, time.min, ZONA_COLOMBIA) + timedelta(days=1)) if hasta else None,
    }


# ----------------------------------------------------------------------- pagos
pagos = APIRouter(prefix="/pagos", tags=["Pagos"])


@pagos.get("/comprobantes-pendientes", summary="Transferencias con comprobante por verificar")
def comprobantes_pendientes(_: UsuarioActual, db: DB, page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesPago.comprobantes_por_verificar(db, page, page_size)


@pagos.post("/{idpago}/verificar", summary="Aprobar o rechazar un comprobante tras revisar el banco")
def verificar(idpago: int, datos: VerificarComprobanteIn, usuario: UsuarioActual, db: DB,
              tareas: BackgroundTasks) -> dict:
    resultado = servicesPago.verificar_comprobante(db, usuario, idpago, datos.aprobar, datos.monto_verificado,
                                                   datos.motivo)
    return _facturar_si_aprobado(resultado, tareas)


@pagos.get("/intentos-sospechosos", summary="Intentos de pago sospechosos (ADMIN)")
def sospechosos(_: SoloAdmin, db: DB, page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesPago.intentos_sospechosos(db, page, page_size)


@pagos.post("/publico/{referencia}/comprobante", summary="El cliente sube su comprobante (con la firma del QR)")
def comprobante_publico(referencia: str, datos: ComprobantePublicoIn, request: Request, db: DB) -> dict:
    ip = ip_cliente(request)
    limitador_webhooks.verificar(f"comprobante:{ip}")
    contenido = datos.model_dump(exclude={"firma"})
    return servicesPago.registrar_comprobante(db, None, contenido, usuario=None, referencia=referencia,
                                              firma=datos.firma, ip=ip)


@pagos.post("/webhooks/wompi", summary="Webhook firmado de Wompi (idempotente)")
async def webhook_wompi(request: Request, tareas: BackgroundTasks, db: DB) -> dict:
    ip = ip_cliente(request)
    limitador_webhooks.verificar(f"webhook:{ip}")
    try:
        evento = await request.json()
    except ValueError:
        evento = None
    if not isinstance(evento, dict):
        raise ValidacionError("Cuerpo JSON inválido.")
    proveedor = obtener_wompi()
    # La consulta a Wompi y la base de datos son bloqueantes: se ejecutan fuera del event loop.
    resultado = await run_in_threadpool(
        servicesPago.procesar_webhook_wompi, db, proveedor, evento, request.headers.get("X-Event-Checksum"), ip
    )
    return _facturar_si_aprobado(resultado, tareas)


# ----------------------------------------------------------------------- cajas
cajas = APIRouter(prefix="/cajas", tags=["Caja"])


@cajas.post("/abrir", status_code=status.HTTP_201_CREATED, summary="Abrir caja con base inicial")
def abrir_caja(datos: AbrirCajaIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesCaja.abrir(db, usuario, datos.base_inicial)


@cajas.get("/actual", summary="Mi caja abierta y el efectivo esperado (null si está cerrada)")
def caja_actual(usuario: UsuarioActual, db: DB) -> dict | None:
    return servicesCaja.actual(db, usuario)


@cajas.post("/cerrar", summary="Cerrar caja con arqueo (esperado vs contado)")
def cerrar_caja(datos: CerrarCajaIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesCaja.cerrar(db, usuario, datos.efectivo_contado, datos.observacion)


@cajas.get("", summary="Historial de cajas (un trabajador ve solo las suyas)")
def listar_cajas(usuario: UsuarioActual, db: DB, idtrabajador: int | None = None,
                 page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesCaja.listar(db, usuario, idtrabajador, page, page_size)
