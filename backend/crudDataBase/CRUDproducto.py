
from sqlalchemy.orm import Session
from backend.crudDataBase.configDataBase.dataBase import get_db
from sqlalchemy import text


# agregar producto de base de datos MySQL
from sqlalchemy.orm import Session
from sqlalchemy import text

def peticion_crear_producto(datos_dict: dict) -> bool:
    db: Session = next(get_db())
    
    try:
        query = text("""
            INSERT INTO productos (
                idcategoria, 
                codigo_interno, 
                codigo_UNSPSC, 
                nombre, 
                descripcion, 
                Uni_medida, 
                cantidad, 
                precio_unitario, 
                descuento, 
                tarifa_iva, 
                URL_imagen
            )
            VALUES (
                :idcategoria, 
                :codigo_interno, 
                :codigo_UNSPSC, 
                :nombre, 
                :descripcion, 
                :Uni_medida, 
                :cantidad, 
                :precio_unitario, 
                :descuento, 
                :tarifa_iva, 
                :URL_imagen
            )
        """)
        
        db.execute(query, datos_dict)
        db.commit()
        return True
    
    except Exception as e:
        db.rollback()
        # Opcional: imprime o maneja el error para depurar mejor en consola
        print(f"Error al insertar producto: {e}")
        raise
    

def buscar_producto_por_id(idproducto: int) -> dict:
    db: Session = next(get_db())
    
    try:
        query = text("SELECT * FROM productos WHERE idproducto = :idproducto")
        result = db.execute(query, {"idproducto": idproducto}).fetchone()
        
        if result:
            return dict(result)
        else:
            return None
    
    except Exception as e:
        print(f"Error al buscar producto: {e}")
        raise    