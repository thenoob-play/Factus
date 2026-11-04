"""Firma de integridad de pagos: HMAC-SHA256(secreto, referencia|centavos|moneda|expira_en).

La firma se calcula una sola vez al crear el pago. Toda confirmación (webhook,
verificación manual, efectivo, datáfono) la recalcula desde los datos guardados y
compara el monto recibido con el monto firmado. Si algo no coincide, el pago se
rechaza y el intento queda marcado como sospechoso.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from backend.core.errores import ConfiguracionError
from backend.core.utilidades import iso_utc
from backend.crudDataBase.configDataBase.conf import settings


def _secreto(secreto: str | None = None) -> bytes:
    valor = secreto if secreto is not None else settings.PAYMENT_SIGNING_SECRET
    if len(valor) < 32:
        raise ConfiguracionError("PAYMENT_SIGNING_SECRET debe tener al menos 32 caracteres.")
    return valor.encode("utf-8")


def mensaje_firma(referencia: str, monto_centavos: int, moneda: str, expira_en: datetime) -> str:
    return f"{referencia}|{int(monto_centavos)}|{moneda.upper()}|{iso_utc(expira_en)}"


def firmar(referencia: str, monto_centavos: int, moneda: str, expira_en: datetime,
           *, secreto: str | None = None) -> str:
    mensaje = mensaje_firma(referencia, monto_centavos, moneda, expira_en)
    return hmac.new(_secreto(secreto), mensaje.encode("utf-8"), hashlib.sha256).hexdigest()


def firma_guardada_valida(pago: dict, *, secreto: str | None = None) -> bool:
    """Recalcula la firma con los datos almacenados del pago y la compara en tiempo constante."""
    esperada = firmar(pago["referencia"], pago["monto_esperado_centavos"], pago["moneda"],
                      pago["expira_en"], secreto=secreto)
    return hmac.compare_digest(esperada, str(pago["firma_integridad"]))


@dataclass(frozen=True)
class Verificacion:
    firma_valida: bool
    monto_valido: bool
    moneda_valida: bool
    referencia_valida: bool

    @property
    def ok(self) -> bool:
        return self.firma_valida and self.monto_valido and self.moneda_valida and self.referencia_valida

    def motivo(self) -> str | None:
        if not self.firma_valida:
            return "La firma de integridad del pago no coincide (datos alterados)."
        if not self.referencia_valida:
            return "La referencia recibida no corresponde al pago."
        if not self.moneda_valida:
            return "La moneda recibida no corresponde al pago."
        if not self.monto_valido:
            return "El monto recibido no coincide con el monto firmado del pago."
        return None


def verificar_confirmacion(
    pago: dict, *, monto_recibido_centavos: int, moneda: str | None = None,
    referencia: str | None = None, secreto: str | None = None,
) -> Verificacion:
    return Verificacion(
        firma_valida=firma_guardada_valida(pago, secreto=secreto),
        monto_valido=int(monto_recibido_centavos) == int(pago["monto_esperado_centavos"]),
        moneda_valida=moneda is None or moneda.upper() == str(pago["moneda"]).upper(),
        referencia_valida=referencia is None or referencia == pago["referencia"],
    )
