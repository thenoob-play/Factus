"""Catálogos de Factus v2, sincronizados y cacheados en la tabla `factus_catalogo`.

- Rangos de numeración: API (GET /v2/numbering-ranges).
- Municipios y unidades de medida: tablas JSON publicadas en la documentación v2.
- Tipos de documento, organizaciones, tributos, métodos de pago, estándares, impuestos
  y conceptos de nota crédito: tablas oficiales fijas
  (https://developers.factus.com.co/tablas-de-referencia/tablas/).
"""

from __future__ import annotations

import html
import json
import logging
from html.parser import HTMLParser
from typing import Any

import requests
from sqlalchemy.orm import Session

from backend.core.utilidades import ahora_utc
from backend.crudDataBase import CRUDreportes
from backend.crudDataBase.configDataBase.conf import settings
from backend.services.factus.cliente import FactusClient, FactusError

logger = logging.getLogger(__name__)

TABLAS_FIJAS: dict[str, list[dict[str, str]]] = {
    "tipos_documento": [
        {"code": "11", "name": "Registro civil"},
        {"code": "12", "name": "Tarjeta de identidad"},
        {"code": "13", "name": "Cédula de ciudadanía"},
        {"code": "21", "name": "Tarjeta de extranjería"},
        {"code": "22", "name": "Cédula de extranjería"},
        {"code": "31", "name": "NIT"},
        {"code": "41", "name": "Pasaporte"},
        {"code": "42", "name": "Documento de identificación extranjero"},
        {"code": "47", "name": "PEP"},
        {"code": "48", "name": "PPT (Permiso Protección Temporal)"},
        {"code": "50", "name": "NIT de otro país"},
        {"code": "91", "name": "NUIP"},
    ],
    "organizaciones_juridicas": [
        {"code": "1", "name": "Persona Jurídica"},
        {"code": "2", "name": "Persona Natural"},
    ],
    "tributos_cliente": [
        {"code": "01", "name": "IVA"},
        {"code": "ZZ", "name": "No aplica"},
    ],
    "metodos_pago": [
        {"code": "10", "name": "Efectivo"},
        {"code": "42", "name": "Consignación"},
        {"code": "20", "name": "Cheque"},
        {"code": "47", "name": "Transferencia"},
        {"code": "71", "name": "Bonos"},
        {"code": "72", "name": "Vales"},
        {"code": "1", "name": "Medio de pago no definido"},
        {"code": "49", "name": "Tarjeta Débito"},
        {"code": "48", "name": "Tarjeta Crédito"},
        {"code": "ZZZ", "name": "Otro"},
    ],
    "formas_pago": [
        {"code": "1", "name": "Pago de contado"},
        {"code": "2", "name": "Pago a crédito"},
    ],
    "codigos_estandar": [
        {"code": "999", "name": "Estándar de adopción del contribuyente"},
        {"code": "001", "name": "UNSPSC"},
        {"code": "020", "name": "Partida Arancelaria"},
        {"code": "010", "name": "GTIN"},
    ],
    "impuestos": [
        {"code": "01", "name": "IVA - Impuesto sobre las ventas"},
        {"code": "04", "name": "INC - Impuesto Nacional al Consumo"},
        {"code": "35", "name": "Impuesto a productos ultraprocesados"},
    ],
    "conceptos_nota_credito": [
        {"code": "1", "name": "Devolución parcial de los bienes y/o no aceptación parcial del servicio"},
        {"code": "2", "name": "Anulación de factura electrónica"},
        {"code": "3", "name": "Rebaja o descuento parcial o total"},
        {"code": "4", "name": "Ajuste de precio"},
        {"code": "5", "name": "Descuento comercial por pronto pago"},
        {"code": "6", "name": "Descuento comercial por volumen de ventas"},
    ],
}
TIPOS_DESCARGABLES = ("municipios", "unidades_medida", "rangos_numeracion")
TIPOS = tuple(TABLAS_FIJAS) + TIPOS_DESCARGABLES


def codigos(tipo: str) -> set[str]:
    return {item["code"] for item in TABLAS_FIJAS[tipo]}


class _ParserPre(HTMLParser):
    """Extrae los bloques <pre> de la página de documentación (donde está el JSON)."""

    def __init__(self) -> None:
        super().__init__()
        self._dentro = False
        self._bloque: list[str] = []
        self.bloques: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "pre":
            self._dentro, self._bloque = True, []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "pre" and self._dentro:
            self._dentro = False
            self.bloques.append("".join(self._bloque))

    def handle_data(self, data: str) -> None:
        if self._dentro:
            self._bloque.append(data)


def _descargar_tabla(url: str, clave: str) -> list[dict[str, Any]]:
    try:
        respuesta = requests.get(url, timeout=settings.FACTUS_TIMEOUT_SECONDS)
        respuesta.raise_for_status()
    except requests.RequestException as error:
        raise FactusError(f"No fue posible descargar el catálogo '{clave}' de Factus.") from error
    try:
        datos: Any = respuesta.json()
    except ValueError:
        parser = _ParserPre()
        parser.feed(respuesta.text)
        datos = None
        for bloque in parser.bloques:
            try:
                datos = json.loads(html.unescape(bloque).strip())
                break
            except json.JSONDecodeError:
                continue
    for _ in range(3):
        if isinstance(datos, dict):
            datos = datos.get(clave, datos.get("data"))
    if not isinstance(datos, list) or not datos:
        raise FactusError(f"El catálogo '{clave}' de Factus está vacío o tiene un formato inesperado.")
    return [d for d in datos if isinstance(d, dict)]


def refrescar(db: Session, cliente: FactusClient, tipos: list[str] | None = None) -> dict[str, Any]:
    """Descarga y guarda los catálogos. Devuelve cuántos registros quedó cada uno o el error."""
    tipos = tipos or list(TIPOS)
    resumen: dict[str, Any] = {}
    for tipo in tipos:
        try:
            if tipo in TABLAS_FIJAS:
                datos: list[dict[str, Any]] = TABLAS_FIJAS[tipo]
            elif tipo == "municipios":
                datos = _descargar_tabla(settings.FACTUS_MUNICIPALITIES_URL, "municipalities")
            elif tipo == "unidades_medida":
                datos = _descargar_tabla(settings.FACTUS_UNIT_MEASURES_URL, "unitMeasures")
            elif tipo == "rangos_numeracion":
                datos = cliente.listar_rangos()
            else:
                resumen[tipo] = {"error": "Tipo de catálogo desconocido."}
                continue
            with db.begin():
                CRUDreportes.guardar_catalogo(db, tipo, datos, ahora_utc())
            resumen[tipo] = {"registros": len(datos)}
        except Exception as error:  # se informa por catálogo, sin cortar el resto
            logger.warning("No se pudo refrescar el catálogo %s: %s", tipo, type(error).__name__)
            mensaje = getattr(error, "mensaje", None) or "Error al refrescar el catálogo."
            resumen[tipo] = {"error": mensaje}
    return resumen


def leer(db: Session, tipo: str) -> list[dict[str, Any]] | None:
    if tipo in TABLAS_FIJAS:
        return TABLAS_FIJAS[tipo]
    fila = CRUDreportes.leer_catalogo(db, tipo)
    return fila["datos"] if fila else None


def codigo_en_catalogo(db: Session, tipo: str, codigo: str) -> bool | None:
    """True/False si el catálogo está cacheado; None si aún no se ha sincronizado."""
    datos = leer(db, tipo)
    if not datos:
        return None
    return any(str(item.get("code")) == codigo for item in datos)
