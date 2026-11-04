"""Proveedores de pago electrónico.

- ``WompiProvider``: Web Checkout de Wompi con firma de integridad del proveedor,
  confirmación por webhook firmado (X-Event-Checksum) y consulta de la transacción.
  Docs: https://docs.wompi.co/docs/colombia/widget-checkout-web/ y /eventos/
- ``BreBManualProvider``: QR con la llave Bre-B del comercio, monto y referencia,
  firmado con HMAC. La confirmación es manual (comprobante + verificación).

Nunca se manejan datos de tarjeta: el pago con tarjeta se captura en el checkout
del proveedor (cumplimiento PCI DSS).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from urllib.parse import urlencode

import qrcode
import requests

from backend.core.errores import ConfiguracionError, ServicioExternoError
from backend.core.utilidades import desde_centavos, dinero_texto, iso_utc
from backend.crudDataBase.configDataBase.conf import settings

logger = logging.getLogger(__name__)


def generar_qr_png_base64(contenido: str) -> str:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=3)
    qr.add_data(contenido)
    qr.make(fit=True)
    buffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


@dataclass(frozen=True)
class InicioPago:
    canal: str
    checkout_url: str | None
    qr_payload: str


class PaymentProvider(Protocol):
    canal: str

    def iniciar(self, *, referencia: str, monto_centavos: int, moneda: str, expira_en: datetime,
                firma: str, cliente: dict[str, Any]) -> InicioPago: ...


# ----------------------------------------------------------------------- Wompi
class WompiProvider:
    canal = "WOMPI"
    CHECKOUT_URL = "https://checkout.wompi.co/p/"

    def __init__(self, public_key: str, integrity_secret: str, events_secret: str, entorno: str,
                 redirect_url: str = "", session: requests.Session | None = None, timeout: float = 20):
        self.public_key = public_key
        self._integrity_secret = integrity_secret
        self._events_secret = events_secret
        self.api_url = ("https://production.wompi.co/v1" if entorno == "production"
                        else "https://sandbox.wompi.co/v1")
        self.redirect_url = redirect_url
        self._http = session or requests.Session()
        self.timeout = timeout

    @staticmethod
    def formato_expiracion(expira_en: datetime) -> str:
        return expira_en.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def firma_integridad(self, referencia: str, monto_centavos: int, moneda: str, expiracion: str) -> str:
        # Orden documentado: <Referencia><Monto><Moneda><FechaExpiracion><SecretoIntegridad>
        cadena = f"{referencia}{int(monto_centavos)}{moneda}{expiracion}{self._integrity_secret}"
        return hashlib.sha256(cadena.encode("utf-8")).hexdigest()

    def iniciar(self, *, referencia: str, monto_centavos: int, moneda: str, expira_en: datetime,
                firma: str, cliente: dict[str, Any]) -> InicioPago:
        expiracion = self.formato_expiracion(expira_en)
        parametros = {
            "public-key": self.public_key,
            "currency": moneda,
            "amount-in-cents": str(int(monto_centavos)),
            "reference": referencia,
            "signature:integrity": self.firma_integridad(referencia, monto_centavos, moneda, expiracion),
            "expiration-time": expiracion,
        }
        if self.redirect_url:
            parametros["redirect-url"] = self.redirect_url
        if cliente.get("email"):
            parametros["customer-data:email"] = cliente["email"]
        url = f"{self.CHECKOUT_URL}?{urlencode(parametros)}"
        return InicioPago(canal=self.canal, checkout_url=url, qr_payload=url)

    def evento_valido(self, evento: dict[str, Any], checksum_header: str | None) -> bool:
        """Valida X-Event-Checksum: SHA256(valores de signature.properties + timestamp + secreto)."""
        firma = evento.get("signature") or {}
        propiedades = firma.get("properties")
        checksum = (checksum_header or firma.get("checksum") or "").strip()
        timestamp = evento.get("timestamp")
        if not isinstance(propiedades, list) or not checksum or timestamp is None or not self._events_secret:
            return False
        valores = []
        for ruta in propiedades:
            actual: Any = evento.get("data", {})
            for parte in str(ruta).split("."):
                if not isinstance(actual, dict) or parte not in actual:
                    return False
                actual = actual[parte]
            valores.append(str(actual))
        cadena = "".join(valores) + str(timestamp) + self._events_secret
        calculado = hashlib.sha256(cadena.encode("utf-8")).hexdigest()
        return hmac.compare_digest(calculado.upper(), checksum.upper())

    def consultar_transaccion(self, transaccion_id: str) -> dict[str, Any]:
        try:
            respuesta = self._http.get(
                f"{self.api_url}/transactions/{transaccion_id}",
                headers={"Authorization": f"Bearer {self.public_key}"}, timeout=self.timeout,
            )
        except requests.RequestException as error:
            raise ServicioExternoError("No fue posible consultar la transacción en Wompi.") from error
        if respuesta.status_code != 200:
            raise ServicioExternoError(
                "Wompi no devolvió la transacción.", detalles={"provider_status": respuesta.status_code}
            )
        datos = respuesta.json().get("data")
        if not isinstance(datos, dict):
            raise ServicioExternoError("Wompi devolvió una transacción inválida.")
        return datos


# --------------------------------------------------------------- Bre-B manual
class BreBManualProvider:
    """QR para transferencia Bre-B confirmada manualmente.

    El QR contiene un JSON firmado (llave, monto, referencia, expiración, firma). Una app
    bancaria no lo usa para autocompletar el monto: eso requiere el QR EMVCo que emite el
    banco o un proveedor. Sirve para que el cliente vea los datos exactos y para que el
    comprobante que suba quede amarrado a la referencia y la firma.
    """

    canal = "BREB_MANUAL"

    def __init__(self, llave: str, nombre_comercio: str = ""):
        self.llave = llave
        self.nombre_comercio = nombre_comercio

    def iniciar(self, *, referencia: str, monto_centavos: int, moneda: str, expira_en: datetime,
                firma: str, cliente: dict[str, Any]) -> InicioPago:
        if not self.llave:
            raise ConfiguracionError("Configura BREB_LLAVE_COMERCIO para recibir transferencias manuales.")
        payload = {
            "tipo": "BREB",
            "llave": self.llave,
            "comercio": self.nombre_comercio or None,
            "monto": dinero_texto(desde_centavos(monto_centavos)),
            "moneda": moneda,
            "referencia": referencia,
            "expira_en": iso_utc(expira_en),
            "firma": firma,
        }
        return InicioPago(canal=self.canal, checkout_url=None,
                          qr_payload=json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def wompi_configurado() -> bool:
    return all([settings.WOMPI_PUBLIC_KEY, settings.WOMPI_INTEGRITY_SECRET, settings.WOMPI_EVENTS_SECRET])


def obtener_wompi() -> WompiProvider:
    if not wompi_configurado():
        raise ConfiguracionError(
            "Configura WOMPI_PUBLIC_KEY, WOMPI_INTEGRITY_SECRET y WOMPI_EVENTS_SECRET."
        )
    return WompiProvider(settings.WOMPI_PUBLIC_KEY, settings.WOMPI_INTEGRITY_SECRET,
                         settings.WOMPI_EVENTS_SECRET, settings.WOMPI_ENV, settings.WOMPI_REDIRECT_URL)


def proveedor_para(canal: str) -> PaymentProvider | None:
    if canal == "WOMPI":
        return obtener_wompi()
    if canal == "BREB_MANUAL":
        return BreBManualProvider(settings.BREB_LLAVE_COMERCIO, settings.BREB_NOMBRE_COMERCIO)
    return None  # EFECTIVO y DATAFONO no generan QR ni checkout
