import html
import json
import logging
import re
import threading
import time
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html.parser import HTMLParser
from typing import Any

import requests

from backend.APIFactus.factusFacturacion.CrearFactura import validar_datos_factura
from backend.crudDataBase.configDataBase.conf import settings

logger = logging.getLogger(__name__)

_TOKEN_LOCK = threading.Lock()
_TOKEN: str | None = None
_TOKEN_EXPIRES_AT = 0.0
_MUNICIPALITIES_LOCK = threading.Lock()
_MUNICIPALITIES: list[dict[str, Any]] | None = None
_MUNICIPALITIES_EXPIRES_AT = 0.0
_UNIT_MEASURES_LOCK = threading.Lock()
_UNIT_MEASURES: list[dict[str, Any]] | None = None
_UNIT_MEASURES_EXPIRES_AT = 0.0
_CENT = Decimal("0.01")


class FactusIntegrationError(Exception):
    def __init__(self, http_status: int, detail: Any, provider_status: int | None = None):
        self.http_status = http_status
        self.detail = detail
        self.provider_status = provider_status
        super().__init__("La solicitud a Factus no pudo completarse.")


class FactusConfigurationError(RuntimeError):
    pass


class _PreformattedContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._inside_pre = False
        self._current_block: list[str] = []
        self.parts: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        super().handle_starttag(tag, attrs)
        if tag.lower() == "pre":
            self._inside_pre = True
            self._current_block = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "pre":
            self._inside_pre = False
            self.parts.append("".join(self._current_block))
            self._current_block = []

    def handle_data(self, data: str) -> None:
        if self._inside_pre:
            self._current_block.append(data)


def _require_factus_credentials() -> tuple[str, str, str, str, str]:
    values = (
        settings.FACTUS_BASE_URL,
        settings.FACTUS_CLIENT_ID,
        settings.FACTUS_CLIENT_SECRET,
        settings.FACTUS_USERNAME,
        settings.FACTUS_PASSWORD,
    )
    if any(not value or not value.strip() for value in values):
        raise FactusConfigurationError(
            "Configura FACTUS_BASE_URL, FACTUS_CLIENT_ID, FACTUS_CLIENT_SECRET, "
            "FACTUS_USERNAME y FACTUS_PASSWORD en el entorno."
        )
    return (
        str(values[0]),
        str(values[1]),
        str(values[2]),
        str(values[3]),
        str(values[4]),
    )


def _factus_base_url() -> str:
    if not settings.FACTUS_BASE_URL or not settings.FACTUS_BASE_URL.strip():
        raise FactusConfigurationError("Configura FACTUS_BASE_URL en el entorno.")
    return settings.FACTUS_BASE_URL.rstrip("/")


def obtener_token() -> str:
    """Obtiene y cachea el token hasta un margen anterior a su expiración."""
    global _TOKEN, _TOKEN_EXPIRES_AT

    with _TOKEN_LOCK:
        now = time.monotonic()
        if _TOKEN and now < _TOKEN_EXPIRES_AT:
            return _TOKEN

        base_url, client_id, client_secret, username, password = _require_factus_credentials()
        try:
            response = requests.post(
                f"{base_url.rstrip('/')}/oauth/token",
                data={
                    "grant_type": "password",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "username": username,
                    "password": password,
                },
                headers={"Accept": "application/json"},
                timeout=30,
            )
        except requests.Timeout as error:
            logger.warning("Factus OAuth request timed out.")
            raise FactusIntegrationError(
                502, {"message": "Tiempo de espera agotado al autenticar con Factus."}
            ) from error
        except requests.RequestException as error:
            logger.warning("Factus OAuth request failed: %s", type(error).__name__)
            raise FactusIntegrationError(
                502, {"message": "No fue posible conectarse con la autenticación de Factus."}
            ) from error

        if response.status_code != 200:
            detail = _response_detail(response)
            logger.warning("Factus OAuth returned HTTP %s.", response.status_code)
            if response.status_code == 401:
                detail = {"provider_status": 401, "factus": detail}
            raise FactusIntegrationError(502, detail, response.status_code)

        try:
            token_data = response.json()
            token = token_data["access_token"]
            expires_in = int(token_data.get("expires_in", 600))
        except (ValueError, KeyError, TypeError) as error:
            logger.warning("Factus OAuth returned an invalid token response.")
            raise FactusIntegrationError(
                502, {"message": "Factus devolvió una respuesta de autenticación inválida."}
            ) from error

        if not isinstance(token, str) or not token or expires_in <= 0:
            raise FactusIntegrationError(
                502, {"message": "Factus devolvió una respuesta de autenticación inválida."}
            )

        renewal_margin = min(60, max(5, expires_in // 10))
        _TOKEN = token
        _TOKEN_EXPIRES_AT = time.monotonic() + max(1, expires_in - renewal_margin)
        return token


def _response_detail(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"message": response.text[:4000] or "Respuesta vacía de Factus."}


def _download_reference_catalog(url: str, catalog_key: str) -> list[dict[str, Any]]:
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        try:
            catalog = response.json()
        except ValueError:
            parser = _PreformattedContentParser()
            parser.feed(response.text)
            catalog = None
            for part in parser.parts:
                try:
                    catalog = json.loads(html.unescape(part).strip())
                    break
                except json.JSONDecodeError:
                    continue
    except requests.Timeout as error:
        logger.warning("Factus %s catalog request timed out.", catalog_key)
        raise FactusIntegrationError(
            502, {"message": f"Tiempo de espera agotado al consultar {catalog_key} de Factus."}
        ) from error
    except requests.RequestException as error:
        logger.warning(
            "Factus %s catalog request failed: %s", catalog_key, type(error).__name__
        )
        raise FactusIntegrationError(
            502, {"message": f"No fue posible consultar {catalog_key} de Factus."}
        ) from error

    if isinstance(catalog, dict):
        catalog = catalog.get(catalog_key, catalog.get("data"))
        if isinstance(catalog, dict):
            catalog = catalog.get(catalog_key)
    if not isinstance(catalog, list):
        raise FactusIntegrationError(
            502, {"message": f"Factus devolvió un catálogo de {catalog_key} inválido."}
        )
    entries = [entry for entry in catalog if isinstance(entry, dict)]
    if not entries:
        raise FactusIntegrationError(
            502, {"message": f"El catálogo de {catalog_key} de Factus está vacío."}
        )
    return entries


def _municipalities_catalog() -> list[dict[str, Any]]:
    global _MUNICIPALITIES, _MUNICIPALITIES_EXPIRES_AT

    with _MUNICIPALITIES_LOCK:
        now = time.monotonic()
        if _MUNICIPALITIES is None or now >= _MUNICIPALITIES_EXPIRES_AT:
            _MUNICIPALITIES = _download_reference_catalog(
                settings.FACTUS_MUNICIPALITIES_URL, "municipalities"
            )
            _MUNICIPALITIES_EXPIRES_AT = now + max(
                60, settings.FACTUS_MUNICIPALITIES_CACHE_SECONDS
            )
        return _MUNICIPALITIES


def _unit_measures_catalog() -> list[dict[str, Any]]:
    global _UNIT_MEASURES, _UNIT_MEASURES_EXPIRES_AT

    with _UNIT_MEASURES_LOCK:
        now = time.monotonic()
        if _UNIT_MEASURES is None or now >= _UNIT_MEASURES_EXPIRES_AT:
            _UNIT_MEASURES = _download_reference_catalog(
                settings.FACTUS_UNIT_MEASURES_URL, "unitMeasures"
            )
            _UNIT_MEASURES_EXPIRES_AT = now + max(
                60, settings.FACTUS_MUNICIPALITIES_CACHE_SECONDS
            )
        return _UNIT_MEASURES


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    unaccented = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", unaccented.upper()).split())


def obtener_municipio_id(municipio_departamento: str) -> str:
    """Busca el municipio por nombre y usa el fallback configurado si no es unívoco."""
    # SUPUESTO: El texto puede incluir municipio y departamento, sin formato fijo.
    search_text = _normalize(municipio_departamento)
    matches: list[tuple[str, str]] = []

    for entry in _municipalities_catalog():
        name = entry.get("name")
        code = entry.get("code")
        department = entry.get("department") or {}
        department_name = department.get("name") if isinstance(department, dict) else ""
        if not name or not code:
            continue
        normalized_name = re.sub(r"\bD\s+C\b", "", _normalize(str(name))).strip()
        normalized_department = _normalize(str(department_name))
        if normalized_name in search_text:
            matches.append((str(code), normalized_department))

    if matches:
        department_matches = [
            code
            for code, department in matches
            if department and department in search_text
        ]
        if len(department_matches) == 1:
            return department_matches[0]
        unique_codes = {code for code, _ in matches}
        if len(unique_codes) == 1:
            return unique_codes.pop()

    if settings.FACTUS_DEFAULT_MUNICIPALITY_ID:
        return str(settings.FACTUS_DEFAULT_MUNICIPALITY_ID)
    raise FactusConfigurationError(
        "No se pudo identificar un municipio de Factus de forma única. "
        "Completa municipio_departamento o configura FACTUS_DEFAULT_MUNICIPALITY_ID."
    )


def _unit_code(unit: str) -> str:
    try:
        configured = json.loads(settings.FACTUS_UNIT_CODES_JSON)
    except json.JSONDecodeError as error:
        raise FactusConfigurationError("FACTUS_UNIT_CODES_JSON debe contener JSON válido.") from error
    if not isinstance(configured, dict):
        raise FactusConfigurationError("FACTUS_UNIT_CODES_JSON debe ser un objeto JSON.")

    normalized_key = unit.strip().lower()
    code = configured.get(normalized_key)
    if code is not None and str(code).strip():
        return str(code)

    catalog_names = {
        "unidad": "unidad",
        "kilos": "kilogramo",
        "gramos": "gramo",
        "litros": "litro",
        "metros": "metro",
        "horas": "hora",
        "mes": "mes",
    }
    expected_name = catalog_names.get(normalized_key)
    if expected_name:
        matching_codes = {
            str(entry["code"])
            for entry in _unit_measures_catalog()
            if entry.get("name")
            and _normalize(str(entry["name"])) == _normalize(expected_name)
            and entry.get("code")
        }
        if len(matching_codes) == 1:
            return matching_codes.pop()

    if code is None or not str(code).strip():
        raise FactusConfigurationError(
            f"Falta el código Factus de unidad para '{unit}'. "
            "Agrégalo a FACTUS_UNIT_CODES_JSON tras verificar el catálogo."
        )
    return str(code)


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"El valor '{field}' no es un número decimal válido.") from error
    if not result.is_finite():
        raise ValueError(f"El valor '{field}' debe ser finito.")
    return result


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal) -> str:
    return format(_money(value), ".2f")


def construir_payload_factus(
    usuario: dict[str, Any],
    productos: list[tuple[dict[str, Any], int]],
    reference_code: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Construye el documento Factus y los totales locales usando Decimal."""
    if settings.FACTUS_NUMBERING_RANGE_ID is None:
        raise FactusConfigurationError(
            "Configura FACTUS_NUMBERING_RANGE_ID con un rango activo de Factus."
        )

    tipo_persona = str(usuario.get("tipo_persona", "")).lower()
    if tipo_persona not in {"natural", "juridica"}:
        raise ValueError("El tipo de persona del cliente no es válido.")
    if tipo_persona == "juridica":
        document_code = "6"
        identification = str(usuario.get("numero_documeto_nit", "")).strip()
        nit_parts = re.fullmatch(r"(\d+)[-\s](\d)", identification)
        if nit_parts:
            nit_number, supplied_dv = nit_parts.groups()
        elif re.fullmatch(r"\d{10}", identification):
            # SUPUESTO: Un NIT de 10 dígitos sin separador incluye el DV al final.
            nit_number, supplied_dv = identification[:-1], identification[-1]
        elif re.fullmatch(r"\d{1,15}", identification):
            nit_number, supplied_dv = identification, None
        else:
            raise ValueError("El NIT del cliente tiene un formato inválido.")
        identification = nit_number
        dv = str(calcular_dv_nit(nit_number))
        if supplied_dv is not None and supplied_dv != dv:
            raise ValueError("El dígito de verificación del NIT no es válido.")
        legal_organization_id = "1"
    else:
        document_types = {"CC": "3", "TI": "2", "CE": "5"}
        tipo_documento = str(usuario.get("tipo_documento") or "").upper()
        if tipo_documento not in document_types:
            raise ValueError("El tipo de documento del cliente no es válido para Factus.")
        document_code = document_types[tipo_documento]
        identification = str(usuario.get("numero_documeto_nit", "")).strip()
        dv = None
        legal_organization_id = "2"

    customer: dict[str, Any] = {
        "identification_document_code": document_code,
        "identification": identification,
        "names": str(usuario.get("nombre", "")).strip(),
        "email": str(usuario.get("correo", "")).strip(),
        "address": str(usuario.get("direccion", "")).strip(),
        "phone": str(usuario.get("telefono_celular", "")).strip(),
        "legal_organization_id": legal_organization_id,
        "tribute_code": settings.FACTUS_TRIBUTE_CODE,
        "municipality_id": obtener_municipio_id(
            str(usuario.get("municipio_departamento", ""))
        ),
    }
    if dv is not None:
        customer["dv"] = dv

    factus_items: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    total_tax = Decimal("0.00")

    for product, quantity in productos:
        unit_price = _money(_decimal(product.get("precio_unitario"), "precio_unitario"))
        # La validación existente limita descuento a 0..100: se interpreta como porcentaje.
        discount_rate = _decimal(product.get("descuento") or 0, "descuento")
        tax_rate = _decimal(product.get("tarifa_iva") or 0, "tarifa_iva")
        if not 0 <= discount_rate <= 100:
            raise ValueError("El descuento del producto debe estar entre 0 y 100.")
        if not 0 <= tax_rate <= 100:
            raise ValueError("La tarifa de IVA del producto debe estar entre 0 y 100.")

        gross = _money(unit_price * quantity)
        discount_amount = _money(gross * discount_rate / Decimal("100"))
        taxable_amount = _money(gross - discount_amount)
        tax_amount = _money(taxable_amount * tax_rate / Decimal("100"))
        subtotal += gross
        total_discount += discount_amount
        total_tax += tax_amount

        taxes: list[dict[str, str]] = []
        if tax_rate > 0:
            taxes.append(
                {
                    "code": "01",
                    "tax_amount": _money_text(tax_amount),
                    "percent": _money_text(tax_rate),
                    "taxable_amount": _money_text(taxable_amount),
                    "rate": _money_text(tax_rate),
                }
            )

        product_id = product.get("idproductos", product.get("idproducto"))
        product_code = product.get("codigo_interno") or product_id
        unspsc_code = str(product.get("codigo_UNSPSC", "")).strip()
        if not re.fullmatch(r"\d{8}", unspsc_code):
            raise ValueError(
                f"El código UNSPSC del producto con id {product_id} debe tener 8 dígitos."
            )
        factus_items.append(
            {
                "code_reference": str(product_code),
                "name": str(product.get("nombre", "")).strip(),
                "quantity": quantity,
                "price": _money_text(unit_price),
                "discount_rate": _money_text(discount_rate),
                "tax_rate": _money_text(tax_rate),
                "unit_measure_code": _unit_code(str(product.get("Uni_medida", ""))),
                # Factus standard_code indica el estándar, no el código de producto.
                "standard_code": "001",
                "is_excluded": 1 if tax_rate == 0 else 0,
                "taxes": taxes,
            }
        )
        detail_rows.append(
            {
                "idproducto": int(product_id),
                "cantidad": quantity,
                "precio_unitario": unit_price,
                "subtotal": gross,
                "descuento": discount_amount,
                "iva": tax_amount,
            }
        )

    subtotal = _money(subtotal)
    total_discount = _money(total_discount)
    total_tax = _money(total_tax)
    total = _money(subtotal - total_discount + total_tax)
    today = date.today().isoformat()
    payment_details = [
        {
            "payment_form": settings.FACTUS_PAYMENT_FORM,
            "payment_method_code": settings.FACTUS_PAYMENT_METHOD_CODE,
            "payment_due_date": today,
            "payment_duration": "0",
            "amount": _money_text(total),
        }
    ]

    payload = {
        "document_type_id": settings.FACTUS_DOCUMENT_TYPE_ID,
        "numbering_range_id": settings.FACTUS_NUMBERING_RANGE_ID,
        "reference_code": reference_code,
        "payment_form": settings.FACTUS_PAYMENT_FORM,
        "payment_method_code": settings.FACTUS_PAYMENT_METHOD_CODE,
        "payment_due_date": today,
        "payment_details": payment_details,
        "customer": customer,
        "items": factus_items,
    }
    validar_datos_factura(payload)
    return payload, {
        "subtotal": subtotal,
        "descuento_total": total_discount,
        "iva": total_tax,
        "total": total,
        "detalles": detail_rows,
    }


def calcular_dv_nit(nit: str) -> int:
    """Calcula el dígito de verificación colombiano con el algoritmo DIAN."""
    weights = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
    if not nit.isdigit() or not 1 <= len(nit) <= len(weights):
        raise ValueError("El NIT debe contener entre 1 y 15 dígitos.")
    total = sum(
        int(digit) * weight
        for digit, weight in zip(reversed(nit), weights)
    )
    remainder = total % 11
    return remainder if remainder in (0, 1) else 11 - remainder


def crear_factura_factus(payload: dict[str, Any]) -> dict[str, Any]:
    """Valida y emite una factura en Factus, devolviendo la respuesta JSON."""
    validar_datos_factura(payload)
    token = obtener_token()
    try:
        response = requests.post(
            f"{_factus_base_url()}/v2/bills/validate",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.Timeout as error:
        logger.warning("Factus invoice request timed out.")
        raise FactusIntegrationError(
            502, {"message": "Tiempo de espera agotado al crear la factura en Factus."}
        ) from error
    except requests.RequestException as error:
        logger.warning("Factus invoice request failed: %s", type(error).__name__)
        raise FactusIntegrationError(
            502, {"message": "No fue posible conectarse con Factus para crear la factura."}
        ) from error

    if response.status_code >= 500:
        detail = _response_detail(response)
        logger.warning("Factus invoice endpoint returned HTTP %s.", response.status_code)
        raise FactusIntegrationError(502, detail, response.status_code)
    if response.status_code == 401:
        global _TOKEN, _TOKEN_EXPIRES_AT
        with _TOKEN_LOCK:
            _TOKEN = None
            _TOKEN_EXPIRES_AT = 0.0
        logger.warning("Factus rejected the cached access token.")
        raise FactusIntegrationError(
            502,
            {"provider_status": 401, "factus": _response_detail(response)},
            401,
        )
    if response.status_code == 422:
        detail = _response_detail(response)
        logger.info("Factus rejected invoice validation with HTTP 422.")
        raise FactusIntegrationError(400, detail, 422)
    if not response.ok:
        detail = _response_detail(response)
        logger.warning("Factus invoice endpoint returned HTTP %s.", response.status_code)
        raise FactusIntegrationError(400, detail, response.status_code)

    try:
        return response.json()
    except ValueError as error:
        raise FactusIntegrationError(
            502, {"message": "Factus devolvió una respuesta de factura inválida."}
        ) from error
