import hashlib
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from backend.crudDataBase.CRUDcompra import (
    peticion_buscar_producto_para_compra,
    peticion_buscar_usuario_para_compra,
    peticion_crear_compra,
    peticion_crear_detalles_compra,
    peticion_crear_factura,
    peticion_descontar_stock,
)
from backend.crudDataBase.configDataBase.dataBase import SessionLocal
from backend.services.servicesFactus import (
    FactusIntegrationError,
    construir_payload_factus,
    crear_factura_factus,
)

logger = logging.getLogger(__name__)


class CompraNoEncontradaError(Exception):
    pass


class CompraConflictoError(Exception):
    pass


def _reference_code(idusuario: int, idempotency_key: str) -> str:
    # SUPUESTO: El cliente envía la misma Idempotency-Key al reintentar la misma compra.
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:32]
    return f"FAC-{idusuario}-{key_hash}"


def _response_value(data: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(data, dict):
        lowered = {str(key).lower(): value for key, value in data.items()}
        for key in keys:
            value = lowered.get(key.lower())
            if value is not None and not isinstance(value, (dict, list)):
                return str(value)
        for value in data.values():
            found = _response_value(value, keys)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _response_value(value, keys)
            if found:
                return found
    return None


def _invoice_number(invoice_data: dict[str, Any]) -> str | None:
    return _response_value(
        invoice_data, ("number", "bill_number", "invoice_number", "numero_factura")
    )


def _invoice_result(
    idcompra: int,
    idfactura: int,
    reference_code: str,
    invoice_data: dict[str, Any],
) -> dict[str, Any]:
    return {
        "message": "Compra registrada exitosamente.",
        "idcompra": idcompra,
        "idfactura": idfactura,
        "factus_reference_code": reference_code,
        "factus_number": _invoice_number(invoice_data),
        "factus_cufe": _response_value(invoice_data, ("cufe", "uuid")),
        "factus_url": _response_value(
            invoice_data, ("public_url", "pdf_url", "url_pdf", "url")
        ),
        "factus_qr": _response_value(
            invoice_data, ("qr", "qr_code", "qr_url", "qr_code_url")
        ),
    }


def servicio_crear_compra(
    datos_dict: dict[str, Any],
    idempotency_key: str,
) -> dict[str, Any]:
    idusuario = datos_dict.get("idusuario")
    items = datos_dict.get("items")
    if isinstance(idusuario, bool) or not isinstance(idusuario, int) or idusuario <= 0:
        raise ValueError("El campo 'idusuario' debe ser un entero positivo.")
    if not isinstance(items, list) or not items:
        raise ValueError("La compra debe contener al menos un producto.")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise ValueError("El encabezado Idempotency-Key es obligatorio.")

    cantidades_por_producto: dict[int, int] = {}
    items_validados: list[tuple[int, int]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"El ítem #{index} debe ser un objeto.")
        product_id = item.get("idproducto")
        quantity = item.get("cantidad")
        if (
            isinstance(product_id, bool)
            or not isinstance(product_id, int)
            or product_id <= 0
        ):
            raise ValueError(f"El ítem #{index} tiene un idproducto inválido.")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError(f"El ítem #{index} tiene una cantidad inválida.")
        items_validados.append((product_id, quantity))
        cantidades_por_producto[product_id] = (
            cantidades_por_producto.get(product_id, 0) + quantity
        )

    reference_code = _reference_code(idusuario, idempotency_key.strip())
    db: Session = SessionLocal()

    try:
        with db.begin():
            usuario = peticion_buscar_usuario_para_compra(db, idusuario)
            if not usuario:
                raise CompraNoEncontradaError(
                    "No existe un usuario cliente con el idusuario indicado."
                )

            productos: dict[int, dict[str, Any]] = {}
            for product_id in sorted(cantidades_por_producto):
                producto = peticion_buscar_producto_para_compra(db, product_id)
                if not producto:
                    raise CompraNoEncontradaError(
                        f"El producto con id {product_id} no existe."
                    )
                productos[product_id] = producto

                stock = int(producto["cantidad"])
                cantidad_solicitada = cantidades_por_producto[product_id]
                if stock < cantidad_solicitada:
                    raise CompraConflictoError(
                        f"Stock insuficiente para el producto con id {product_id}; "
                        f"disponible: {stock}, solicitado: {cantidad_solicitada}."
                    )

            productos_compra = [
                (productos[product_id], quantity)
                for product_id, quantity in items_validados
            ]

            payload, totales = construir_payload_factus(
                usuario, productos_compra, reference_code
            )
            try:
                respuesta_factus = crear_factura_factus(payload)
            except FactusIntegrationError as error:
                logger.warning(
                    "Factus rejected purchase request for user %s (HTTP %s).",
                    idusuario,
                    error.provider_status or error.http_status,
                )
                raise

            numero_factura = _invoice_number(respuesta_factus)
            cufe = _response_value(respuesta_factus, ("cufe", "uuid"))
            if not numero_factura or not cufe:
                raise RuntimeError(
                    "Factus no devolvió numero_factura y CUFE; no se puede guardar "
                    "la factura."
                )
            prefijo_match = re.match(r"([A-Za-z]+)", numero_factura)
            idcompra = peticion_crear_compra(db, idusuario)
            peticion_crear_detalles_compra(
                db,
                idcompra,
                totales["detalles"],
            )
            factura = {
                "idcompra": idcompra,
                "prefijo": prefijo_match.group(1) if prefijo_match else None,
                "numero_factura": numero_factura,
                "cufe": cufe,
                "total_bruto": totales["subtotal"],
                "total_descuentos": totales["descuento_total"],
                "total_iva": totales["iva"],
                "total_neto": totales["total"],
                "qr_dian": _response_value(
                    respuesta_factus, ("qr", "qr_code", "qr_url", "qr_code_url")
                ),
            }
            idfactura = peticion_crear_factura(db, factura)
            for product_id, quantity in sorted(cantidades_por_producto.items()):
                peticion_descontar_stock(db, product_id, quantity)

            return _invoice_result(
                idcompra, idfactura, reference_code, respuesta_factus
            )
    except (CompraNoEncontradaError, CompraConflictoError, ValueError):
        raise
    except FactusIntegrationError:
        raise
    except Exception:
        logger.exception("Purchase transaction failed for user %s.", idusuario)
        raise
    finally:
        db.close()
