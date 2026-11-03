from decimal import Decimal, InvalidOperation
from typing import Any

import requests


def validar_datos_factura(datos: dict[str, Any]) -> bool:
    """Valida localmente el contrato de factura usado por la integración Factus."""
    if not isinstance(datos, dict):
        raise ValueError("El parámetro 'datos' debe ser un diccionario.")

    campos_requeridos = (
        "document_type_id",
        "numbering_range_id",
        "reference_code",
        "payment_form",
        "payment_method_code",
        "customer",
        "items",
    )
    for campo in campos_requeridos:
        if datos.get(campo) is None or datos.get(campo) == "":
            raise ValueError(
                f"El campo obligatorio '{campo}' falta o está vacío en la factura."
            )

    customer = datos["customer"]
    if not isinstance(customer, dict):
        raise ValueError("El campo 'customer' debe ser un objeto.")
    for campo in (
        "identification",
        "names",
        "email",
        "identification_document_code",
        "municipality_id",
    ):
        if not customer.get(campo):
            raise ValueError(
                f"El campo del cliente '{campo}' es obligatorio y no puede estar vacío."
            )

    items = datos["items"]
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items:
        raise ValueError("La factura debe incluir al menos un ítem en 'items'.")

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError(f"El ítem #{index} no tiene un nombre válido.")
        try:
            quantity = Decimal(str(item.get("quantity")))
            price = Decimal(str(item.get("price")))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(
                f"El ítem #{index} tiene una cantidad o precio inválido."
            ) from error
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError(f"El ítem #{index} tiene una cantidad inválida.")
        if not price.is_finite() or price < 0:
            raise ValueError(f"El ítem #{index} tiene un precio inválido.")

    return True


def obtener_token() -> str:
    """Compatibilidad con el script anterior; usa las credenciales del entorno."""
    from backend.services.servicesFactus import obtener_token as obtener_token_factus

    return obtener_token_factus()


def crear_factura(access_token: str, datos: dict[str, Any]) -> requests.Response:
    """Compatibilidad con el script anterior, sin credenciales embebidas."""
    from backend.services.servicesFactus import _factus_base_url

    validar_datos_factura(datos)
    return requests.post(
        f"{_factus_base_url()}/v2/bills/validate",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=datos,
        timeout=30,
    )
