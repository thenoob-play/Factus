"""Esquemas de entrada de la API.

Todos usan ``extra="forbid"``: un campo no declarado (p. ej. un precio, un número de
tarjeta o un idtrabajador) hace que la petición se rechace con 422.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Telefono = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\+?[0-9 ]{7,20}$")]
Dinero = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]


class Estricto(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Estado(str, Enum):
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"


class MetodoPago(str, Enum):
    EFECTIVO = "EFECTIVO"
    TRANSFERENCIA = "TRANSFERENCIA"
    TARJETA = "TARJETA"


class Canal(str, Enum):
    WOMPI = "WOMPI"
    BREB_MANUAL = "BREB_MANUAL"
    DATAFONO = "DATAFONO"


# ------------------------------------------------------------------------ auth
class LoginIn(Estricto):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CambiarPasswordIn(Estricto):
    password_actual: str = Field(min_length=1, max_length=128)
    password_nueva: str = Field(min_length=10, max_length=72)


# ----------------------------------------------------------------- trabajadores
class TrabajadorIn(Estricto):
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]
    tipo_documento: Literal["13", "22", "41", "48", "12"] = "13"
    documento: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9A-Za-z]{5,20}$")]
    email: EmailStr
    telefono: Telefono | None = None
    rol: Literal["ADMIN", "TRABAJADOR"] = "TRABAJADOR"
    estado: Estado = Estado.ACTIVO


class TrabajadorCrear(TrabajadorIn):
    password: str = Field(min_length=10, max_length=72)


class TrabajadorActualizar(TrabajadorIn):
    password: str | None = Field(default=None, min_length=10, max_length=72)


# --------------------------------------------------------------------- clientes
class ClienteIn(Estricto):
    identification_document_code: Annotated[str, StringConstraints(pattern=r"^\d{2}$")] = Field(
        description="Código Factus del tipo de documento: 13 CC, 31 NIT, 22 CE, 41 pasaporte..."
    )
    identification: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9A-Za-z]{3,20}$")]
    dv: Annotated[str, StringConstraints(pattern=r"^\d$")] | None = Field(
        default=None, description="Si es NIT se calcula automáticamente; si lo envías, debe coincidir."
    )
    legal_organization_code: Literal["1", "2"] = Field(description="1 jurídica, 2 natural.")
    tribute_code: Literal["01", "ZZ"] = "ZZ"
    names: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)] | None = None
    company: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=150)] | None = None
    trade_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=150)] | None = None
    email: EmailStr | None = None
    phone: Telefono | None = None
    address: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=200)] | None = None
    municipality_code: Annotated[str, StringConstraints(pattern=r"^\d{1,10}$")] | None = None
    estado: Estado = Estado.ACTIVO

    @model_validator(mode="after")
    def _nombre_segun_organizacion(self) -> ClienteIn:
        if self.legal_organization_code == "1" and not self.company:
            raise ValueError("company (razón social) es obligatorio para persona jurídica.")
        if self.legal_organization_code == "2" and not self.names:
            raise ValueError("names es obligatorio para persona natural.")
        if self.identification_document_code == "31" and not self.identification.isdigit():
            raise ValueError("El NIT debe contener solo dígitos, sin DV ni guion.")
        return self


# -------------------------------------------------------------------- productos
class ProductoIn(Estricto):
    code_reference: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9._-]{2,50}$")]
    nombre: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    descripcion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None
    precio_unitario: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    stock: int = Field(default=0, ge=0, description="Solo al crear; luego usa /productos/{id}/stock.")
    stock_minimo: int = Field(default=0, ge=0)
    tax_rate: Literal[0, 5, 19] = 19
    is_excluded: bool = False
    tax_code: Literal["01", "04"] = Field(default="01", description="01 IVA, 04 INC (tribute del ítem).")
    unit_measure_code: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{1,10}$")] = "94"
    standard_code: Literal["999", "001", "010", "020"] = "999"
    codigo_unspsc: Annotated[str, StringConstraints(pattern=r"^\d{8}$")] | None = None
    discount_rate: Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)] = Decimal("0")
    estado: Estado = Estado.ACTIVO
    idcategoria: int | None = Field(default=None, gt=0)
    url_imagen: Annotated[str, StringConstraints(pattern=r"^https?://\S{3,250}$")] | None = None

    @model_validator(mode="after")
    def _coherencia(self) -> ProductoIn:
        if self.is_excluded and self.tax_rate != 0:
            raise ValueError("Un producto excluido de IVA debe tener tax_rate 0.")
        if self.standard_code == "001" and not self.codigo_unspsc:
            raise ValueError("Con standard_code 001 (UNSPSC) debes enviar codigo_unspsc.")
        return self


class AjusteStockIn(Estricto):
    delta: int = Field(description="Unidades a sumar (positivo) o restar (negativo).")
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]

    @model_validator(mode="after")
    def _no_cero(self) -> AjusteStockIn:
        if self.delta == 0:
            raise ValueError("delta no puede ser 0.")
        return self


# ----------------------------------------------------------------------- ventas
class ItemVentaIn(Estricto):
    model_config = ConfigDict(extra="forbid", strict=True)
    idproducto: int = Field(gt=0)
    cantidad: int = Field(gt=0, le=100_000)


class VentaIn(Estricto):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    idcliente: int = Field(gt=0)
    metodo_pago: MetodoPago = Field(alias="metodoPago")
    canal: Canal | None = Field(
        default=None,
        description="Opcional. TRANSFERENCIA: WOMPI o BREB_MANUAL. TARJETA: WOMPI o DATAFONO. "
                    "Por defecto se usa PAYMENT_PROVIDER.",
    )
    items: list[ItemVentaIn] = Field(min_length=1, max_length=200)


class RegenerarPagoIn(Estricto):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    metodo_pago: MetodoPago | None = Field(default=None, alias="metodoPago")
    canal: Canal | None = None
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


class CancelarVentaIn(Estricto):
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=255)]


# ------------------------------------------------------------------------ pagos
class EfectivoIn(Estricto):
    monto_recibido: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class DatafonoIn(Estricto):
    codigo_autorizacion: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9]{4,12}$")]
    ultimos4: Annotated[str, StringConstraints(pattern=r"^\d{4}$")]
    franquicia: Literal["VISA", "MASTERCARD", "AMEX", "DINERS", "OTRA"]
    tipo_tarjeta: Literal["CREDITO", "DEBITO"]
    recibo_numero: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9-]{3,64}$")]
    monto: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)] = Field(
        description="Monto impreso en el voucher; debe coincidir con el total de la venta."
    )


class ComprobanteIn(Estricto):
    banco_origen: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
    numero_comprobante: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z0-9-]{4,64}$")] = Field(
        description="Número de comprobante o CUS. Único en el sistema."
    )
    fecha_hora: datetime
    monto: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]
    imagen_base64: str | None = Field(default=None, description="Imagen PNG/JPEG opcional en base64.")


class ComprobantePublicoIn(ComprobanteIn):
    firma: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")] = Field(
        description="Firma incluida en el QR del pago."
    )


class VerificarComprobanteIn(Estricto):
    aprobar: bool
    monto_verificado: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)] | None = Field(
        default=None, description="Obligatorio al aprobar: monto visto en el extracto del banco."
    )
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None

    @model_validator(mode="after")
    def _monto_al_aprobar(self) -> VerificarComprobanteIn:
        if self.aprobar and self.monto_verificado is None:
            raise ValueError("monto_verificado es obligatorio para aprobar.")
        if not self.aprobar and not self.motivo:
            raise ValueError("motivo es obligatorio para rechazar.")
        return self


# ------------------------------------------------------------------------- caja
class AbrirCajaIn(Estricto):
    base_inicial: Dinero


class CerrarCajaIn(Estricto):
    efectivo_contado: Dinero
    observacion: Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)] | None = None


# --------------------------------------------------------------------- facturas
class EnviarEmailIn(Estricto):
    email: EmailStr | None = Field(default=None, description="Por defecto, el correo del cliente.")


class ItemNotaCreditoIn(Estricto):
    idproducto: int = Field(gt=0)
    cantidad: int = Field(gt=0)


class NotaCreditoIn(Estricto):
    correction_concept_code: Literal["1", "2", "3", "4", "5", "6"] = Field(
        description="1 devolución parcial, 2 anulación, 3 rebaja, 4 ajuste de precio, 5/6 descuentos."
    )
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    items: list[ItemNotaCreditoIn] | None = Field(
        default=None, description="Vacío = todas las unidades aún no devueltas (anulación total)."
    )
    restaurar_stock: bool = True


class RefrescarCatalogosIn(Estricto):
    tipos: list[str] | None = None
