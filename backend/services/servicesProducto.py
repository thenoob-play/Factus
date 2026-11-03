from backend.Extend.validarProductos import validar_producto
from backend.crudDataBase.CRUDproducto import peticion_crear_producto

def servicio_crear_producto(datos_dict: dict) -> str:
    # 1. Validar (si hay un error, validar_producto ya hace raise ValueError por sí misma)
    validar_producto(datos_dict)
    
    try:
        # 2. Intentar guardar en la base de datos
        peticion_crear_producto(datos_dict)
        return "Producto creado exitosamente."
    except Exception as e:
        # Captura cualquier error de base de datos o inesperado
        raise ValueError(f"Error al crear el producto en la base de datos: {str(e)}")