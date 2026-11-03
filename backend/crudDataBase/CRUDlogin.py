
from sqlalchemy.orm import Session
from backend.crudDataBase.configDataBase.dataBase import get_db
from sqlalchemy import text


# agregar cliente de base de datos MySQL
def peticion_crear_cuenta_usuario_cliente(datos_dict: dict) -> bool:
    db: Session = next(get_db())
    try:
        query = text("""
            INSERT INTO usuario (
                tipo_persona, tipo_documento, numero_documeto_nit, nombre,
                correo, direccion, municipio_departamento, telefono_celular,
                rol, contraseña
            )
            VALUES (
                :tipo_persona, :tipo_documento, :numero_documeto_nit, :nombre,
                :correo, :direccion, :municipio_departamento, :telefono_celular,
                :rol, :contraseña
            )
        """)
        db.execute(query, datos_dict)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()



# modificar cliente de base de datos MySQL
def peticion_modificar_cuenta_usuario_cliente(datos_dict: dict) -> str:
    # enciar los datos a la base de datos Tabla "usuarios" para modificar una cuenta de usuario cliente
    
    db: Session = next(get_db())
    try:
        query = """
        UPDATE usuarios
        SET tipo_persona = %s, tipo_documento = %s, numero_documeto_nit = %s, nombre = %s, correo = %s, direccion = %s, municipio_departamento = %s, telefono_celular = %s
        WHERE rol = 'cliente' AND correo = %s
        """
        
        db.execute(query, datos_dict)
        db.commit()
        return True
    
    except Exception as err:
        
        print(f"❌ Error detallado en la base de datos: {err}")
        db.rollback()
        return {
            "estado": False,
            "mensaje": f"Error al modificar la cuenta de usuario cliente: {str(err)}"
        }


def peticion_crear_cuenta_usuario_Trabajador(datos_dict: dict, passwordNEW: str) -> bool:
    db: Session = next(get_db())
    try:
        query = text("""
            INSERT INTO usuario (
                tipo_persona, tipo_documento, numero_documeto_nit, nombre,
                correo, direccion, municipio_departamento, telefono_celular,
                rol, correo_trabajdor, contraseña
            )
            VALUES (
                :tipo_persona, :tipo_documento, :numero_documeto_nit, :nombre,
                :correo, :direccion, :municipio_departamento, :telefono_celular,
                :rol, :correo_trabajdor, :contraseña
            )
        """)
        parametros = {
            **datos_dict,
            "correo_trabajdor": datos_dict["correotrabajador"],
            "contraseña": passwordNEW,
        }
        db.execute(query, parametros)
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# buscar cliente de base de datos MySQL
def peticion_buscar_cuenta_usuario_cliente(
    dato_busqueda: dict,
    *,
    rol: str | None = "cliente",
) -> dict | None:
    db: Session = next(get_db())
    try:
        # Extraemos los valores del diccionario
        nit = dato_busqueda.get("numero_documeto_nit")
        correo = dato_busqueda.get("correo")
        telefono = dato_busqueda.get("telefono_celular")
        correo_trabajador = dato_busqueda.get("correo_trabajador")
        
        # Validamos que al menos envíen uno de los tres datos para buscar
        if not nit and not correo and not telefono and not correo_trabajador:
            return None
        
        # Consulta SQL flexible: evalúa solo los campos que vengan con datos (1, 2 o los 3)
        query = text("""
        SELECT * FROM usuario
        WHERE (:rol IS NULL OR rol = :rol)
          AND (
              (:nit IS NOT NULL AND numero_documeto_nit = :nit) OR 
              (:correo IS NOT NULL AND correo = :correo) OR 
              (:telefono IS NOT NULL AND telefono_celular = :telefono) OR
              (:correo_trabajador IS NOT NULL AND correo_trabajdor = :correo_trabajador)
          )
        """)
        
        # Ejecutamos pasando los parámetros
        result = db.execute(query, {
            "nit": nit,
            "correo": correo,
            "telefono": telefono,
            "correo_trabajador": correo_trabajador,
            "rol": rol,
        }).mappings().fetchone()
        
        if result:
            return dict(result)
        return None
    finally:
        db.close()

# eliminar cliente de base de datos MySQL
def peticion_eliminar_cuenta_usuario_cliente(dato_busqueda: dict):
    db: Session = next(get_db())
    try:
        # Extraemos los valores del diccionario
        nit = dato_busqueda.get("numero_documeto_nit")
        correo = dato_busqueda.get("correo")
        telefono = dato_busqueda.get("telefono_celular")
        
        # Validamos que al menos envíen uno de los tres datos para buscar
        if not nit and not correo and not telefono:
            return {
                "estado": False,
                "mensaje": "Debes proporcionar al menos un criterio de búsqueda (documento, correo o teléfono) para eliminar."
            }
        
        # Consulta SQL flexible: evalúa solo los campos que vengan con datos (1, 2 o los 3)
        query = text("""
        DELETE FROM usuario
        WHERE rol = 'cliente' 
          AND (
              (:nit IS NOT NULL AND numero_documeto_nit = :nit) OR 
              (:correo IS NOT NULL AND correo = :correo) OR 
              (:telefono IS NOT NULL AND telefono_celular = :telefono)
          )
        """)
        
        # Ejecutamos pasando los parámetros
        result = db.execute(query, {
            "nit": nit,
            "correo": correo,
            "telefono": telefono
        })
        
        db.commit()
        
        if result.rowcount > 0:
            return {
                "estado": True,
                "mensaje": "Cuenta de usuario cliente eliminada exitosamente."
            }
        else:
            return {
                "estado": False,
                "mensaje": "No se encontró ninguna cuenta de usuario cliente con los datos proporcionados para eliminar."
            }
    
    except Exception as err:
        print(f"❌ Error detallado en la base de datos: {err}")
        db.rollback()
        return {
            "estado": False,
            "mensaje": f"Error al eliminar la cuenta de usuario cliente: {str(err)}"
        }        
        
        
