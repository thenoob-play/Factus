import hashlib
import json
import logging
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.crudDataBase.CRUDcompra import (
    peticion_actualizar_estado_factus,
    peticion_buscar_compra_idempotente,
    peticion_buscar_compra_por_id,
    peticion_buscar_factura_por_compra,
    peticion_buscar_producto_para_compra,
    peticion_buscar_usuario_para_compra,
    peticion_crear_compra,
    peticion_crear_detalles_compra,
    peticion_crear_factura,
    peticion_descontar_stock,
    peticion_guardar_payload_factus,
    peticion_guardar_respuesta_factus,
)
from backend.crudDataBase.configDataBase.conf import settings
from backend.crudDataBase.configDataBase.dataBase import SessionLocal
from backend.services.servicesFactus import (
    FactusConfigurationError,
    FactusIntegrationError,
    construir_payload_factus,
    crear_factura_factus,
    validar_rango_numeracion_factus,
)

logger = logging.getLogger(__name__)
_CENT = Decimal("0.01")


class CompraNoEncontradaError(Exception):
    pass


class CompraConflictoError(Exception):
    pass


def _reference_code(idusuario: int) -> str:
    return f"FAC-{idusuario}-{uuid4().hex}"


def _request_hash(datos_dict: dict[str, Any]) -> str:
    request_json = json.dumps(
        datos_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(request_json.encode("utf-8")).hexdigest()


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
        "message": "Compra registrada y factura emitida exitosamente.",
        "idcompra": idcompra,
        "idfactura": idfactura,
        "factus_estado": "emitida",
        "factus_reference_code": reference_code,
        "factus_number": _invoice_number(invoice_data),
        "factus_cufe": _response_value(invoice_data, ("cufe", "uuid")),
        "factus_url": _response_value(
            invoice_data, ("public_url", "pdf_url", "url_pdf", "url")
        ),
        "factus_qr": _response_value(
            invoice_data, ("qr", "qr_code", "qr_url", "qr_code_url")
        ),
        "factus_response": invoice_data,
    }


def _json_object(value: Any, field: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise RuntimeError(f"El campo persistido '{field}' no contiene JSON válido.") from error
        if isinstance(decoded, dict):
            return decoded
    raise RuntimeError(f"El campo persistido '{field}' no contiene un objeto JSON.")


def _money(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"El valor '{field}' no es un número decimal válido.") from error
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"El valor '{field}' debe ser un número no negativo y finito.")
    return amount.quantize(_CENT, rounding=ROUND_HALF_UP)


def _factus_source(
    usuario: dict[str, Any],
    productos: list[tuple[dict[str, Any], int]],
) -> dict[str, Any]:
    customer_fields = (
        "tipo_persona",
        "tipo_documento",
        "numero_documeto_nit",
        "nombre",
        "correo",
        "direccion",
        "municipio_departamento",
        "telefono_celular",
    )
    return {
        "usuario": {field: usuario.get(field) for field in customer_fields},
        "productos": [
            {"producto": producto, "cantidad": cantidad}
            for producto, cantidad in productos
        ],
    }


def _invoice_totals(
    db: Session,
    compra: dict[str, Any],
) -> dict[str, Decimal]:
    payload_value = compra.get("factus_payload")
    totals_value = compra.get("factus_totales")
    if payload_value is None or totals_value is None:
        source = _json_object(compra.get("factus_source"), "factus_source")
        product_entries = source.get("productos")
        if not isinstance(product_entries, list) or not product_entries:
            raise RuntimeError("La compra no tiene productos guardados para facturar.")
        products: list[tuple[dict[str, Any], int]] = []
        for entry in product_entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("producto"), dict):
                raise RuntimeError("Los productos guardados para facturar no son válidos.")
            products.append((entry["producto"], int(entry["cantidad"])))

        payload, totals = construir_payload_factus(
            source["usuario"],
            products,
            str(compra["factus_reference_code"]),
        )
        totals_for_storage = {
            key: str(totals[key])
            for key in ("subtotal", "descuento_total", "iva", "total")
        }
        peticion_guardar_payload_factus(
            db,
            int(compra["idcompra"]),
            json.dumps(payload, ensure_ascii=False),
            json.dumps(totals_for_storage),
        )
        totals_value = totals_for_storage
    else:
        payload = _json_object(payload_value, "factus_payload")

    totals_data = _json_object(totals_value, "factus_totales")
    return {
        "subtotal": Decimal(str(totals_data["subtotal"])),
        "descuento_total": Decimal(str(totals_data["descuento_total"])),
        "iva": Decimal(str(totals_data["iva"])),
        "total": Decimal(str(totals_data["total"])),
    }


def _emitir_factura(
    db: Session,
    idcompra: int,
    reference_code: str,
) -> dict[str, Any]:
    result: dict[str, Any] | None = None
    integration_error: Exception | None = None

    with db.begin():
        compra = peticion_buscar_compra_por_id(db, idcompra)
        if not compra:
            raise RuntimeError(f"No existe la compra local con id {idcompra}.")

        if compra["factus_estado"] == "emitida":
            idfactura = peticion_buscar_factura_por_compra(db, idcompra)
            if idfactura is None:
                raise RuntimeError("La compra figura emitida, pero no tiene factura local.")
            response_data = _json_object(
                compra.get("factus_response"), "factus_response"
            )
            result = _invoice_result(
                idcompra, idfactura, reference_code, response_data
            )
        else:
            try:
                totals = _invoice_totals(db, compra)
                payload_value = compra.get("factus_payload")
                if payload_value is None:
                    refreshed = peticion_buscar_compra_por_id(db, idcompra)
                    if not refreshed:
                        raise RuntimeError("No se pudo volver a leer la compra.")
                    payload_value = refreshed.get("factus_payload")
                payload = _json_object(payload_value, "factus_payload")
                valid_range_id = validar_rango_numeracion_factus()
                expected_document = f"{settings.FACTUS_DOCUMENT_TYPE_ID:02d}"
                payload_changed = False
                if payload.get("numbering_range_id") != valid_range_id:
                    payload["numbering_range_id"] = valid_range_id
                    payload_changed = True
                if payload.get("document") != expected_document:
                    payload["document"] = expected_document
                    payload_changed = True
                if payload_changed:
                    peticion_guardar_payload_factus(
                        db,
                        idcompra,
                        json.dumps(payload, ensure_ascii=False),
                        json.dumps(
                            {
                                key: str(totals[key])
                                for key in ("subtotal", "descuento_total", "iva", "total")
                            }
                        ),
                    )

                response_data = crear_factura_factus(payload)
                numero_factura = _invoice_number(response_data)
                cufe = _response_value(response_data, ("cufe", "uuid"))
                if not numero_factura or not cufe:
                    raise FactusIntegrationError(
                        502,
                        {
                            "message": (
                                "Factus respondió sin número de factura o CUFE; "
                                "la respuesta no se puede registrar como emitida."
                            )
                        },
                    )

                prefijo_match = re.match(r"([A-Za-z]+)", numero_factura)
                idfactura = peticion_crear_factura(
                    db,
                    {
                        "idcompra": idcompra,
                        "prefijo": prefijo_match.group(1) if prefijo_match else None,
                        "numero_factura": numero_factura,
                        "cufe": cufe,
                        "total_bruto": totals["subtotal"],
                        "total_descuentos": totals["descuento_total"],
                        "total_iva": totals["iva"],
                        "total_neto": totals["total"],
                        "qr_dian": _response_value(
                            response_data,
                            ("qr", "qr_code", "qr_url", "qr_code_url"),
                        ),
                    },
                )
                peticion_guardar_respuesta_factus(
                    db,
                    idcompra,
                    json.dumps(response_data, ensure_ascii=False),
                )
                result = _invoice_result(
                    idcompra, idfactura, reference_code, response_data
                )
            except (
                FactusConfigurationError,
                FactusIntegrationError,
                ValueError,
            ) as error:
                peticion_actualizar_estado_factus(db, idcompra, "error")
                integration_error = error

    if integration_error is not None:
        raise integration_error
    if result is None:
        raise RuntimeError("La emisión de la factura terminó sin resultado.")
    return result


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

    key = idempotency_key.strip()
    request_hash = _request_hash(datos_dict)
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

    reference_code = _reference_code(idusuario)
    db: Session = SessionLocal()

    try:
        with db.begin():
            usuario = peticion_buscar_usuario_para_compra(db, idusuario)
            if not usuario:
                raise CompraNoEncontradaError(
                    "No existe un usuario cliente con el idusuario indicado."
                )

            compra_existente = peticion_buscar_compra_idempotente(
                db, idusuario, key
            )
            if compra_existente:
                if compra_existente["request_hash"] != request_hash:
                    raise CompraConflictoError(
                        "La Idempotency-Key ya fue utilizada con un cuerpo diferente."
                    )
                idcompra = int(compra_existente["idcompra"])
                reference_code = str(compra_existente["factus_reference_code"])
            else:
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
                source = _factus_source(usuario, productos_compra)
                source_json = json.dumps(
                    source,
                    ensure_ascii=False,
                    default=str,
                )
                idcompra = peticion_crear_compra(
                    db,
                    idusuario,
                    key,
                    request_hash,
                    reference_code,
                    source_json,
                )

                detalles: list[dict[str, Any]] = []
                for product_id, quantity in items_validados:
                    unit_price = _money(
                        productos[product_id].get("precio_unitario"),
                        "precio_unitario",
                    )
                    detalles.append(
                        {
                            "idproducto": product_id,
                            "cantidad": quantity,
                            "precio_unitario": unit_price,
                            "subtotal": (unit_price * quantity).quantize(
                                _CENT, rounding=ROUND_HALF_UP
                            ),
                        }
                    )
                peticion_crear_detalles_compra(db, idcompra, detalles)
                for product_id, quantity in sorted(cantidades_por_producto.items()):
                    peticion_descontar_stock(db, product_id, quantity)

        return _emitir_factura(db, idcompra, reference_code)
    except (CompraNoEncontradaError, CompraConflictoError, ValueError):
        raise
    except (FactusConfigurationError, FactusIntegrationError):
        raise
    except Exception:
        logger.exception("Purchase transaction failed for user %s.", idusuario)
        raise
    finally:
        db.close()
