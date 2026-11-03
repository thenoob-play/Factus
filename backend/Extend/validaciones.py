
import bcrypt

from backend.crudDataBase.CRUDlogin import peticion_buscar_cuenta_usuario_cliente

def encriptar_password(password: str) -> str:
    """Toma una contraseña plana y devuelve su hash seguro."""
    # Convertimos la contraseña a bytes y generamos el hash con bcrypt
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verificar_password(password_plana: str, password_hash: str) -> bool:
    """Compara una contraseña escrita por el usuario con el hash guardado en la BD."""
    return bcrypt.checkpw(password_plana.encode('utf-8'), password_hash.encode('utf-8'))

# Validar correo si el correo no termina en @gmail.com o @hotmail.com devolver False
def validar_email(email):
    if email.endswith("@gmail.com") or email.endswith("@hotmail.com") or email.endswith("@outlook.com"):
        return True
    else:
        return False
    
    

def validar_datos_usuario(datos_dict: dict) -> None:
    """
    Valida los datos proporcionados para crear una cuenta de usuario cliente.

    Args:
        datos_dict (dict): Diccionario que contiene los datos del usuario cliente.

    Raises:
        ValueError: Si algún campo es inválido o no cumple con los requisitos.
    """
    tipo_persona = datos_dict.get("tipo_persona")
    tipo_documento = datos_dict.get("tipo_documento")
    numero_documeto_nit = datos_dict.get("numero_documeto_nit")
    nombre = datos_dict.get("nombre")
    correo = datos_dict.get("correo")
    direccion = datos_dict.get("direccion")
    municipio_departamento = datos_dict.get("municipio_departamento")
    telefono_celular = datos_dict.get("telefono_celular")
    

    
    if not all([tipo_persona, tipo_documento, numero_documeto_nit, 
                nombre, correo, direccion, municipio_departamento, telefono_celular]):
        return {
            "estado": False,
            "mensaje": "Todos los campos son obligatorios y deben ser proporcionados."
        }
    if tipo_persona not in ["natural", "juridica"]:
        return {
            "estado": False,
            "mensaje": "El tipo de persona debe ser 'natural' o 'juridica'."
        }    

    if tipo_documento not in ["CC", "NIT", "CE"]:
        return {
            "estado": False,
            "mensaje": "El tipo de documento debe ser 'CC', 'NIT' o 'CE'."
        }

    if len(numero_documeto_nit) < 7:
        return {
            "estado": False,
            "mensaje": "El número de documento o NIT debe tener al menos 7 caracteres."
        }

    if len(nombre) < 15 or len(nombre) > 100 :
        return {
            "estado": False,
            "mensaje": "El nombre debe tener al menos 15 caracteres."
        }
    
    if not validar_email(correo):
        return {
            "estado": False,
            "mensaje": "El correo electrónico debe terminar en @gmail.com, @hotmail.com o @outlook.com."
        }

    
    if len(direccion) < 10 or len(direccion) > 200:
        return {
            "estado": False,
            "mensaje": "La dirección debe tener al menos 10 caracteres y no más de 200."
        }
        
    if len(municipio_departamento) < 5 or len(municipio_departamento) > 100:
        return {
            "estado": False,
            "mensaje": "El municipio o departamento debe tener al menos 5 caracteres y no más de 100."
        }
        
    validar_repeticion = peticion_buscar_cuenta_usuario_cliente(
        {
            "numero_documeto_nit": numero_documeto_nit,
            "correo": correo,
            "telefono_celular": telefono_celular,
            "correo_trabajador": datos_dict.get("correotrabajador"),
        },
        rol=None,
    )
    if validar_repeticion:
        return {
            "estado": False,
            "mensaje": "Ya existe una cuenta con el mismo documento, correo o teléfono celular."
        }
                
    
    
    return {
        "estado": True,
        "mensaje": "Todos los datos son válidos."
    }  # Si todas las validaciones pasan, devolvemos True
