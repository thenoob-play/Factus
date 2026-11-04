"""Utilidades de dinero (Decimal exacto), tiempo (UTC) y paginación."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
CIEN = Decimal("100")


def ahora_utc() -> datetime:
    """Fecha/hora UTC sin zona ni microsegundos (como se guarda en MySQL DATETIME)."""
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


ZONA_COLOMBIA = timezone(timedelta(hours=-5))  # Colombia no tiene horario de verano


def a_utc(valor: datetime) -> datetime:
    """Convierte a UTC sin zona. Una fecha sin zona se interpreta como hora de Colombia."""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=ZONA_COLOMBIA)
    return valor.astimezone(UTC).replace(tzinfo=None, microsecond=0)


def iso_utc(valor: datetime) -> str:
    return valor.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def decimal(valor: Any, campo: str = "valor") -> Decimal:
    if isinstance(valor, float):
        # Nunca operar con float: se convierte por su representación decimal corta.
        valor = repr(valor)
    try:
        resultado = Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"El campo '{campo}' no es un número decimal válido.") from error
    if not resultado.is_finite():
        raise ValueError(f"El campo '{campo}' debe ser un número finito.")
    return resultado


def dinero(valor: Any) -> Decimal:
    return decimal(valor).quantize(CENT, rounding=ROUND_HALF_UP)


def dinero_texto(valor: Any) -> str:
    return format(dinero(valor), ".2f")


def a_centavos(valor: Any) -> int:
    return int((dinero(valor) * CIEN).to_integral_value(rounding=ROUND_HALF_UP))


def desde_centavos(centavos: int) -> Decimal:
    return (Decimal(int(centavos)) / CIEN).quantize(CENT)


def paginar(page: int, page_size: int) -> tuple[int, int]:
    page = max(1, int(page))
    page_size = min(100, max(1, int(page_size)))
    return page_size, (page - 1) * page_size


def respuesta_paginada(items: list[Any], total: int, page: int, page_size: int) -> dict[str, Any]:
    page_size = min(100, max(1, page_size))
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }
