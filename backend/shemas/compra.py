from pydantic import BaseModel, ConfigDict, Field

class DetalleCompra(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    idproducto: int = Field(gt=0)
    cantidad: int = Field(gt=0)


class CompraCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    idusuario: int = Field(gt=0)
    items: list[DetalleCompra] = Field(min_length=1)