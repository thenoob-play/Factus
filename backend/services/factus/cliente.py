"""Cliente HTTP aislado para la API v2 de Factus.

Endpoints verificados en https://developers.factus.com.co:
    POST   /oauth/token                               (password y refresh_token)
    POST   /v2/bills/validate                         crear y validar factura
    GET    /v2/bills?filter[reference_code]=...       listar / filtrar
    GET    /v2/bills/{number}                         ver factura
    GET    /v2/bills/{number}/download-pdf            -> pdf_base_64_encoded
    GET    /v2/bills/{number}/download-xml            -> xml_base_64_encoded
    POST   /v2/bills/{number}/send-email              {"email": ...}
    DELETE /v2/bills/destroy/reference/{reference}    solo facturas no validadas
    POST   /v2/credit-notes/validate                  nota crédito
    GET    /v2/numbering-ranges[/{id}]                rangos de numeración

Nunca se registran en logs credenciales, tokens ni cuerpos completos.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests

from backend.core.errores import AppError, ConfiguracionError
from backend.crudDataBase.configDataBase.conf import settings

logger = logging.getLogger(__name__)


class FactusError(AppError):
    status_code = 502
    codigo = "FACTUS_ERROR"

    def __init__(self, mensaje: str, *, provider_status: int | None = None, detalle: Any = None,
                 codigo: str | None = None, status_code: int | None = None):
        super().__init__(mensaje, codigo=codigo, status_code=status_code,
                         detalles={"provider_status": provider_status, "factus": detalle})
        self.provider_status = provider_status
        self.detalle = detalle


class FactusRechazoError(FactusError):
    """Factus rechazó el documento (validación). Reintentar sin corregir no sirve."""
    status_code = 422
    codigo = "FACTUS_RECHAZO"


class FactusConflictoError(FactusError):
    """409: existe un documento pendiente por enviar a la DIAN con esa referencia."""
    status_code = 409
    codigo = "FACTUS_CONFLICTO"


class FactusNoDisponibleError(FactusError):
    """Error de red, timeout o 5xx tras agotar los reintentos."""
    status_code = 503
    codigo = "FACTUS_NO_DISPONIBLE"


class FactusTimeoutError(FactusNoDisponibleError):
    """No se sabe si Factus procesó la petición: hay que consultar antes de reintentar."""
    codigo = "FACTUS_TIMEOUT"


@dataclass
class _Token:
    access: str
    refresh: str | None
    expira: float


class FactusClient:
    def __init__(
        self,
        base_url: str | None,
        client_id: str | None,
        client_secret: str | None,
        username: str | None,
        password: str | None,
        *,
        timeout: float = 30,
        max_retries: int = 3,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.base_url = (base_url or "").rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._username = username
        self._password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self._http = session or requests.Session()
        self._sleep = sleep
        self._token: _Token | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------- autenticación
    def _verificar_configuracion(self) -> None:
        if not all([self.base_url, self._client_id, self._client_secret, self._username, self._password]):
            raise ConfiguracionError(
                "Configura FACTUS_BASE_URL, FACTUS_CLIENT_ID, FACTUS_CLIENT_SECRET, "
                "FACTUS_USERNAME y FACTUS_PASSWORD."
            )

    def _pedir_token(self, datos: dict[str, str]) -> _Token:
        try:
            respuesta = self._http.post(
                f"{self.base_url}/oauth/token", data=datos,
                headers={"Accept": "application/json"}, timeout=self.timeout,
            )
        except requests.RequestException as error:
            logger.warning("Factus OAuth: fallo de red (%s).", type(error).__name__)
            raise FactusNoDisponibleError("No fue posible autenticar con Factus.") from error
        if respuesta.status_code != 200:
            logger.warning("Factus OAuth respondió HTTP %s.", respuesta.status_code)
            raise FactusError(
                "Factus rechazó la autenticación. Revisa las credenciales.",
                provider_status=respuesta.status_code, codigo="FACTUS_AUTH",
            )
        try:
            cuerpo = respuesta.json()
            expira_en = int(cuerpo.get("expires_in", 3600))
            access = str(cuerpo["access_token"])
        except (ValueError, KeyError, TypeError) as error:
            raise FactusError("Factus devolvió una respuesta de autenticación inválida.") from error
        margen = min(120, max(5, expira_en // 10))
        return _Token(access, cuerpo.get("refresh_token"), time.monotonic() + max(1, expira_en - margen))

    def _access_token(self) -> str:
        self._verificar_configuracion()
        with self._lock:
            if self._token and time.monotonic() < self._token.expira:
                return self._token.access
            if self._token and self._token.refresh:
                try:
                    self._token = self._pedir_token({
                        "grant_type": "refresh_token",
                        "client_id": str(self._client_id),
                        "client_secret": str(self._client_secret),
                        "refresh_token": self._token.refresh,
                    })
                    return self._token.access
                except FactusError:
                    logger.info("Factus: el refresh_token falló; se usa usuario y contraseña.")
            self._token = self._pedir_token({
                "grant_type": "password",
                "client_id": str(self._client_id),
                "client_secret": str(self._client_secret),
                "username": str(self._username),
                "password": str(self._password),
            })
            return self._token.access

    def invalidar_token(self) -> None:
        with self._lock:
            self._token = None

    # -------------------------------------------------------------- transporte
    def _request(
        self, metodo: str, ruta: str, *, json: Any = None, params: dict[str, Any] | None = None,
        reintentar: bool = True,
    ) -> tuple[int, Any]:
        """Hace la petición con backoff exponencial ante red/5xx/429.

        ``reintentar=False`` (para POST que crean documentos) no repite tras un timeout:
        el llamador debe consultar por reference_code antes de reintentar.
        """
        intentos = (self.max_retries + 1) if reintentar else 1
        token_renovado = False
        intento = 0
        while True:
            intento += 1
            token = self._access_token()
            try:
                respuesta = self._http.request(
                    metodo, f"{self.base_url}{ruta}", json=json, params=params, timeout=self.timeout,
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                             "Content-Type": "application/json"},
                )
            except requests.Timeout as error:
                logger.warning("Factus %s %s: timeout (intento %s).", metodo, ruta, intento)
                if intento >= intentos:
                    raise FactusTimeoutError("Tiempo de espera agotado con Factus.") from error
                self._sleep(0.5 * 2 ** (intento - 1))
                continue
            except requests.RequestException as error:
                logger.warning("Factus %s %s: error de red %s (intento %s).", metodo, ruta,
                               type(error).__name__, intento)
                if intento >= intentos:
                    raise FactusNoDisponibleError("No fue posible conectarse con Factus.") from error
                self._sleep(0.5 * 2 ** (intento - 1))
                continue

            status = respuesta.status_code
            if status == 401 and not token_renovado:
                self.invalidar_token()
                token_renovado = True
                intento -= 1
                continue
            if (status >= 500 or status == 429) and intento < intentos:
                logger.warning("Factus %s %s: HTTP %s, reintentando.", metodo, ruta, status)
                self._sleep(0.5 * 2 ** (intento - 1))
                continue
            return status, _cuerpo(respuesta)

    @staticmethod
    def _error(status: int, cuerpo: Any, accion: str) -> FactusError:
        mensaje = _mensaje(cuerpo) or f"Factus no pudo {accion}."
        if status in (400, 422):
            return FactusRechazoError(mensaje, provider_status=status, detalle=cuerpo)
        if status == 409:
            return FactusConflictoError(mensaje, provider_status=status, detalle=cuerpo)
        if status == 404:
            return FactusError(mensaje, provider_status=status, detalle=cuerpo,
                               codigo="FACTUS_NO_ENCONTRADO", status_code=404)
        if status >= 500 or status == 429:
            return FactusNoDisponibleError(mensaje, provider_status=status, detalle=cuerpo)
        return FactusError(mensaje, provider_status=status, detalle=cuerpo)

    # ------------------------------------------------------------------ facturas
    def validar_factura(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, cuerpo = self._request("POST", "/v2/bills/validate", json=payload, reintentar=False)
        if status in (200, 201):
            return cuerpo
        raise self._error(status, cuerpo, "crear la factura")

    def buscar_factura_por_referencia(self, reference_code: str) -> dict[str, Any] | None:
        status, cuerpo = self._request(
            "GET", "/v2/bills", params={"filter[reference_code]": reference_code}
        )
        if status != 200:
            raise self._error(status, cuerpo, "consultar facturas")
        for item in _lista(cuerpo):
            if str(item.get("reference_code")) == reference_code:
                return item
        return None

    def ver_factura(self, numero: str) -> dict[str, Any]:
        status, cuerpo = self._request("GET", f"/v2/bills/{quote(numero, safe='')}")
        if status != 200:
            raise self._error(status, cuerpo, "consultar la factura")
        return cuerpo

    def descargar_pdf(self, numero: str) -> tuple[bytes, str | None]:
        return self._descargar(numero, "download-pdf", "pdf_base_64_encoded")

    def descargar_xml(self, numero: str) -> tuple[bytes, str | None]:
        return self._descargar(numero, "download-xml", "xml_base_64_encoded")

    def _descargar(self, numero: str, ruta: str, campo: str) -> tuple[bytes, str | None]:
        status, cuerpo = self._request("GET", f"/v2/bills/{quote(numero, safe='')}/{ruta}")
        if status != 200:
            raise self._error(status, cuerpo, "descargar el documento")
        datos = cuerpo.get("data", cuerpo) if isinstance(cuerpo, dict) else {}
        contenido = datos.get(campo) if isinstance(datos, dict) else None
        if not contenido:
            raise FactusError(f"Factus no devolvió el campo {campo}.", detalle=None)
        try:
            return base64.b64decode(contenido, validate=True), datos.get("file_name")
        except (ValueError, TypeError) as error:
            raise FactusError("Factus devolvió un archivo base64 inválido.") from error

    def enviar_email(self, numero: str, email: str) -> dict[str, Any]:
        status, cuerpo = self._request(
            "POST", f"/v2/bills/{quote(numero, safe='')}/send-email", json={"email": email}
        )
        if status not in (200, 201):
            raise self._error(status, cuerpo, "enviar el correo")
        return cuerpo

    def eliminar_factura_por_referencia(self, reference_code: str) -> None:
        status, cuerpo = self._request(
            "DELETE", f"/v2/bills/destroy/reference/{quote(reference_code, safe='')}"
        )
        if status not in (200, 204):
            raise self._error(status, cuerpo, "eliminar la factura pendiente")

    # ------------------------------------------------------------- notas crédito
    def validar_nota_credito(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, cuerpo = self._request("POST", "/v2/credit-notes/validate", json=payload, reintentar=False)
        if status in (200, 201):
            return cuerpo
        raise self._error(status, cuerpo, "crear la nota crédito")

    # ----------------------------------------------------------------- catálogos
    def listar_rangos(self) -> list[dict[str, Any]]:
        status, cuerpo = self._request("GET", "/v2/numbering-ranges", params={"filter[is_active]": 1})
        if status != 200:
            raise self._error(status, cuerpo, "listar los rangos de numeración")
        return _lista(cuerpo)

    def ver_rango(self, idrango: int) -> dict[str, Any]:
        status, cuerpo = self._request("GET", f"/v2/numbering-ranges/{int(idrango)}")
        if status != 200:
            raise self._error(status, cuerpo, "consultar el rango de numeración")
        datos: Any = cuerpo
        while isinstance(datos, dict) and "id" not in datos and isinstance(datos.get("data"), (dict, list)):
            datos = datos["data"]
        if isinstance(datos, list):
            datos = next((r for r in datos if str(r.get("id")) == str(idrango)), None)
        if not isinstance(datos, dict) or "id" not in datos:
            raise ConfiguracionError(f"Factus no devolvió el rango de numeración {idrango}.")
        return datos


# ----------------------------------------------------------------- utilidades
def _cuerpo(respuesta: requests.Response) -> Any:
    try:
        return respuesta.json()
    except ValueError:
        return {"message": (respuesta.text or "")[:2000]}


def _mensaje(cuerpo: Any) -> str | None:
    if isinstance(cuerpo, dict):
        mensaje = cuerpo.get("message")
        if isinstance(mensaje, str) and mensaje.strip():
            return mensaje.strip()[:500]
    return None


def _lista(cuerpo: Any) -> list[dict[str, Any]]:
    """Encuentra la lista de registros en respuestas paginadas ({data: {data: [...]}} o similares)."""
    actual = cuerpo
    for _ in range(4):
        if isinstance(actual, list):
            return [x for x in actual if isinstance(x, dict)]
        if not isinstance(actual, dict):
            break
        actual = actual.get("data")
    return []


def extraer_documento(respuesta: Any) -> dict[str, Any]:
    """Normaliza la respuesta de factura o nota crédito (v2 usa data.*, v1 usaba data.bill.*)."""
    datos: Any = respuesta.get("data", respuesta) if isinstance(respuesta, dict) else {}
    if isinstance(datos, dict):
        for clave in ("bill", "credit_note"):
            if isinstance(datos.get(clave), dict):
                datos = {**datos, **datos[clave]}
    else:
        datos = {}
    links = datos.get("links") if isinstance(datos.get("links"), dict) else {}
    numero = datos.get("number")
    prefijo = datos.get("prefix")
    if not prefijo and isinstance(numero, str):
        letras = "".join(c for c in numero if c.isalpha())
        prefijo = letras or None
    validado = datos.get("is_validated", datos.get("validated"))
    return {
        "numero": str(numero) if numero else None,
        "prefijo": prefijo,
        "cufe": datos.get("cufe") or datos.get("cude") or datos.get("uuid"),
        "qr_url": links.get("qr") or datos.get("qr") or datos.get("qr_image"),
        "public_url": links.get("public_url") or datos.get("public_url"),
        "is_validated": str(validado).lower() in {"1", "true"} if validado is not None else bool(datos.get("cufe")),
        "validated_at": datos.get("validated_at") or datos.get("validated"),
        "errores": datos.get("errors") or None,
        "mensaje": respuesta.get("message") if isinstance(respuesta, dict) else None,
    }


_cliente: FactusClient | None = None
_cliente_lock = threading.Lock()


def obtener_cliente_factus() -> FactusClient:
    """Instancia compartida (mantiene el token en caché entre peticiones)."""
    global _cliente
    with _cliente_lock:
        if _cliente is None:
            _cliente = FactusClient(
                settings.FACTUS_BASE_URL, settings.FACTUS_CLIENT_ID, settings.FACTUS_CLIENT_SECRET,
                settings.FACTUS_USERNAME, settings.FACTUS_PASSWORD,
                timeout=settings.FACTUS_TIMEOUT_SECONDS, max_retries=settings.FACTUS_MAX_RETRIES,
            )
        return _cliente
