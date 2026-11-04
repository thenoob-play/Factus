"""Pagos verificables.

Reglas clave:
- Cada pago tiene monto en centavos, moneda, referencia única y firma HMAC calculados
  al crearlo; nada de eso se puede editar (lo garantiza también un trigger de MySQL).
- Toda confirmación recalcula la firma y compara el monto recibido con el firmado.
  Si no coinciden, el pago queda RECHAZADO y el intento se marca como sospechoso.
- Al aprobar: pago APROBADO, venta PAGADA, stock reservado descontado y auditoría,
  todo en una sola transacción. La facturación se dispara después.
- Orden de bloqueo en todas las operaciones: venta → pago → productos (evita deadlocks).
"""

from __future__ import annotations

import base64
import binascii
import hmac
import logging
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import (
    ConfiguracionError,
    ConflictoError,
    NoAutenticadoError,
    NoEncontradoError,
    ValidacionError,
)
from backend.core.seguridad import Usuario
from backend.core.utilidades import a_centavos, a_utc, ahora_utc, desde_centavos, paginar, respuesta_paginada
from backend.crudDataBase import CRUDcaja, CRUDpago, CRUDproducto, CRUDventa
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.crudDataBase.configDataBase.conf import settings
from backend.services.pagos import firma as firma_pago
from backend.services.pagos.proveedores import WompiProvider, generar_qr_png_base64, proveedor_para

logger = logging.getLogger(__name__)

CANALES_POR_METODO = {
    "EFECTIVO": {"EFECTIVO"},
    "TRANSFERENCIA": {"WOMPI", "BREB_MANUAL"},
    "TARJETA": {"WOMPI", "DATAFONO"},
}


def resolver_canal(metodo: str, canal: str | None) -> str:
    if metodo == "EFECTIVO":
        if canal not in (None, "EFECTIVO"):
            raise ValidacionError("El pago en efectivo no admite canal.")
        return "EFECTIVO"
    if canal is None:
        if settings.PAYMENT_PROVIDER == "wompi":
            canal = "WOMPI"
        else:
            canal = "BREB_MANUAL" if metodo == "TRANSFERENCIA" else "DATAFONO"
    if canal not in CANALES_POR_METODO[metodo]:
        raise ValidacionError(f"El canal {canal} no es válido para {metodo}.")
    return canal


# ----------------------------------------------------------------- creación
def crear_pago(db: Session, venta: dict[str, Any], cliente: dict[str, Any], metodo: str,
               canal: str | None, idtrabajador: int, referencia: str) -> int:
    """Crea el pago firmado de la venta (dentro de la transacción del llamador)."""
    canal = resolver_canal(metodo, canal)
    monto = a_centavos(venta["total"])
    if monto <= 0:
        raise ValidacionError("El total de la venta debe ser mayor que 0.")
    moneda = settings.PAYMENT_CURRENCY
    expira_en = ahora_utc() + timedelta(minutes=settings.PAYMENT_EXPIRATION_MINUTES)
    firma = firma_pago.firmar(referencia, monto, moneda, expira_en)
    idpago = CRUDpago.crear(db, {
        "idventa": venta["idventa"], "metodo": metodo, "canal": canal,
        "monto_esperado_centavos": monto, "moneda": moneda, "referencia": referencia,
        "firma_integridad": firma, "expira_en": expira_en, "creado_por": idtrabajador,
    })
    proveedor = proveedor_para(canal)
    if proveedor is not None:
        # Construir el checkout/QR es local (sin red): se puede hacer dentro de la transacción.
        inicio = proveedor.iniciar(referencia=referencia, monto_centavos=monto, moneda=moneda,
                                   expira_en=expira_en, firma=firma, cliente=cliente)
        CRUDpago.actualizar(db, idpago, {
            "checkout_url": inicio.checkout_url,
            "qr_payload": inicio.qr_payload,
            "qr_png_base64": generar_qr_png_base64(inicio.qr_payload),
        })
    registrar_auditoria(db, "pago", idpago, "CREAR", idtrabajador,
                        {"idventa": venta["idventa"], "metodo": metodo, "canal": canal,
                         "monto_centavos": monto, "referencia": referencia})
    return idpago


def publico(pago: dict[str, Any] | None) -> dict[str, Any] | None:
    """Vista del pago para respuestas: sin la imagen del QR ni la firma."""
    if pago is None:
        return None
    datos = {k: v for k, v in pago.items() if k not in ("qr_png_base64", "firma_integridad", "qr_payload")}
    datos["monto"] = desde_centavos(pago["monto_esperado_centavos"])
    datos["sospechoso"] = bool(pago.get("sospechoso"))
    for campo in ("monto_recibido_centavos", "cambio_centavos", "comprobante_monto_centavos"):
        if pago.get(campo) is not None:
            datos[campo.replace("_centavos", "")] = desde_centavos(pago[campo])
    return datos


# ------------------------------------------------------- aprobación / rechazo
def _bloquear(db: Session, idventa: int, idpago: int) -> tuple[dict[str, Any], dict[str, Any]]:
    venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
    pago = CRUDpago.buscar_por_id(db, idpago, bloquear=True)
    if not venta or not pago or pago["idventa"] != venta["idventa"]:
        raise NoEncontradoError("El pago no existe.")
    return venta, pago


def _rechazar(db: Session, venta: dict[str, Any], pago: dict[str, Any], *, motivo: str, origen: str,
              sospechoso: bool, idtrabajador: int | None, ip: str | None = None,
              monto_recibido: int | None = None, verificacion: firma_pago.Verificacion | None = None,
              detalle: dict[str, Any] | None = None) -> dict[str, Any]:
    CRUDpago.actualizar(db, pago["idpago"], {
        "estado": "RECHAZADO", "motivo_rechazo": motivo[:255], "sospechoso": int(sospechoso),
        "verificado_por": idtrabajador, "verificado_en": ahora_utc(),
    })
    CRUDpago.registrar_intento(
        db, idpago=pago["idpago"], origen=origen, resultado="RECHAZADO", sospechoso=sospechoso,
        monto_recibido_centavos=monto_recibido, moneda=pago["moneda"],
        firma_valida=verificacion.firma_valida if verificacion else None,
        monto_valido=verificacion.monto_valido if verificacion else None,
        detalle={"motivo": motivo, **(detalle or {})}, idtrabajador=idtrabajador, ip=ip,
    )
    CRUDventa.registrar_historial(db, venta["idventa"], venta["estado"], venta["estado"],
                                  f"Pago {pago['referencia']} rechazado: {motivo}"[:255], idtrabajador)
    registrar_auditoria(db, "pago", pago["idpago"], "RECHAZAR", idtrabajador,
                        {"motivo": motivo, "sospechoso": sospechoso, "origen": origen})
    if sospechoso:
        logger.warning("Pago %s rechazado por verificación (%s).", pago["referencia"], origen)
    return {"aprobado": False, "motivo": motivo, "sospechoso": sospechoso, "idpago": pago["idpago"],
            "idventa": venta["idventa"]}


def _aprobar(db: Session, venta: dict[str, Any], pago: dict[str, Any], *, origen: str,
             monto_recibido_centavos: int, moneda: str | None, referencia: str | None,
             cambios: dict[str, Any], idtrabajador: int | None, ip: str | None = None,
             detalle: dict[str, Any] | None = None) -> dict[str, Any]:
    if pago["estado"] != "PENDIENTE":
        raise ConflictoError(f"El pago está {pago['estado']}; no se puede aprobar.", codigo="PAGO_NO_PENDIENTE")
    if venta["estado"] != "PENDIENTE_PAGO":
        raise ConflictoError(f"La venta está {venta['estado']}.", codigo="VENTA_NO_PENDIENTE")

    verificacion = firma_pago.verificar_confirmacion(
        pago, monto_recibido_centavos=monto_recibido_centavos, moneda=moneda, referencia=referencia
    )
    if not verificacion.ok:
        return _rechazar(db, venta, pago, motivo=verificacion.motivo() or "Verificación fallida.",
                         origen=origen, sospechoso=True, idtrabajador=idtrabajador, ip=ip,
                         monto_recibido=monto_recibido_centavos, verificacion=verificacion, detalle=detalle)

    CRUDpago.actualizar(db, pago["idpago"], {
        **cambios, "estado": "APROBADO", "verificado_por": idtrabajador, "verificado_en": ahora_utc(),
    })
    for linea in CRUDventa.detalles(db, venta["idventa"]):
        if not CRUDproducto.confirmar_reserva(db, linea["idproducto"], linea["cantidad"]):
            raise RuntimeError(f"Reserva inconsistente del producto {linea['idproducto']}.")
    CRUDventa.cambiar_estado(db, venta["idventa"], venta["estado"], "PAGADA",
                             f"Pago {pago['referencia']} aprobado ({origen}).", idtrabajador)
    CRUDpago.registrar_intento(
        db, idpago=pago["idpago"], origen=origen, resultado="APROBADO",
        monto_recibido_centavos=monto_recibido_centavos, moneda=moneda or pago["moneda"],
        firma_valida=True, monto_valido=True, detalle=detalle, idtrabajador=idtrabajador, ip=ip,
    )
    registrar_auditoria(db, "pago", pago["idpago"], "APROBAR", idtrabajador, {"origen": origen, **cambios})
    return {"aprobado": True, "idpago": pago["idpago"], "idventa": venta["idventa"]}


def _pago_pendiente(db: Session, idventa: int, canales: set[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
    if not venta:
        raise NoEncontradoError("La venta no existe.")
    pago = CRUDpago.pago_vigente_de_venta(db, idventa, bloquear=True)
    if not pago or pago["estado"] != "PENDIENTE":
        raise ConflictoError("La venta no tiene un pago pendiente.", codigo="SIN_PAGO_PENDIENTE")
    if pago["canal"] not in canales:
        raise ConflictoError(
            f"El pago de esta venta es por {pago['canal']}. Regenera el pago para cambiar de método.",
            codigo="CANAL_INCORRECTO",
        )
    return venta, pago


# ---------------------------------------------------------------------- efectivo
def registrar_efectivo(db: Session, usuario: Usuario, idventa: int, monto_recibido: Any) -> dict[str, Any]:
    with db.begin():
        venta, pago = _pago_pendiente(db, idventa, {"EFECTIVO"})
        caja = CRUDcaja.caja_abierta(db, usuario.idtrabajador, bloquear=True)
        if not caja:
            raise ConflictoError("Abre tu caja antes de registrar pagos en efectivo.", codigo="CAJA_CERRADA")
        recibido = a_centavos(monto_recibido)
        esperado = int(pago["monto_esperado_centavos"])
        if recibido < esperado:
            CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="EFECTIVO",
                                       resultado="MONTO_INSUFICIENTE", monto_recibido_centavos=recibido,
                                       moneda=pago["moneda"], idtrabajador=usuario.idtrabajador)
            insuficiente = ValidacionError(
                "El monto recibido es menor que el total.", codigo="MONTO_INSUFICIENTE",
                detalles={"total": str(desde_centavos(esperado)), "recibido": str(desde_centavos(recibido))},
            )
        else:
            insuficiente = None
            resultado = _aprobar(
                db, venta, pago, origen="EFECTIVO", monto_recibido_centavos=esperado, moneda=pago["moneda"],
                referencia=pago["referencia"], idtrabajador=usuario.idtrabajador,
                cambios={"monto_recibido_centavos": recibido, "cambio_centavos": recibido - esperado,
                         "idcaja": caja["idcaja"]},
            )
    if insuficiente:
        raise insuficiente
    resultado["cambio"] = desde_centavos(recibido - esperado)
    return resultado


# ---------------------------------------------------------------------- datáfono
def registrar_datafono(db: Session, usuario: Usuario, idventa: int, datos: dict[str, Any]) -> dict[str, Any]:
    with db.begin():
        venta, pago = _pago_pendiente(db, idventa, {"DATAFONO"})
        if CRUDpago.existe_valor_unico(db, "recibo_numero", datos["recibo_numero"]):
            CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="DATAFONO", resultado="RECIBO_DUPLICADO",
                                       sospechoso=True, detalle={"recibo_numero": datos["recibo_numero"]},
                                       idtrabajador=usuario.idtrabajador)
            duplicado = True
        else:
            duplicado = False
            resultado = _aprobar(
                db, venta, pago, origen="DATAFONO", monto_recibido_centavos=a_centavos(datos["monto"]),
                moneda=pago["moneda"], referencia=pago["referencia"], idtrabajador=usuario.idtrabajador,
                cambios={"recibo_numero": datos["recibo_numero"], "codigo_autorizacion": datos["codigo_autorizacion"],
                         "tarjeta_ultimos4": datos["ultimos4"], "tarjeta_franquicia": datos["franquicia"],
                         "tarjeta_tipo": datos["tipo_tarjeta"]},
            )
    if duplicado:
        raise ConflictoError("Ese número de recibo ya fue registrado en otro pago.", codigo="RECIBO_DUPLICADO")
    return resultado


# ------------------------------------------------------ transferencia manual
_FIRMAS_IMAGEN = {b"\x89PNG\r\n\x1a\n": "png", b"\xff\xd8\xff": "jpg"}


def _guardar_imagen(idpago: int, imagen_base64: str) -> str:
    try:
        contenido = base64.b64decode(imagen_base64.split(",")[-1], validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValidacionError("imagen_base64 no es base64 válido.") from error
    if len(contenido) > settings.COMPROBANTE_MAX_BYTES:
        raise ValidacionError("La imagen del comprobante supera el tamaño permitido.")
    extension = next((ext for firma, ext in _FIRMAS_IMAGEN.items() if contenido.startswith(firma)), None)
    if not extension:
        raise ValidacionError("La imagen del comprobante debe ser PNG o JPEG.")
    carpeta = Path(settings.STORAGE_DIR) / "comprobantes"
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / f"{idpago}_{uuid.uuid4().hex}.{extension}"
    ruta.write_bytes(contenido)
    return str(ruta)


def registrar_comprobante(db: Session, idventa: int | None, datos: dict[str, Any], *,
                          usuario: Usuario | None, referencia: str | None = None,
                          firma: str | None = None, ip: str | None = None) -> dict[str, Any]:
    """Registra el comprobante de una transferencia manual (queda pendiente de verificación).

    Lo puede subir un trabajador (autenticado) o el cliente con la referencia y la firma del QR.
    """
    idtrabajador = usuario.idtrabajador if usuario else None
    error: Exception | None = None
    with db.begin():
        if idventa is None:
            pago_ref = CRUDpago.buscar_por_referencia(db, referencia or "")
            if not pago_ref or not firma or not hmac.compare_digest(firma, pago_ref["firma_integridad"]):
                CRUDpago.registrar_intento(db, idpago=pago_ref["idpago"] if pago_ref else None,
                                           origen="COMPROBANTE_PUBLICO", resultado="FIRMA_INVALIDA",
                                           sospechoso=True, firma_valida=False, ip=ip,
                                           detalle={"referencia": referencia})
                error = NoAutenticadoError("Referencia o firma inválidas.", codigo="FIRMA_INVALIDA")
            else:
                idventa = pago_ref["idventa"]
        if error is None:
            venta, pago = _pago_pendiente(db, idventa, {"BREB_MANUAL"})
            ahora = ahora_utc()
            fecha = a_utc(datos["fecha_hora"])
            if pago["comprobante_registrado_en"]:
                error = ConflictoError("Este pago ya tiene un comprobante registrado.", codigo="COMPROBANTE_EXISTENTE")
            elif CRUDpago.existe_valor_unico(db, "comprobante_numero", datos["numero_comprobante"]):
                CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="COMPROBANTE",
                                           resultado="COMPROBANTE_DUPLICADO", sospechoso=True, ip=ip,
                                           idtrabajador=idtrabajador,
                                           detalle={"numero_comprobante": datos["numero_comprobante"]})
                error = ConflictoError("Ese número de comprobante ya fue usado en otro pago.",
                                       codigo="COMPROBANTE_DUPLICADO")
            elif fecha < pago["creado_en"] - timedelta(minutes=5) or fecha > ahora + timedelta(minutes=5):
                error = ValidacionError("La fecha del comprobante es anterior a la venta o está en el futuro.")
            elif a_centavos(datos["monto"]) != int(pago["monto_esperado_centavos"]):
                resultado = _rechazar(
                    db, venta, pago, motivo="El monto del comprobante no coincide con el monto firmado.",
                    origen="COMPROBANTE", sospechoso=True, idtrabajador=idtrabajador, ip=ip,
                    monto_recibido=a_centavos(datos["monto"]),
                )
                return {**resultado, "estado": "RECHAZADO"}
            else:
                imagen = _guardar_imagen(pago["idpago"], datos["imagen_base64"]) if datos.get("imagen_base64") else None
                CRUDpago.actualizar(db, pago["idpago"], {
                    "comprobante_numero": datos["numero_comprobante"], "comprobante_banco": datos["banco_origen"],
                    "comprobante_fecha": fecha, "comprobante_monto_centavos": a_centavos(datos["monto"]),
                    "comprobante_imagen": imagen, "comprobante_registrado_en": ahora,
                })
                CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="COMPROBANTE",
                                           resultado="REGISTRADO", monto_recibido_centavos=a_centavos(datos["monto"]),
                                           moneda=pago["moneda"], idtrabajador=idtrabajador, ip=ip)
                registrar_auditoria(db, "pago", pago["idpago"], "COMPROBANTE", idtrabajador,
                                    {"numero": datos["numero_comprobante"], "banco": datos["banco_origen"]})
    if error:
        raise error
    return {"idpago": pago["idpago"], "idventa": idventa, "estado": "PENDIENTE_VERIFICACION"}


def verificar_comprobante(db: Session, usuario: Usuario, idpago: int, aprobar: bool,
                          monto_verificado: Any, motivo: str | None) -> dict[str, Any]:
    with db.begin():
        pago_sin_bloqueo = CRUDpago.buscar_por_id(db, idpago)
        if not pago_sin_bloqueo:
            raise NoEncontradoError("El pago no existe.")
        venta, pago = _bloquear(db, pago_sin_bloqueo["idventa"], idpago)
        if pago["canal"] != "BREB_MANUAL" or not pago["comprobante_registrado_en"]:
            raise ConflictoError("El pago no tiene un comprobante de transferencia por verificar.")
        if pago["estado"] != "PENDIENTE":
            raise ConflictoError(f"El pago ya está {pago['estado']}.", codigo="PAGO_NO_PENDIENTE")
        if not aprobar:
            return _rechazar(db, venta, pago, motivo=motivo or "Rechazado por verificación manual.",
                             origen="VERIFICACION_MANUAL", sospechoso=False, idtrabajador=usuario.idtrabajador)
        verificado = a_centavos(monto_verificado)
        if verificado != int(pago["comprobante_monto_centavos"]):
            return _rechazar(db, venta, pago, motivo="El monto verificado en el banco no coincide con el comprobante.",
                             origen="VERIFICACION_MANUAL", sospechoso=True, idtrabajador=usuario.idtrabajador,
                             monto_recibido=verificado)
        return _aprobar(db, venta, pago, origen="VERIFICACION_MANUAL", monto_recibido_centavos=verificado,
                        moneda=pago["moneda"], referencia=pago["referencia"], idtrabajador=usuario.idtrabajador,
                        cambios={})


def comprobantes_por_verificar(db: Session, page: int, page_size: int) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDpago.comprobantes_por_verificar(db, limite, offset)
    return respuesta_paginada([publico(i) for i in items], total, page, limite)


def intentos_sospechosos(db: Session, page: int, page_size: int) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDpago.intentos_sospechosos(db, limite, offset)
    return respuesta_paginada(items, total, page, limite)


# ----------------------------------------------------------------------- Wompi
_ESTADOS_RECHAZO_WOMPI = {"DECLINED", "ERROR", "VOIDED"}


def procesar_webhook_wompi(db: Session, proveedor: WompiProvider, evento: dict[str, Any],
                           checksum: str | None, ip: str | None) -> dict[str, Any]:
    """Webhook idempotente: firma del evento → consulta a la API → verificación propia."""
    if not proveedor.evento_valido(evento, checksum):
        with db.begin():
            CRUDpago.registrar_intento(db, idpago=None, origen="WEBHOOK_WOMPI", resultado="FIRMA_EVENTO_INVALIDA",
                                       sospechoso=True, firma_valida=False, ip=ip,
                                       detalle={"evento": evento.get("event")})
        raise NoAutenticadoError("Firma del evento inválida.", codigo="FIRMA_EVENTO_INVALIDA")

    transaccion = ((evento.get("data") or {}).get("transaction") or {})
    tx_id = str(transaccion.get("id") or "")
    referencia = str(transaccion.get("reference") or "")
    evento_hash = str((evento.get("signature") or {}).get("checksum") or checksum or "").lower()
    if evento.get("event") != "transaction.updated" or not tx_id or not referencia:
        return {"procesado": False, "motivo": "Evento ignorado."}

    # Nunca se confía solo en el evento: se consulta la transacción en Wompi.
    real = proveedor.consultar_transaccion(tx_id)

    with db.begin():
        if not CRUDpago.registrar_evento_webhook(db, "WOMPI", evento_hash, evento.get("event"), referencia,
                                                 tx_id, evento):
            return {"procesado": False, "duplicado": True}

        pago_ref = CRUDpago.buscar_por_referencia(db, referencia)
        if not pago_ref:
            CRUDpago.registrar_intento(db, idpago=None, origen="WEBHOOK_WOMPI", resultado="REFERENCIA_DESCONOCIDA",
                                       sospechoso=True, ip=ip, detalle={"referencia": referencia, "tx": tx_id})
            CRUDpago.resultado_evento_webhook(db, "WOMPI", evento_hash, "REFERENCIA_DESCONOCIDA")
            return {"procesado": False, "motivo": "Referencia desconocida."}

        venta, pago = _bloquear(db, pago_ref["idventa"], pago_ref["idpago"])
        estado_real = str(real.get("status") or "")
        detalle = {"tx": tx_id, "estado_evento": transaccion.get("status"), "estado_api": estado_real}
        coincide_api = (str(real.get("id")) == tx_id and str(real.get("reference")) == referencia)
        monto_evento = int(transaccion.get("amount_in_cents") or -1)
        monto_api = int(real.get("amount_in_cents") or -1)

        if pago["estado"] != "PENDIENTE":
            sospechoso = estado_real == "APPROVED" and pago["estado"] != "APROBADO"
            CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="WEBHOOK_WOMPI",
                                       resultado="PAGO_TARDIO" if sospechoso else "IGNORADO",
                                       sospechoso=sospechoso, ip=ip, detalle=detalle,
                                       monto_recibido_centavos=monto_api)
            resultado = {"procesado": False, "motivo": f"El pago ya estaba {pago['estado']}."}
        elif not coincide_api or monto_evento != monto_api:
            resultado = _rechazar(db, venta, pago, motivo="El evento no coincide con la transacción consultada en Wompi.",
                                  origen="WEBHOOK_WOMPI", sospechoso=True, idtrabajador=None, ip=ip,
                                  monto_recibido=monto_evento, detalle=detalle)
        elif estado_real == "APPROVED":
            metodo = real.get("payment_method") or {}
            extra = metodo.get("extra") or {}
            tipo_tarjeta = {"CREDIT": "CREDITO", "DEBIT": "DEBITO"}.get(str(extra.get("card_type", "")).upper())
            resultado = _aprobar(
                db, venta, pago, origen="WEBHOOK_WOMPI", monto_recibido_centavos=monto_api,
                moneda=real.get("currency"), referencia=real.get("reference"), idtrabajador=None, ip=ip,
                detalle=detalle,
                cambios={k: v for k, v in {
                    "proveedor_transaccion_id": tx_id, "proveedor_estado": estado_real,
                    "proveedor_metodo": real.get("payment_method_type"),
                    "tarjeta_franquicia": extra.get("brand"),
                    "tarjeta_ultimos4": str(extra["last_four"])[-4:] if extra.get("last_four") else None,
                    "tarjeta_tipo": tipo_tarjeta,
                }.items() if v is not None},
            )
        elif estado_real in _ESTADOS_RECHAZO_WOMPI:
            resultado = _rechazar(db, venta, pago, motivo=f"Wompi reportó la transacción como {estado_real}.",
                                  origen="WEBHOOK_WOMPI", sospechoso=False, idtrabajador=None, ip=ip,
                                  monto_recibido=monto_api, detalle=detalle)
        else:
            resultado = {"procesado": False, "motivo": f"Estado {estado_real} sin acción."}
        CRUDpago.resultado_evento_webhook(db, "WOMPI", evento_hash,
                                          "APROBADO" if resultado.get("aprobado") else
                                          ("RECHAZADO" if resultado.get("aprobado") is False else "SIN_ACCION"))
    return resultado


# ------------------------------------------------------------ expiración (job)
def _liberar_reservas(db: Session, idventa: int) -> None:
    for linea in CRUDventa.detalles(db, idventa):
        CRUDproducto.liberar_reserva(db, linea["idproducto"], linea["cantidad"])


def cerrar_venta_sin_pago(db: Session, venta: dict[str, Any], estado: str, motivo: str,
                          idtrabajador: int | None) -> None:
    """Expira o cancela una venta pendiente y libera su stock reservado (en la tx del llamador)."""
    _liberar_reservas(db, venta["idventa"])
    CRUDventa.cambiar_estado(db, venta["idventa"], venta["estado"], estado, motivo, idtrabajador)
    registrar_auditoria(db, "venta", venta["idventa"], estado, idtrabajador, {"motivo": motivo})


def expirar_pagos_vencidos(db: Session) -> dict[str, int]:
    """Expira pagos vencidos y las ventas que se quedan sin pago vigente."""
    pagos = ventas = 0
    with db.begin():
        candidatos = CRUDpago.pendientes_vencidos(db)
    for candidato in candidatos:
        with db.begin():
            venta = CRUDventa.buscar_por_id(db, candidato["idventa"], bloquear=True)
            pago = CRUDpago.buscar_por_id(db, candidato["idpago"], bloquear=True)
            if not venta or not pago or pago["estado"] != "PENDIENTE" or pago["expira_en"] >= ahora_utc():
                continue
            CRUDpago.actualizar(db, pago["idpago"], {"estado": "EXPIRADO"})
            CRUDpago.registrar_intento(db, idpago=pago["idpago"], origen="JOB", resultado="EXPIRADO")
            pagos += 1
    with db.begin():
        sin_pago = CRUDventa.pendientes_sin_pago_vigente(db, ahora_utc())
    for idventa in sin_pago:
        with db.begin():
            venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
            if not venta or venta["estado"] != "PENDIENTE_PAGO":
                continue
            if CRUDpago.pago_vigente_de_venta(db, idventa, bloquear=True):
                continue
            cerrar_venta_sin_pago(db, venta, "EXPIRADA", "Pago vencido; stock liberado.", None)
            ventas += 1
    return {"pagos_expirados": pagos, "ventas_expiradas": ventas}


def anular_pago_pendiente(db: Session, pago: dict[str, Any], motivo: str, idtrabajador: int) -> None:
    CRUDpago.actualizar(db, pago["idpago"], {"estado": "ANULADO", "motivo_rechazo": motivo[:255],
                                             "verificado_por": idtrabajador, "verificado_en": ahora_utc()})
    registrar_auditoria(db, "pago", pago["idpago"], "ANULAR", idtrabajador, {"motivo": motivo})


def requiere_secreto_configurado() -> None:
    if len(settings.PAYMENT_SIGNING_SECRET) < 32:
        raise ConfiguracionError("PAYMENT_SIGNING_SECRET debe tener al menos 32 caracteres.")
