
from backend.Extend.validaciones import validar_datos_usuario ,encriptar_password,\
    verificar_password

from backend.crudDataBase.CRUDlogin import peticion_crear_cuenta_usuario_cliente, \
peticion_buscar_cuenta_usuario_cliente ,\
peticion_crear_cuenta_usuario_Trabajador



# agregar usuario tipo cliente
def crear_cuenta_usuario_cliente(datos_dict: dict) -> str:
    
    
    rol = datos_dict.get("rol")
    
    if rol != "cliente":
        raise ValueError("El rol debe ser 'cliente' para crear una cuenta de usuario cliente.")
    
    validar = validar_datos_usuario(datos_dict)
    if not validar["estado"]:
        raise ValueError(validar["mensaje"])
    
    try:
        datos_dict["contraseña"] = encriptar_password(datos_dict["numero_documeto_nit"])
        peticion_crear_cuenta_usuario_cliente(datos_dict)
        return "Cuenta de usuario cliente creada exitosamente."
    except ValueError as ve:
        raise ValueError(f"Error al crear la cuenta de usuario cliente: {str(ve)}")    


def crear_cuenta_usuario_Trabajador(datos_dict: dict) -> str:
    rol = datos_dict.get("rol")
    
    if rol != "trabajador":
        raise ValueError("El rol debe ser 'trabajador' para crear una cuenta de usuario trabajador.")
    
    validar = validar_datos_usuario(datos_dict)
    if not validar["estado"]:
        raise ValueError(validar["mensaje"])
    
    try:
        passwordNEW = encriptar_password(datos_dict["contraseña"])
        peticion_crear_cuenta_usuario_Trabajador(datos_dict, passwordNEW)
        return "Cuenta de usuario trabajador creada exitosamente."
    except ValueError as ve:
        raise ValueError(f"Error al crear la cuenta de usuario trabajador: {str(ve)}")


    
# login usuario
def login_usuario(datos_dict: dict) -> str:
    identificador = datos_dict.get("correo", "").strip()
    contraseña = datos_dict.get("contraseña", "")

    if not identificador or not contraseña:
        raise ValueError("El identificador y la contraseña son obligatorios.")

    cuenta_cliente = peticion_buscar_cuenta_usuario_cliente(
        {"numero_documeto_nit": identificador},
        rol="cliente",
    )
    if cuenta_cliente and contraseña == identificador:
        return "Bienvenido al sistema, usuario cliente."

    cuenta_trabajador = peticion_buscar_cuenta_usuario_cliente(
        {"correo_trabajador": identificador},
        rol="trabajador",
    )
    if cuenta_trabajador and cuenta_trabajador.get("contraseña"):
        if verificar_password(contraseña, cuenta_trabajador["contraseña"]):
            return "Bienvenido al sistema, usuario trabajador."

    raise ValueError("Credenciales incorrectas.")
