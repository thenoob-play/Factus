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


def peticion_buscar_compra_idempotente(
    db: Session,
    idusuario: int,
    idempotency_key: str,
) -> dict[str, Any] | None:
    result = db.execute(
        text(
            """
            SELECT idcompra, request_hash, factus_reference_code, factus_source,
                   factus_payload, factus_totales, factus_response, factus_estado
            FROM compra
            WHERE idusuario = :idusuario AND idempotency_key = :idempotency_key
            FOR UPDATE
            """
        ),
        {"idusuario": idusuario, "idempotency_key": idempotency_key},
    ).mappings().first()
    return dict(result) if result else None


def peticion_buscar_compra_por_id(
    db: Session,
    idcompra: int,
) -> dict[str, Any] | None:
    result = db.execute(
        text(
            """
            SELECT idcompra, factus_reference_code, factus_source,
                   factus_payload, factus_totales, factus_response, factus_estado
            FROM compra
            WHERE idcompra = :idcompra
            FOR UPDATE
            """
        ),
        {"idcompra": idcompra},
    ).mappings().first()
    return dict(result) if result else None


def peticion_crear_compra(
    db: Session,
    idusuario: int,
    idempotency_key: str,
    request_hash: str,
    reference_code: str,
    factus_source: str,
) -> int:
    result = db.execute(
        text(
            """
            INSERT INTO compra (
                idusuario, idempotency_key, request_hash, factus_reference_code,
                factus_source, factus_estado
            )
            VALUES (
                :idusuario, :idempotency_key, :request_hash, :reference_code,
                CAST(:factus_source AS JSON), 'pendiente'
            )
            """
        ),
        {
            "idusuario": idusuario,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "reference_code": reference_code,
            "factus_source": factus_source,
        },
    )
    return int(result.lastrowid)


def peticion_guardar_payload_factus(
    db: Session,
    idcompra: int,
    payload: str,
    totales: str,
) -> None:
    db.execute(
        text(
            """
            UPDATE compra
            SET factus_payload = CAST(:payload AS JSON),
                factus_totales = CAST(:totales AS JSON),
                factus_source = NULL
            WHERE idcompra = :idcompra
            """
        ),
        {"idcompra": idcompra, "payload": payload, "totales": totales},
    )


def peticion_actualizar_estado_factus(
    db: Session,
    idcompra: int,
    estado: str,
) -> None:
    db.execute(
        text(
            """
            UPDATE compra
            SET factus_estado = :estado
            WHERE idcompra = :idcompra
            """
        ),
        {"idcompra": idcompra, "estado": estado},
    )


def peticion_guardar_respuesta_factus(
    db: Session,
    idcompra: int,
    respuesta: str,
) -> None:
    db.execute(
        text(
            """
            UPDATE compra
            SET factus_response = CAST(:respuesta AS JSON),
                factus_estado = 'emitida'
            WHERE idcompra = :idcompra
            """
        ),
        {"idcompra": idcompra, "respuesta": respuesta},
    )


def peticion_buscar_factura_por_compra(
    db: Session,
    idcompra: int,
) -> int | None:
    result = db.execute(
        text("SELECT idfactura FROM factura WHERE idcompra = :idcompra"),
        {"idcompra": idcompra},
    ).scalar_one_or_none()
    return int(result) if result is not None else None


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
