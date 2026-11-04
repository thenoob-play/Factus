"""Ventas: cálculo exacto, snapshot de productos, reserva de stock y estados.

Estados: PENDIENTE_PAGO → PAGADA → FACTURADA, más EXPIRADA, CANCELADA y FACTURA_FALLIDA.
El trabajador siempre se toma del token; el cliente nunca envía precios.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import OrderedDict
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ConflictoError, NoEncontradoError, ValidacionError
from backend.core.seguridad import Usuario
from backend.core.utilidades import CIEN, ahora_utc, desde_centavos, dinero, paginar, respuesta_paginada
from backend.crudDataBase import CRUDcliente, CRUDfactura, CRUDpago, CRUDproducto, CRUDtrabajador, CRUDventa
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.crudDataBase.configDataBase.conf import settings
from backend.services import servicesPago

CERO = Decimal("0.00")


# --------------------------------------------------------------- cálculo puro
def agrupar_items(items: list[dict[str, Any]]) -> OrderedDict[int, int]:
    """Suma cantidades de ítems repetidos, conservando el orden de aparición."""
    agrupados: OrderedDict[int, int] = OrderedDict()
    for item in items:
        idproducto, cantidad = item["idproducto"], item["cantidad"]
        if isinstance(cantidad, bool) or not isinstance(cantidad, int) or cantidad <= 0:
            raise ValidacionError(f"La cantidad del producto {idproducto} debe ser un entero mayor que 0.")
        agrupados[idproducto] = agrupados.get(idproducto, 0) + cantidad
    return agrupados


def validar_disponibilidad(productos: dict[int, dict[str, Any] | None], cantidades: dict[int, int]) -> None:
    """Valida existencia, estado y stock disponible (stock - reservado) de cada producto."""
    faltantes = [pid for pid in cantidades if not productos.get(pid)]
    if faltantes:
        raise NoEncontradoError("Uno o más productos no existen.", detalles={"productos": faltantes})
    inactivos = [pid for pid in cantidades if productos[pid]["estado"] != "ACTIVO"]
    if inactivos:
        raise ConflictoError("Uno o más productos están inactivos.", codigo="PRODUCTO_INACTIVO",
                             detalles={"productos": inactivos})
    insuficientes = [
        {"idproducto": pid, "disponible": int(productos[pid]["stock_disponible"]), "solicitado": cantidad}
        for pid, cantidad in cantidades.items()
        if int(productos[pid]["stock_disponible"]) < cantidad
    ]
    if insuficientes:
        raise ConflictoError("Stock insuficiente.", codigo="STOCK_INSUFICIENTE", detalles=insuficientes)


def calcular_linea(producto: dict[str, Any], cantidad: int) -> dict[str, Any]:
    """Una línea de venta con redondeo a 2 decimales por paso (como lo calcula Factus)."""
    precio = dinero(producto["precio_unitario"])
    discount_rate = dinero(producto.get("discount_rate") or 0)
    excluido = bool(producto.get("is_excluded"))
    tax_rate = CERO if excluido else dinero(producto.get("tax_rate") or 0)
    bruto = dinero(precio * cantidad)
    descuento = dinero(bruto * discount_rate / CIEN)
    base = bruto - descuento
    iva = dinero(base * tax_rate / CIEN)
    standard = producto.get("standard_code") or "999"
    code_reference = producto["codigo_unspsc"] if standard == "001" and producto.get("codigo_unspsc") \
        else producto["code_reference"]
    return {
        "idproducto": int(producto["idproducto"]),
        "code_reference": code_reference,
        "nombre": producto["nombre"],
        "unit_measure_code": producto.get("unit_measure_code") or "94",
        "standard_code": standard,
        "cantidad": cantidad,
        "precio_unitario": precio,
        "discount_rate": discount_rate,
        "subtotal": bruto,
        "descuento": descuento,
        "base_gravable": base,
        "tax_code": producto.get("tax_code") or "01",
        "tax_rate": tax_rate,
        "is_excluded": excluido,
        "iva": iva,
        "total": base + iva,
    }


def calcular_totales(lineas: list[dict[str, Any]]) -> dict[str, Decimal]:
    subtotal = sum((linea["subtotal"] for linea in lineas), CERO)
    descuento = sum((linea["descuento"] for linea in lineas), CERO)
    base_gravable = sum((linea["base_gravable"] for linea in lineas
                         if not linea["is_excluded"] and linea["tax_rate"] > 0), CERO)
    iva = sum((linea["iva"] for linea in lineas), CERO)
    return {
        "subtotal": dinero(subtotal),
        "descuento_total": dinero(descuento),
        "base_gravable": dinero(base_gravable),
        "iva_total": dinero(iva),
        "total": dinero(subtotal - descuento + iva),
    }


def impuestos_por_tarifa(lineas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    resumen: dict[tuple[str, str, bool], dict[str, Any]] = {}
    for linea in lineas:
        excluido = bool(linea["is_excluded"])
        clave = (linea["tax_code"], format(dinero(linea["tax_rate"]), ".2f"), excluido)
        grupo = resumen.setdefault(clave, {"tax_code": clave[0], "tax_rate": clave[1], "is_excluded": excluido,
                                           "base": CERO, "impuesto": CERO})
        grupo["base"] += dinero(linea["base_gravable"])
        grupo["impuesto"] += dinero(linea["iva"])
    return list(resumen.values())


def _hash_peticion(datos: dict[str, Any]) -> str:
    texto = json.dumps(datos, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _nueva_referencia() -> str:
    return f"VTA-{ahora_utc():%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"


# -------------------------------------------------------------------- crear
def crear_venta(db: Session, usuario: Usuario, datos: dict[str, Any],
                idempotency_key: str | None = None) -> dict[str, Any]:
    metodo = getattr(datos["metodo_pago"], "value", datos["metodo_pago"])
    canal = getattr(datos.get("canal"), "value", datos.get("canal"))
    items = [{"idproducto": i["idproducto"], "cantidad": i["cantidad"]} for i in datos["items"]]
    cantidades = agrupar_items(items)
    servicesPago.resolver_canal(metodo, canal)  # falla rápido si el canal no aplica
    servicesPago.requiere_secreto_configurado()
    request_hash = _hash_peticion({"idcliente": datos["idcliente"], "metodo": metodo, "canal": canal,
                                   "items": items})

    with db.begin():
        if idempotency_key:
            existente = CRUDventa.buscar_por_idempotencia(db, usuario.idtrabajador, idempotency_key)
            if existente:
                if existente["request_hash"] != request_hash:
                    raise ConflictoError("La Idempotency-Key ya se usó con otro cuerpo.", codigo="IDEMPOTENCIA")
                idventa = existente["idventa"]
                nueva = False
            else:
                nueva = True
        else:
            nueva = True

        if nueva:
            cliente = CRUDcliente.buscar_por_id(db, datos["idcliente"])
            if not cliente:
                raise NoEncontradoError("El cliente no existe.")
            if cliente["estado"] != "ACTIVO":
                raise ConflictoError("El cliente está inactivo.", codigo="CLIENTE_INACTIVO")

            # Bloqueo en orden de id para evitar deadlocks entre ventas concurrentes.
            productos = {pid: CRUDproducto.buscar_por_id(db, pid, bloquear=True) for pid in sorted(cantidades)}
            validar_disponibilidad(productos, cantidades)

            lineas = [calcular_linea(productos[pid], cantidad) for pid, cantidad in cantidades.items()]
            totales = calcular_totales(lineas)
            referencia = _nueva_referencia()
            idventa = CRUDventa.crear(db, {
                "referencia": referencia, "idcliente": cliente["idcliente"], "idtrabajador": usuario.idtrabajador,
                "metodo_pago": metodo, "moneda": settings.PAYMENT_CURRENCY, **totales,
                "idempotency_key": idempotency_key, "request_hash": request_hash if idempotency_key else None,
            })
            CRUDventa.crear_detalles(db, idventa, lineas)
            for pid in sorted(cantidades):
                if not CRUDproducto.reservar(db, pid, cantidades[pid]):
                    raise ConflictoError("Stock insuficiente.", codigo="STOCK_INSUFICIENTE",
                                         detalles=[{"idproducto": pid}])
            CRUDventa.registrar_historial(db, idventa, None, "PENDIENTE_PAGO", "Venta creada.", usuario.idtrabajador)
            venta = CRUDventa.buscar_por_id(db, idventa)
            servicesPago.crear_pago(db, venta, cliente, metodo, canal, usuario.idtrabajador, referencia)
            registrar_auditoria(db, "venta", idventa, "CREAR", usuario.idtrabajador,
                                {"referencia": referencia, "total": str(totales["total"]), "metodo": metodo})
    return obtener_venta(db, idventa)


# ---------------------------------------------------------------- consultas
def obtener_venta(db: Session, idventa: int) -> dict[str, Any]:
    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa)
        if not venta:
            raise NoEncontradoError("La venta no existe.")
        venta["items"] = CRUDventa.detalles(db, idventa)
        venta["impuestos"] = impuestos_por_tarifa(venta["items"])
        venta["pago"] = servicesPago.publico(CRUDpago.pago_vigente_de_venta(db, idventa))
        venta["pagos"] = [servicesPago.publico(p) for p in CRUDpago.pagos_de_venta(db, idventa)]
        venta["historial"] = CRUDventa.historial(db, idventa)
        factura = CRUDfactura.buscar_por_venta(db, idventa)
        venta["factura"] = {k: factura[k] for k in ("idfactura", "estado", "numero", "cufe", "mensaje")} \
            if factura else None
    return venta


def listar_ventas(db: Session, filtros: dict[str, Any], page: int, page_size: int) -> dict[str, Any]:
    limite, offset = paginar(page, page_size)
    with db.begin():
        items, total = CRUDventa.listar(db, filtros, limite, offset)
    return respuesta_paginada(items, total, page, limite)


def obtener_qr(db: Session, idventa: int) -> dict[str, Any]:
    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa)
        if not venta:
            raise NoEncontradoError("La venta no existe.")
        pago = CRUDpago.pago_vigente_de_venta(db, idventa)
    if not pago or pago["estado"] != "PENDIENTE":
        raise ConflictoError("La venta no tiene un pago pendiente.", codigo="SIN_PAGO_PENDIENTE")
    if not pago.get("qr_png_base64"):
        raise ConflictoError(f"El canal {pago['canal']} no usa QR.", codigo="SIN_QR")
    return {
        "idventa": idventa,
        "referencia": pago["referencia"],
        "metodo": pago["metodo"],
        "canal": pago["canal"],
        "monto": desde_centavos(pago["monto_esperado_centavos"]),
        "moneda": pago["moneda"],
        "expira_en": pago["expira_en"],
        "checkout_url": pago.get("checkout_url"),
        "qr_payload": pago["qr_payload"],
        "qr_png_base64": pago["qr_png_base64"],
        "firma": pago["firma_integridad"],
    }


def comprobante(db: Session, idventa: int) -> dict[str, Any]:
    """Todo lo necesario para verificar el pago y facturar."""
    venta = obtener_venta(db, idventa)
    pago = next((p for p in venta["pagos"] if p["estado"] == "APROBADO"), None)
    if not pago:
        raise ConflictoError("La venta no tiene un pago aprobado.", codigo="SIN_PAGO_APROBADO")
    with db.begin():
        cliente = CRUDcliente.buscar_por_id(db, venta["idcliente"])
        trabajador = CRUDtrabajador.buscar_por_id(db, venta["idtrabajador"])
        verificador = CRUDtrabajador.buscar_por_id(db, pago["verificado_por"]) if pago.get("verificado_por") else None
    verificacion = {k: pago.get(k) for k in (
        "proveedor_transaccion_id", "proveedor_estado", "proveedor_metodo", "comprobante_numero",
        "comprobante_banco", "comprobante_fecha", "codigo_autorizacion", "recibo_numero",
        "tarjeta_franquicia", "tarjeta_ultimos4", "tarjeta_tipo", "monto_recibido", "cambio", "idcaja",
    ) if pago.get(k) is not None}
    return {
        "referencia": venta["referencia"],
        "estado_venta": venta["estado"],
        "metodo_pago": venta["metodo_pago"],
        "canal": pago["canal"],
        "referencia_pago": pago["referencia"],
        "monto": pago["monto"],
        "moneda": pago["moneda"],
        "aprobado_en": pago["verificado_en"],
        "verificado_por": verificador["nombre"] if verificador else "Proveedor de pagos",
        "verificacion": verificacion,
        "trabajador": {"idtrabajador": trabajador["idtrabajador"], "nombre": trabajador["nombre"]} if trabajador else None,
        "cliente": cliente,
        "items": venta["items"],
        "impuestos": venta["impuestos"],
        "totales": {k: venta[k] for k in ("subtotal", "descuento_total", "base_gravable", "iva_total", "total")},
        "factura": venta["factura"],
    }


# ----------------------------------------------------------- cambios de estado
def cancelar_venta(db: Session, usuario: Usuario, idventa: int, motivo: str) -> dict[str, Any]:
    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
        if not venta:
            raise NoEncontradoError("La venta no existe.")
        if venta["estado"] != "PENDIENTE_PAGO":
            raise ConflictoError(f"Solo se cancelan ventas pendientes de pago (está {venta['estado']}). "
                                 "Para una venta facturada usa una nota crédito.", codigo="VENTA_NO_CANCELABLE")
        pago = CRUDpago.pago_vigente_de_venta(db, idventa, bloquear=True)
        if pago and pago["estado"] == "PENDIENTE":
            servicesPago.anular_pago_pendiente(db, pago, f"Venta cancelada: {motivo}", usuario.idtrabajador)
        servicesPago.cerrar_venta_sin_pago(db, venta, "CANCELADA", motivo, usuario.idtrabajador)
    return obtener_venta(db, idventa)


def regenerar_pago(db: Session, usuario: Usuario, idventa: int, metodo: str | None, canal: str | None,
                   motivo: str) -> dict[str, Any]:
    """Anula el pago pendiente (o reemplaza uno rechazado) y crea otro con referencia y firma nuevas."""
    with db.begin():
        venta = CRUDventa.buscar_por_id(db, idventa, bloquear=True)
        if not venta:
            raise NoEncontradoError("La venta no existe.")
        if venta["estado"] != "PENDIENTE_PAGO":
            raise ConflictoError(f"La venta está {venta['estado']}.", codigo="VENTA_NO_PENDIENTE")
        pago = CRUDpago.pago_vigente_de_venta(db, idventa, bloquear=True)
        if pago and pago["estado"] == "APROBADO":
            raise ConflictoError("La venta ya tiene un pago aprobado.")
        if pago and pago["estado"] == "PENDIENTE":
            if pago["comprobante_registrado_en"]:
                raise ConflictoError("El pago tiene un comprobante por verificar; verifícalo o recházalo primero.")
            servicesPago.anular_pago_pendiente(db, pago, motivo, usuario.idtrabajador)
        metodo = metodo or venta["metodo_pago"]
        if metodo != venta["metodo_pago"]:
            CRUDventa.actualizar_metodo(db, idventa, metodo)
        cliente = CRUDcliente.buscar_por_id(db, venta["idcliente"])
        numero = CRUDventa.contar_pagos(db, idventa) + 1
        referencia = f"{venta['referencia']}-{numero}"
        servicesPago.crear_pago(db, {**venta, "metodo_pago": metodo}, cliente or {}, metodo, canal,
                                usuario.idtrabajador, referencia)
        CRUDventa.registrar_historial(db, idventa, venta["estado"], venta["estado"],
                                      f"Pago regenerado ({metodo}): {motivo}"[:255], usuario.idtrabajador)
    return obtener_venta(db, idventa)
