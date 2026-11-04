"""Facturación electrónica con Factus.

Idempotencia (nunca dos facturas para la misma venta):
1. `factura_electronica` tiene UNIQUE(idventa) y UNIQUE(reference_code = referencia de la venta).
2. La emisión "toma" la factura con estado PROCESANDO en una transacción corta; otra
   llamada concurrente recibe 409 mientras tanto.
3. Factus devuelve la factura existente si se reenvía un reference_code ya procesado.
4. Si la llamada falla por timeout o red, se consulta en Factus por reference_code
   antes de marcarla como fallida o reintentar.
Las llamadas HTTP nunca se hacen con una transacción de base de datos abierta.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import AppError, ConfiguracionError, ConflictoError, NoEncontradoError, ValidacionError
from backend.core.seguridad import Usuario
from backend.core.utilidades import ahora_utc, paginar, respuesta_paginada
from backend.crudDataBase import CRUDcliente, CRUDfactura, CRUDpago, CRUDproducto, CRUDventa
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.crudDataBase.configDataBase.conf import settings
from backend.services.factus import mapeo
from backend.services.factus.cliente import (
    FactusClient,
    FactusConflictoError,
    FactusError,
    FactusNoDisponibleError,
    FactusRechazoError,
    extraer_documento,
    obtener_cliente_factus,
)

logger = logging.getLogger(__name__)
PROCESANDO_MAX = timedelta(minutes=5)
_rango_validado_hasta = 0.0


def _fecha(valor: Any) -> datetime | None:
    if not valor:
        return None
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None)
    texto = str(valor).strip().replace("Z", "")
    for formato in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S",
                    "%d-%m-%Y %I:%M:%S %p", "%d-%m-%Y %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto[:26], formato)
        except ValueError:
            continue
    return None


def _validar_rango(cliente: FactusClient) -> None:
    """Comprueba (con caché de 10 min) que el rango configurado exista, esté activo y vigente."""
    global _rango_validado_hasta
    idrango = settings.FACTUS_NUMBERING_RANGE_ID
    if not idrango or time.monotonic() < _rango_validado_hasta:
        return
    rango = cliente.ver_rango(idrango)
    activo = str(rango.get("is_active")).lower() in {"1", "true"}
    vencido = str(rango.get("is_expired")).lower() in {"1", "true"}
    if not activo or vencido:
        raise ConfiguracionError(
            f"FACTUS_NUMBERING_RANGE_ID={idrango} no está activo o está vencido en Factus. "
            "Consulta GET /catalogos/factus/rangos_numeracion y configura un rango vigente."
        )
    _rango_validado_hasta = time.monotonic() + 600


# ----------------------------------------------------------------- emisión
def _tomar_factura(db: Session, idventa: int, idtrabajador: int | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Fase 1 (transacción corta): crea/toma la factura y arma el payload."""
    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
        if not venta:
            raise NoEncontradoError("La venta no existe.")
        factura = CRUDfactura.buscar_por_venta(db, idventa, bloquear=True)
        if factura and factura["estado"] in ("EMITIDA", "ANULADA"):
            return factura, None
        if venta["estado"] not in ("PAGADA", "FACTURA_FALLIDA"):
            raise ConflictoError(f"La venta está {venta['estado']}; solo se facturan ventas pagadas.",
                                 codigo="VENTA_NO_PAGADA")
        ahora = ahora_utc()
        if factura and factura["estado"] == "PROCESANDO" and factura["procesando_desde"] \
                and factura["procesando_desde"] > ahora - PROCESANDO_MAX:
            raise ConflictoError("La factura ya se está emitiendo.", codigo="FACTURA_EN_PROCESO")
        if not factura:
            idfactura = CRUDfactura.crear(db, {
                "idventa": idventa, "idcliente": venta["idcliente"], "idtrabajador": venta["idtrabajador"],
                "reference_code": venta["referencia"], "total": venta["total"],
            })
            factura = CRUDfactura.buscar_por_venta(db, idventa, bloquear=True)
        payload = factura.get("payload_enviado")
        if not payload:
            try:
                cliente = CRUDcliente.buscar_por_id(db, venta["idcliente"])
                pago = CRUDpago.pago_vigente_de_venta(db, idventa)
                if not cliente or not pago or pago["estado"] != "APROBADO":
                    raise ValueError("La venta no tiene cliente o pago aprobado.")
                payload = mapeo.construir_payload_factura(venta, CRUDventa.detalles(db, idventa), cliente, pago)
            except ValueError as error:
                _marcar_fallida(db, factura, venta, str(error), {"validacion_local": str(error)}, idtrabajador)
                return CRUDfactura.buscar_por_id(db, factura["idfactura"]), None
        CRUDfactura.actualizar(db, factura["idfactura"], {
            "estado": "PROCESANDO", "procesando_desde": ahora, "intentos_mas_uno": True,
            "payload_enviado": payload,
            "payment_method_code": payload["payment_details"][0]["payment_method_code"],
        })
        factura["estado"] = "PROCESANDO"
    return factura, payload


def _marcar_fallida(db: Session, factura: dict[str, Any], venta: dict[str, Any], mensaje: str,
                    errores: Any, idtrabajador: int | None) -> None:
    CRUDfactura.actualizar(db, factura["idfactura"], {
        "estado": "FALLIDA", "mensaje": mensaje[:500], "errores": errores, "procesando_desde": None,
    })
    if venta["estado"] != "FACTURA_FALLIDA":
        CRUDventa.cambiar_estado(db, venta["idventa"], venta["estado"], "FACTURA_FALLIDA", mensaje[:255], idtrabajador)
    registrar_auditoria(db, "factura", factura["idfactura"], "FALLIDA", idtrabajador, {"mensaje": mensaje})


def _llamar_factus(cliente: FactusClient, payload: dict[str, Any]) -> dict[str, Any]:
    """Fase 2 (sin transacción): emite, resolviendo timeouts y conflictos de forma idempotente."""
    referencia = payload["reference_code"]
    _validar_rango(cliente)
    try:
        return cliente.validar_factura(payload)
    except FactusConflictoError:
        # Factus documenta el 409 "documento pendiente por enviar a la DIAN": se elimina el
        # pendiente con esa referencia y se crea de nuevo.
        logger.info("Factus 409 para %s: se elimina el documento pendiente y se reintenta.", referencia)
        cliente.eliminar_factura_por_referencia(referencia)
        return cliente.validar_factura(payload)
    except FactusNoDisponibleError:
        # Resultado incierto: puede que Factus sí la haya creado. Se consulta antes de reintentar.
        existente = cliente.buscar_factura_por_referencia(referencia)
        if existente and existente.get("number"):
            logger.info("La factura %s ya existía en Factus tras un error de red.", referencia)
            return cliente.ver_factura(str(existente["number"]))
        raise


def emitir_factura(db: Session, idventa: int, idtrabajador: int | None = None,
                   cliente: FactusClient | None = None) -> dict[str, Any]:
    factura, payload = _tomar_factura(db, idventa, idtrabajador)
    if payload is None:
        return factura

    cliente = cliente or obtener_cliente_factus()
    respuesta: dict[str, Any] | None = None
    error: AppError | None = None
    try:
        respuesta = _llamar_factus(cliente, payload)
    except FactusRechazoError as e:
        error = e
    except (FactusError, ConfiguracionError) as e:
        error = e
    except Exception as e:  # nunca dejar la factura en PROCESANDO
        logger.exception("Error inesperado emitiendo la factura de la venta %s.", idventa)
        error = AppError("Error inesperado al emitir la factura.", detalles={"tipo": type(e).__name__})

    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
        factura = CRUDfactura.buscar_por_venta(db, idventa, bloquear=True)
        if respuesta is not None:
            doc = extraer_documento(respuesta)
            if not doc["numero"]:
                _marcar_fallida(db, factura, venta, "Factus respondió sin número de factura.", respuesta, idtrabajador)
            else:
                CRUDfactura.actualizar(db, factura["idfactura"], {
                    "estado": "EMITIDA", "numero": doc["numero"], "prefijo": doc["prefijo"], "cufe": doc["cufe"],
                    "qr_url": doc["qr_url"], "public_url": doc["public_url"],
                    "is_validated": int(bool(doc["is_validated"])), "validated_at": _fecha(doc["validated_at"]),
                    "mensaje": (doc["mensaje"] or "")[:500] or None, "errores": doc["errores"],
                    "respuesta": respuesta, "procesando_desde": None,
                })
                if venta["estado"] != "FACTURADA":
                    CRUDventa.cambiar_estado(db, idventa, venta["estado"], "FACTURADA",
                                             f"Factura {doc['numero']} emitida.", idtrabajador)
                registrar_auditoria(db, "factura", factura["idfactura"], "EMITIDA", idtrabajador,
                                    {"numero": doc["numero"], "cufe": doc["cufe"]})
        else:
            detalle = getattr(error, "detalles", None)
            _marcar_fallida(db, factura, venta, error.mensaje if error else "Error desconocido.", detalle, idtrabajador)
    return obtener_factura(db, factura["idfactura"])


def emitir_en_segundo_plano(idventa: int) -> None:
    """Para BackgroundTasks: usa su propia sesión y nunca propaga errores."""
    from backend.crudDataBase.configDataBase.dataBase import SessionLocal

    with SessionLocal() as db:
        try:
            emitir_factura(db, idventa)
        except AppError as error:
            logger.warning("No se emitió la factura de la venta %s: %s", idventa, error.mensaje)
        except Exception:
            logger.exception("Fallo emitiendo la factura de la venta %s.", idventa)


def reintentar(db: Session, usuario: Usuario, idfactura: int) -> dict[str, Any]:
    with db.begin():
        factura = CRUDfactura.buscar_por_id(db, idfactura)
    if not factura:
        raise NoEncontradoError("La factura no existe.")
    if factura["estado"] == "EMITIDA":
        raise ConflictoError("La factura ya fue emitida.", codigo="FACTURA_EMITIDA")
    if factura["estado"] == "FALLIDA":
        # El payload se reconstruye: así se aplican correcciones al cliente o a la configuración.
        with db.begin():
            CRUDfactura.actualizar(db, idfactura, {"payload_enviado": None})
    registrar_reintento(db, usuario, idfactura)
    return emitir_factura(db, factura["idventa"], usuario.idtrabajador)


def registrar_reintento(db: Session, usuario: Usuario, idfactura: int) -> None:
    with db.begin():
        registrar_auditoria(db, "factura", idfactura, "REINTENTO", usuario.idtrabajador)


# ------------------------------------------------------------------ consultas
def obtener_factura(db: Session, idfactura: int, *, completo: bool = False) -> dict[str, Any]:
    with db.begin():
        factura = CRUDfactura.buscar_por_id(db, idfactura, completo=completo)
        if not factura:
            raise NoEncontradoError("La factura no existe.")
        factura["is_validated"] = bool(factura["is_validated"])
        if completo:
            factura["venta"] = CRUDventa.buscar_por_id(db, factura["idventa"])
            factura["items"] = CRUDventa.detalles(db, factura["idventa"])
            factura["cliente"] = CRUDcliente.buscar_por_id(db, factura["idcliente"])
            factura["notas_credito"] = CRUDfactura.notas_de_factura(db, idfactura)
    return factura


def listar(db: Session, filtros: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDfactura.listar(db, filtros, limite, offset)
    return respuesta_paginada(items, total, page, limite)


def _emitida(db: Session, idfactura: int) -> dict[str, Any]:
    factura = obtener_factura(db, idfactura)
    if factura["estado"] not in ("EMITIDA", "ANULADA") or not factura["numero"]:
        raise ConflictoError("La factura no ha sido emitida.", codigo="FACTURA_NO_EMITIDA")
    return factura


def descargar(db: Session, idfactura: int, tipo: str, cliente: FactusClient | None = None) -> tuple[bytes, str]:
    """PDF o XML. Se guarda una copia local para no depender de Factus en cada descarga."""
    factura = _emitida(db, idfactura)
    campo = "pdf_path" if tipo == "pdf" else "xml_path"
    if factura.get(campo) and Path(factura[campo]).is_file():
        return Path(factura[campo]).read_bytes(), f"{factura['numero']}.{tipo}"
    cliente = cliente or obtener_cliente_factus()
    contenido, _ = cliente.descargar_pdf(factura["numero"]) if tipo == "pdf" else cliente.descargar_xml(factura["numero"])
    carpeta = Path(settings.STORAGE_DIR) / "facturas"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{factura['idfactura']}_{factura['numero']}.{tipo}"
    ruta.write_bytes(contenido)
    with db.begin():
        CRUDfactura.actualizar(db, idfactura, {campo: str(ruta)})
    return contenido, f"{factura['numero']}.{tipo}"


def enviar_email(db: Session, usuario: Usuario, idfactura: int, email: str | None,
                 cliente: FactusClient | None = None) -> dict[str, Any]:
    factura = _emitida(db, idfactura)
    if not email:
        with db.begin():
            datos_cliente = CRUDcliente.buscar_por_id(db, factura["idcliente"])
        email = (datos_cliente or {}).get("email")
    if not email:
        raise ValidacionError("El cliente no tiene correo; envía uno en el cuerpo.")
    (cliente or obtener_cliente_factus()).enviar_email(factura["numero"], email)
    with db.begin():
        CRUDfactura.actualizar(db, idfactura, {"email_enviado_en": ahora_utc()})
        registrar_auditoria(db, "factura", idfactura, "ENVIAR_EMAIL", usuario.idtrabajador, {"email": email})
    return {"enviado": True, "email": email}


# --------------------------------------------------------------- nota crédito
def crear_nota_credito(db: Session, usuario: Usuario, idfactura: int, datos: dict[str, Any],
                       cliente: FactusClient | None = None) -> dict[str, Any]:
    with db.begin():
        factura = CRUDfactura.buscar_por_id(db, idfactura, bloquear=True)
        if not factura:
            raise NoEncontradoError("La factura no existe.")
        if factura["estado"] != "EMITIDA" or not factura["numero"]:
            raise ConflictoError("Solo se emiten notas crédito sobre facturas emitidas.", codigo="FACTURA_NO_EMITIDA")
        detalles = CRUDventa.detalles(db, factura["idventa"])
        vendidas = {int(d["idproducto"]): int(d["cantidad"]) for d in detalles}
        devueltas = CRUDfactura.cantidades_devueltas(db, idfactura)
        disponibles = {pid: vendidas[pid] - devueltas.get(pid, 0) for pid in vendidas}
        if datos.get("items"):
            cantidades: dict[int, int] = {}
            for item in datos["items"]:
                cantidades[item["idproducto"]] = cantidades.get(item["idproducto"], 0) + item["cantidad"]
            excedidos = [pid for pid, c in cantidades.items() if c > disponibles.get(pid, 0)]
            if excedidos:
                raise ValidacionError("La nota crédito supera las unidades facturadas no devueltas.",
                                      detalles={"productos": excedidos, "disponibles": disponibles})
        else:
            cantidades = {pid: c for pid, c in disponibles.items() if c > 0}
        if not cantidades:
            raise ConflictoError("No quedan unidades por acreditar en esta factura.")

        venta = CRUDventa.buscar_por_id(db, factura["idventa"])
        pago = CRUDpago.pago_vigente_de_venta(db, factura["idventa"]) or {}
        datos_cliente = CRUDcliente.buscar_por_id(db, factura["idcliente"])
        numero_nota = len(CRUDfactura.notas_de_factura(db, idfactura)) + 1
        reference = f"NC-{factura['reference_code']}-{numero_nota}"
        try:
            payload = mapeo.construir_payload_nota_credito(
                factura, detalles, datos_cliente, cantidades, datos["correction_concept_code"], datos["motivo"],
                reference, venta["metodo_pago"], pago.get("tarjeta_tipo"),
            )
        except ValueError as error:
            raise ValidacionError(str(error)) from error
        idnota = CRUDfactura.crear_nota(db, {
            "idfactura": idfactura, "reference_code": reference,
            "correction_concept_code": datos["correction_concept_code"], "motivo": datos["motivo"],
            "total": payload["payment_details"][0]["amount"], "restaura_stock": datos.get("restaurar_stock", True),
            "items": [{"idproducto": pid, "cantidad": c} for pid, c in cantidades.items()],
            "idtrabajador": usuario.idtrabajador,
        })
        CRUDfactura.actualizar_nota(db, idnota, {"payload_enviado": payload})
        registrar_auditoria(db, "nota_credito", idnota, "CREAR", usuario.idtrabajador,
                            {"idfactura": idfactura, "concepto": datos["correction_concept_code"]})
    return _enviar_nota(db, usuario, idnota, payload, cliente)


def reintentar_nota_credito(db: Session, usuario: Usuario, idnota: int,
                            cliente: FactusClient | None = None) -> dict[str, Any]:
    """Reenvía una nota PENDIENTE con la misma referencia (Factus devuelve la existente si ya la creó)."""
    with db.begin():
        nota = CRUDfactura.buscar_nota(db, idnota, con_payload=True)
    if not nota:
        raise NoEncontradoError("La nota crédito no existe.")
    if nota["estado"] != "PENDIENTE" or not nota.get("payload_enviado"):
        raise ConflictoError(f"La nota crédito está {nota['estado']}; solo se reintentan las pendientes.")
    return _enviar_nota(db, usuario, idnota, nota["payload_enviado"], cliente)


def _enviar_nota(db: Session, usuario: Usuario, idnota: int, payload: dict[str, Any],
                 cliente: FactusClient | None) -> dict[str, Any]:
    cliente = cliente or obtener_cliente_factus()
    respuesta: dict[str, Any] | None = None
    error: AppError | None = None
    incierto = False
    try:
        respuesta = cliente.validar_nota_credito(payload)
    except FactusNoDisponibleError as e:
        # Resultado incierto (timeout/red): queda PENDIENTE para reintentar con la misma referencia.
        error, incierto = e, True
    except (FactusError, ConfiguracionError) as e:
        error = e

    with db.begin():
        nota = CRUDfactura.buscar_nota(db, idnota, bloquear=True)
        idfactura = nota["idfactura"]
        if respuesta is not None:
            doc = extraer_documento(respuesta)
            CRUDfactura.actualizar_nota(db, idnota, {"estado": "EMITIDA", "numero": doc["numero"],
                                                     "cufe": doc["cufe"], "respuesta": respuesta, "errores": None})
            if nota["restaura_stock"] and not nota["stock_restaurado"]:
                for item in nota["items"]:
                    CRUDproducto.devolver_stock(db, int(item["idproducto"]), int(item["cantidad"]))
                CRUDfactura.actualizar_nota(db, idnota, {"stock_restaurado": 1})
            factura = CRUDfactura.buscar_por_id(db, idfactura, bloquear=True)
            vendidas = {int(d["idproducto"]): int(d["cantidad"]) for d in CRUDventa.detalles(db, factura["idventa"])}
            devueltas = CRUDfactura.cantidades_devueltas(db, idfactura)
            if nota["correction_concept_code"] == "2" or all(devueltas.get(p, 0) >= c for p, c in vendidas.items()):
                CRUDfactura.actualizar(db, idfactura, {"estado": "ANULADA"})
            registrar_auditoria(db, "nota_credito", idnota, "EMITIDA", usuario.idtrabajador, {"numero": doc["numero"]})
        else:
            detalle = getattr(error, "detalles", None) or {"mensaje": str(error)}
            CRUDfactura.actualizar_nota(db, idnota, {"estado": "PENDIENTE" if incierto else "FALLIDA",
                                                     "errores": detalle})
            registrar_auditoria(db, "nota_credito", idnota, "PENDIENTE" if incierto else "FALLIDA",
                                usuario.idtrabajador, {"mensaje": getattr(error, "mensaje", str(error))})
    with db.begin():
        nota = CRUDfactura.buscar_nota(db, idnota)
    if error is not None:
        raise ConflictoError(
            f"Factus no emitió la nota crédito: {getattr(error, 'mensaje', error)}"
            + (" Reintenta con POST /facturas/notas-credito/{idnota}/reintentar." if incierto else ""),
            codigo="NOTA_CREDITO_PENDIENTE" if incierto else "NOTA_CREDITO_FALLIDA",
            detalles={"idnota": idnota, "factus": getattr(error, "detalles", None)},
        )
    return nota
