from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from backend.core.rate_limit import ip_cliente
from backend.core.seguridad import UsuarioActual
from backend.crudDataBase.configDataBase.dataBase import get_db
from backend.services import servicesAuth
from backend.shemas.esquemas import CambiarPasswordIn, LoginIn

router = APIRouter(prefix="/auth", tags=["Autenticación"])
DB = Annotated[Session, Depends(get_db)]


@router.post("/login", summary="Iniciar sesión (devuelve un JWT)")
def login(datos: LoginIn, request: Request, db: DB) -> dict:
    return servicesAuth.login(db, datos.email, datos.password, ip_cliente(request))


@router.get("/me", summary="Usuario autenticado")
def yo(usuario: UsuarioActual) -> dict:
    return {"idtrabajador": usuario.idtrabajador, "nombre": usuario.nombre, "email": usuario.email,
            "rol": usuario.rol}


@router.post("/cambiar-password", status_code=status.HTTP_204_NO_CONTENT, summary="Cambiar mi contraseña")
def cambiar_password(datos: CambiarPasswordIn, usuario: UsuarioActual, db: DB) -> None:
    servicesAuth.cambiar_password(db, usuario, datos.password_actual, datos.password_nueva)
