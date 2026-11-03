## router de login

from fastapi import APIRouter, HTTPException, status

# Importamos las clases de los esquemas
from backend.shemas.usuario import UsuarioClienteCreate , loginUsarioCreate, UsuarioTrabajadorCreate  
  
# Importamos las funciones directamente del servicio

from backend.services.servicesLogin import crear_cuenta_usuario_cliente , login_usuario as autenticar_usuario , \
    crear_cuenta_usuario_Trabajador
router = APIRouter()

@router.post("/CrearCuentaCliente", status_code=status.HTTP_201_CREATED, response_model=dict)
async def crear_cuenta(usuario: UsuarioClienteCreate):   
    datos_dict = usuario.model_dump()

    try:
        enviar_datos = crear_cuenta_usuario_cliente(datos_dict)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return {"message": enviar_datos}


@router.post("/CrearCuentaTrabajador", status_code=status.HTTP_201_CREATED, response_model=dict)
async def crear_cuenta(usuario: UsuarioTrabajadorCreate):   
    datos_dict = usuario.model_dump()

    try:
        enviar_datos = crear_cuenta_usuario_Trabajador(datos_dict)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return {"message": enviar_datos}


@router.post("/Login", status_code=status.HTTP_200_OK, response_model=dict)
async def iniciar_sesion(usuario: loginUsarioCreate):
    datos_dict = usuario.model_dump()

    try:
        enviar_datos = autenticar_usuario(datos_dict)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error

    return {"message": enviar_datos}