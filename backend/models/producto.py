
from fastapi import APIRouter, HTTPException, status

# Importamos el esquema usado por esta ruta.
from backend.shemas.producto import ProductoCreate
  
# Importamos las funciones directamente del servicio

from backend.services.servicesProducto import servicio_crear_producto 
router = APIRouter()

@router.post("/CrearProducto", status_code=status.HTTP_201_CREATED, response_model=dict)
async def crear_producto(usuario: ProductoCreate):   
    datos_dict = usuario.model_dump()

    try:
        enviar_datos = servicio_crear_producto (datos_dict)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return {"message": enviar_datos}