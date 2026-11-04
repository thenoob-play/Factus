"""CRUD de trabajadores (solo ADMIN), clientes y productos (TRABAJADOR y ADMIN)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.core.seguridad import SoloAdmin, UsuarioActual
from backend.crudDataBase.configDataBase.dataBase import get_db
from backend.services import servicesCliente, servicesProducto, servicesTrabajador
from backend.schemas.esquemas import (
    AjusteStockIn,
    ClienteIn,
    ProductoIn,
    TrabajadorActualizar,
    TrabajadorCrear,
)

DB = Annotated[Session, Depends(get_db)]
Pagina = Annotated[int, Query(ge=1)]
Tamano = Annotated[int, Query(ge=1, le=100)]
Buscar = Annotated[str | None, Query(min_length=1, max_length=100)]
EstadoQ = Annotated[Literal["ACTIVO", "INACTIVO"] | None, Query()]

# --------------------------------------------------------------- trabajadores
trabajadores = APIRouter(prefix="/trabajadores", tags=["Trabajadores (ADMIN)"])


@trabajadores.get("", summary="Listar trabajadores")
def listar_trabajadores(_: SoloAdmin, db: DB, buscar: Buscar = None,
                        rol: Literal["ADMIN", "TRABAJADOR"] | None = None, estado: EstadoQ = None,
                        page: Pagina = 1, page_size: Tamano = 20) -> dict:
    return servicesTrabajador.listar(db, buscar, rol, estado, page, page_size)


@trabajadores.post("", status_code=status.HTTP_201_CREATED, summary="Crear trabajador")
def crear_trabajador(datos: TrabajadorCrear, admin: SoloAdmin, db: DB) -> dict:
    return servicesTrabajador.crear(db, admin, datos.model_dump())


@trabajadores.get("/{idtrabajador}", summary="Ver trabajador")
def ver_trabajador(idtrabajador: int, _: SoloAdmin, db: DB) -> dict:
    return servicesTrabajador.obtener(db, idtrabajador)


@trabajadores.put("/{idtrabajador}", summary="Actualizar trabajador")
def actualizar_trabajador(idtrabajador: int, datos: TrabajadorActualizar, admin: SoloAdmin, db: DB) -> dict:
    return servicesTrabajador.actualizar(db, admin, idtrabajador, datos.model_dump())


@trabajadores.delete("/{idtrabajador}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar (lógico)")
def eliminar_trabajador(idtrabajador: int, admin: SoloAdmin, db: DB) -> None:
    servicesTrabajador.eliminar(db, admin, idtrabajador)


# ------------------------------------------------------------------- clientes
clientes = APIRouter(prefix="/clientes", tags=["Clientes"])


@clientes.get("", summary="Buscar clientes por nombre, documento o email (paginado)")
def listar_clientes(_: UsuarioActual, db: DB, buscar: Buscar = None, estado: EstadoQ = None,
                    page: Pagina = 1, page_size: Tamano = 20,
                    ordenar: Literal["nombre", "identification", "email", "creado_en", "estado"] = "nombre",
                    desc: bool = False) -> dict:
    return servicesCliente.listar(db, buscar, estado, page, page_size, ordenar, desc)


@clientes.post("", status_code=status.HTTP_201_CREATED, summary="Crear cliente")
def crear_cliente(datos: ClienteIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesCliente.crear(db, usuario, datos.model_dump())


@clientes.get("/{idcliente}", summary="Ver cliente")
def ver_cliente(idcliente: int, _: UsuarioActual, db: DB) -> dict:
    return servicesCliente.obtener(db, idcliente)


@clientes.put("/{idcliente}", summary="Actualizar cliente")
def actualizar_cliente(idcliente: int, datos: ClienteIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesCliente.actualizar(db, usuario, idcliente, datos.model_dump())


@clientes.delete("/{idcliente}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar cliente (lógico)")
def eliminar_cliente(idcliente: int, usuario: UsuarioActual, db: DB) -> None:
    servicesCliente.eliminar(db, usuario, idcliente)


# ------------------------------------------------------------------ productos
productos = APIRouter(prefix="/productos", tags=["Productos"])


@productos.get("", summary="Buscar productos (paginado, con alerta de stock bajo)")
def listar_productos(_: UsuarioActual, db: DB, buscar: Buscar = None, estado: EstadoQ = None,
                     stock_bajo: bool = False, page: Pagina = 1, page_size: Tamano = 20,
                     ordenar: Literal["nombre", "code_reference", "precio_unitario", "stock", "tax_rate",
                                      "estado"] = "nombre",
                     desc: bool = False) -> dict:
    return servicesProducto.listar(db, buscar, estado, stock_bajo, page, page_size, ordenar, desc)


@productos.get("/stock-bajo", summary="Productos con stock disponible ≤ stock mínimo")
def stock_bajo(_: UsuarioActual, db: DB, page: Pagina = 1, page_size: Tamano = 50) -> dict:
    return servicesProducto.listar(db, None, "ACTIVO", True, page, page_size)


@productos.post("", status_code=status.HTTP_201_CREATED, summary="Crear producto")
def crear_producto(datos: ProductoIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesProducto.crear(db, usuario, datos.model_dump())


@productos.get("/{idproducto}", summary="Ver producto")
def ver_producto(idproducto: int, _: UsuarioActual, db: DB) -> dict:
    return servicesProducto.obtener(db, idproducto)


@productos.put("/{idproducto}", summary="Actualizar producto (el stock se cambia con /stock)")
def actualizar_producto(idproducto: int, datos: ProductoIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesProducto.actualizar(db, usuario, idproducto, datos.model_dump())


@productos.post("/{idproducto}/stock", summary="Ajustar stock con motivo (auditado)")
def ajustar_stock(idproducto: int, datos: AjusteStockIn, usuario: UsuarioActual, db: DB) -> dict:
    return servicesProducto.ajustar_stock(db, usuario, idproducto, datos.delta, datos.motivo)


@productos.delete("/{idproducto}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar producto (lógico)")
def eliminar_producto(idproducto: int, usuario: UsuarioActual, db: DB) -> None:
    servicesProducto.eliminar(db, usuario, idproducto)
