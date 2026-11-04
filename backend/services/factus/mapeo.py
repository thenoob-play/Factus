"""Mapeo venta → payload de Factus v2 y validación local antes de enviar.

Los ítems salen del snapshot guardado en `venta_detalle`, nunca del catálogo actual.
En v2 `price` es el precio unitario neto (sin impuestos ni descuentos) y los impuestos
van en `taxes[] = {code, rate, is_excluded}`.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from backend.core.utilidades import decimal, dinero, dinero_texto
from backend.crudDataBase.configDataBase.conf import settings

_PESOS_DV = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)


def calcular_dv_nit(nit: str) -> str:
    """Dígito de verificación del NIT colombiano (algoritmo DIAN, módulo 11)."""
    nit = nit.strip()
    if not nit.isdigit() or not 1 <= len(nit) <= len(_PESOS_DV):
        raise ValueError("El NIT debe contener entre 1 y 15 dígitos, sin DV ni guion.")
    suma = sum(int(d) * p for d, p in zip(reversed(nit), _PESOS_DV))
    residuo = suma % 11
    return str(residuo if residuo in (0, 1) else 11 - residuo)


def codigo_metodo_pago(metodo: str, tarjeta_tipo: str | None = None) -> str:
    codigos = settings.factus_payment_method_codes
    if metodo == "TARJETA":
        clave = "TARJETA_DEBITO" if tarjeta_tipo == "DEBITO" else "TARJETA_CREDITO"
    else:
        clave = metodo
    if clave not in codigos:
        raise ValueError(f"No hay payment_method_code configurado para {clave}.")
    return codigos[clave]


def construir_customer(cliente: dict[str, Any]) -> dict[str, Any]:
    customer: dict[str, Any] = {
        "identification_document_code": cliente["identification_document_code"],
        "identification": cliente["identification"],
        "legal_organization_code": cliente["legal_organization_code"],
        "tribute_code": cliente.get("tribute_code") or settings.FACTUS_TRIBUTE_CODE,
    }
    if cliente["identification_document_code"] == "31":
        customer["dv"] = cliente.get("dv") or calcular_dv_nit(cliente["identification"])
    if cliente["legal_organization_code"] == "1":
        customer["company"] = cliente.get("company")
    else:
        customer["names"] = cliente.get("names")
    for campo in ("trade_name", "address", "email", "phone", "municipality_code"):
        valor = cliente.get(campo)
        if valor:
            customer[campo] = str(valor)
    return customer


def construir_items(detalles: list[dict[str, Any]], cantidades: dict[int, int] | None = None) -> list[dict[str, Any]]:
    """Ítems Factus desde el snapshot. ``cantidades`` permite notas crédito parciales."""
    items = []
    for d in detalles:
        cantidad = d["cantidad"] if cantidades is None else cantidades.get(int(d["idproducto"]), 0)
        if cantidad <= 0:
            continue
        excluido = bool(d["is_excluded"])
        items.append({
            "code_reference": d["code_reference"],
            "name": d["nombre"],
            "quantity": dinero_texto(cantidad),
            "discount_rate": dinero_texto(d["discount_rate"]),
            "price": dinero_texto(d["precio_unitario"]),
            "unit_measure_code": d["unit_measure_code"],
            "standard_code": d["standard_code"],
            "taxes": [{
                "code": d["tax_code"],
                "rate": "0.00" if excluido else dinero_texto(d["tax_rate"]),
                "is_excluded": excluido,
            }],
        })
    return items


def total_items(items: list[dict[str, Any]]) -> Decimal:
    """Total que calculará Factus para estos ítems (mismo redondeo por línea que la venta)."""
    total = Decimal("0")
    for item in items:
        bruto = dinero(decimal(item["price"]) * decimal(item["quantity"]))
        descuento = dinero(bruto * decimal(item["discount_rate"]) / 100)
        base = bruto - descuento
        iva = sum((dinero(base * decimal(t["rate"]) / 100) for t in item["taxes"] if not t.get("is_excluded")),
                  Decimal("0"))
        total += base + iva
    return dinero(total)


def construir_payload_factura(
    venta: dict[str, Any], detalles: list[dict[str, Any]], cliente: dict[str, Any],
    pago: dict[str, Any],
) -> dict[str, Any]:
    items = construir_items(detalles)
    payload: dict[str, Any] = {
        "document": f"{settings.FACTUS_DOCUMENT_TYPE_ID:02d}",
        "reference_code": venta["referencia"],
        "send_email": settings.FACTUS_SEND_EMAIL,
        "payment_details": [{
            "payment_form": str(settings.FACTUS_PAYMENT_FORM),
            "payment_method_code": codigo_metodo_pago(venta["metodo_pago"], pago.get("tarjeta_tipo")),
            "reference_code": pago["referencia"],
            "amount": dinero_texto(venta["total"]),
        }],
        "customer": construir_customer(cliente),
        "items": items,
    }
    if settings.FACTUS_NUMBERING_RANGE_ID:
        payload["numbering_range_id"] = settings.FACTUS_NUMBERING_RANGE_ID
    validar_payload_factura(payload)
    return payload


def construir_payload_nota_credito(
    factura: dict[str, Any], detalles: list[dict[str, Any]], cliente: dict[str, Any],
    cantidades: dict[int, int], concepto: str, motivo: str, reference_code: str,
    metodo_pago: str, tarjeta_tipo: str | None,
) -> dict[str, Any]:
    items = construir_items(detalles, cantidades)
    for item in items:
        item["note"] = motivo[:250]
    payload: dict[str, Any] = {
        "reference_code": reference_code,
        "correction_concept_code": concepto,
        "customization_id": "20",
        "bill_number": factura["numero"],
        "observation": motivo[:500],
        "payment_details": [{
            "payment_form": str(settings.FACTUS_PAYMENT_FORM),
            "payment_method_code": codigo_metodo_pago(metodo_pago, tarjeta_tipo),
            "amount": dinero_texto(total_items(items)),
        }],
        "customer": construir_customer(cliente),
        "items": items,
    }
    if settings.FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID:
        payload["numbering_range_id"] = settings.FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID
    validar_payload_factura(payload, nota_credito=True)
    return payload


_DOS_DECIMALES = re.compile(r"^\d+(\.\d{1,2})?$")


def validar_payload_factura(datos: dict[str, Any], *, nota_credito: bool = False) -> None:
    """Valida localmente lo que Factus rechazaría, para no gastar intentos ni consecutivos."""
    errores: list[str] = []
    obligatorios = ["reference_code", "payment_details", "customer", "items"]
    if nota_credito:
        obligatorios += ["correction_concept_code", "bill_number"]
    for campo in obligatorios:
        if not datos.get(campo):
            errores.append(f"Falta el campo obligatorio '{campo}'.")

    customer = datos.get("customer") or {}
    for campo in ("identification_document_code", "identification", "legal_organization_code"):
        if not customer.get(campo):
            errores.append(f"Falta customer.{campo}.")
    organizacion = str(customer.get("legal_organization_code", ""))
    if organizacion == "1" and not customer.get("company"):
        errores.append("customer.company es obligatorio para persona jurídica.")
    if organizacion == "2" and not customer.get("names"):
        errores.append("customer.names es obligatorio para persona natural.")
    if organizacion not in {"1", "2"}:
        errores.append("customer.legal_organization_code debe ser '1' o '2'.")
    if customer.get("identification_document_code") == "31":
        try:
            if customer.get("dv") != calcular_dv_nit(str(customer.get("identification", ""))):
                errores.append("El dígito de verificación (dv) del NIT no es válido.")
        except ValueError as error:
            errores.append(str(error))

    items = datos.get("items") or []
    for i, item in enumerate(items, start=1):
        for campo in ("code_reference", "name", "quantity", "price", "unit_measure_code", "standard_code"):
            if item.get(campo) in (None, ""):
                errores.append(f"Ítem #{i}: falta '{campo}'.")
        for campo in ("quantity", "price", "discount_rate"):
            valor = item.get(campo)
            if valor not in (None, "") and not _DOS_DECIMALES.match(str(valor)):
                errores.append(f"Ítem #{i}: '{campo}' debe ser positivo y tener máximo 2 decimales.")
        if item.get("quantity") and decimal(item["quantity"]) <= 0:
            errores.append(f"Ítem #{i}: la cantidad debe ser mayor que 0.")
        if not item.get("taxes"):
            errores.append(f"Ítem #{i}: falta 'taxes'.")
        for t in item.get("taxes") or []:
            if not t.get("code") or not _DOS_DECIMALES.match(str(t.get("rate", ""))):
                errores.append(f"Ítem #{i}: impuesto inválido.")

    pagos = datos.get("payment_details") or []
    for i, pago in enumerate(pagos, start=1):
        for campo in ("payment_form", "payment_method_code", "amount"):
            if not pago.get(campo):
                errores.append(f"Pago #{i}: falta '{campo}'.")
    if items and pagos and not errores:
        suma = sum((decimal(p["amount"]) for p in pagos), Decimal("0"))
        if dinero(suma) != total_items(items):
            errores.append(
                f"La suma de payment_details ({dinero_texto(suma)}) no coincide con el total "
                f"de los ítems ({dinero_texto(total_items(items))})."
            )
    if errores:
        raise ValueError("; ".join(errores))
