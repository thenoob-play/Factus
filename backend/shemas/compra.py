from pydantic import BaseModel, Field

# Submodelo para cada producto individual dentro de la compra
class DetalleCompra(BaseModel):
    idproducto: int = Field(gt=0)
    cantidad: int = Field(gt=0)

# Modelo principal que incluye el usuario y la lista de productos
class CompraCreate(BaseModel):
    idusuario: int = Field(gt=0)
    items: list[DetalleCompra] = Field(min_length=1)