from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def peticion_buscar_usuario_para_compra(
    db: Session,
    idusuario: int,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT idusuario, tipo_persona, tipo_documento, numero_documeto_nit,
               nombre, correo, direccion, municipio_departamento,
               telefono_celular, rol
        FROM usuario
        WHERE idusuario = :idusuario AND rol = 'cliente'
        FOR UPDATE
        """
    )
    result = db.execute(query, {"idusuario": idusuario}).mappings().first()
    return dict(result) if result else None


def peticion_buscar_producto_para_compra(
    db: Session,
    idproducto: int,
) -> dict[str, Any] | None:
    query = text(
        """
        SELECT idproductos, codigo_interno, codigo_UNSPSC, nombre, Uni_medida,
               cantidad, precio_unitario, descuento, tarifa_iva
        FROM productos
        WHERE idproductos = :idproducto
        FOR UPDATE
        """
    )
    result = db.execute(query, {"idproducto": idproducto}).mappings().first()
    return dict(result) if result else None


def peticion_crear_compra(
    db: Session,
    idusuario: int,
) -> int:
    result = db.execute(
        text(
            """
            INSERT INTO compra (idusuario)
            VALUES (:idusuario)
            """
        ),
        {"idusuario": idusuario},
    )
    return int(result.lastrowid)


def peticion_crear_detalles_compra(
    db: Session,
    idcompra: int,
    detalles: list[dict[str, Any]],
) -> None:
    db.execute(
        text(
            """
            INSERT INTO compra_detalle (
                idcompra, idproducto, cantidad, precio_unitario, subtotal
            )
            VALUES (
                :idcompra, :idproducto, :cantidad, :precio_unitario, :subtotal
            )
            """
        ),
        [
            {
                "idcompra": idcompra,
                "idproducto": detalle["idproducto"],
                "cantidad": detalle["cantidad"],
                "precio_unitario": detalle["precio_unitario"],
                "subtotal": detalle["subtotal"],
            }
            for detalle in detalles
        ],
    )


def peticion_crear_factura(
    db: Session,
    factura: dict[str, Any],
) -> int:
    result = db.execute(
        text(
            """
            INSERT INTO factura (
                idcompra, prefijo, numero_factura, cufe,
                total_bruto, total_descuentos, total_iva, total_neto, qr_dian
            )
            VALUES (
                :idcompra, :prefijo, :numero_factura, :cufe,
                :total_bruto, :total_descuentos, :total_iva, :total_neto, :qr_dian
            )
            """
        ),
        factura,
    )
    return int(result.lastrowid)


def peticion_descontar_stock(
    db: Session,
    idproducto: int,
    cantidad: int,
) -> None:
    result = db.execute(
        text(
            """
            UPDATE productos
            SET cantidad = cantidad - :cantidad
            WHERE idproductos = :idproducto AND cantidad >= :cantidad
            """
        ),
        {"idproducto": idproducto, "cantidad": cantidad},
    )
    if result.rowcount != 1:
        raise RuntimeError(
            f"No fue posible descontar el stock del producto {idproducto}."
        )
