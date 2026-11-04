"""Datos de prueba: un ADMIN, un TRABAJADOR, clientes y productos de ejemplo.

Uso:
    python -m scripts.seed --admin-email admin@miempresa.co --admin-password "Clave-Larga-2026"
    python -m scripts.seed --solo-admin --admin-email ... --admin-password ...

Es idempotente: si un registro ya existe (mismo email, documento o code_reference), lo omite.
Las contraseñas no se guardan en el código: se pasan por argumento o por las variables
SEED_ADMIN_EMAIL / SEED_ADMIN_PASSWORD / SEED_TRABAJADOR_PASSWORD.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from backend.core.errores import AppError  # noqa: E402
from backend.core.seguridad import Usuario, hash_password  # noqa: E402
from backend.crudDataBase.configDataBase.dataBase import SessionLocal  # noqa: E402
from backend.services import servicesCliente, servicesProducto, servicesTrabajador  # noqa: E402

CLIENTES = [
    {"identification_document_code": "13", "identification": "1002938485", "legal_organization_code": "2",
     "names": "Julián Benavides", "email": "cliente.natural@example.com", "phone": "3001234567",
     "address": "Calle 10 # 20-30", "municipality_code": None},
    {"identification_document_code": "31", "identification": "900373115", "legal_organization_code": "1",
     "company": "Distribuciones Ejemplo SAS", "trade_name": "Distriejemplo", "tribute_code": "01",
     "email": "facturacion@example.com", "phone": "6015550000", "address": "Carrera 7 # 71-21"},
    {"identification_document_code": "22", "identification": "E1234567", "legal_organization_code": "2",
     "names": "María Fernanda López", "email": "maria.lopez@example.com", "address": "Avenida 68 # 12-40"},
]

PRODUCTOS = [
    {"code_reference": "LECHE-1L", "nombre": "Leche entera 1 L", "precio_unitario": "4500.00", "stock": 50,
     "stock_minimo": 10, "tax_rate": 5, "unit_measure_code": "94"},
    {"code_reference": "CAFE-500G", "nombre": "Café molido 500 g", "precio_unitario": "18900.00", "stock": 30,
     "stock_minimo": 5, "tax_rate": 5, "unit_measure_code": "94"},
    {"code_reference": "PORT-14", "nombre": "Portátil 14 pulgadas", "precio_unitario": "2499000.00", "stock": 4,
     "stock_minimo": 5, "tax_rate": 19, "standard_code": "001", "codigo_unspsc": "43211503"},
    {"code_reference": "HUEVOS-30", "nombre": "Huevos AA x30", "precio_unitario": "16500.00", "stock": 40,
     "stock_minimo": 8, "tax_rate": 0, "is_excluded": True},
    {"code_reference": "DETERG-3K", "nombre": "Detergente 3 kg", "precio_unitario": "32000.00", "stock": 20,
     "stock_minimo": 4, "tax_rate": 19, "discount_rate": "10.00"},
]


def _crear(etiqueta: str, funcion, *args) -> None:
    try:
        funcion(*args)
        print(f"  + {etiqueta}")
    except AppError as error:
        print(f"  · {etiqueta}: {error.mensaje}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--admin-email", default=os.getenv("SEED_ADMIN_EMAIL"))
    parser.add_argument("--admin-password", default=os.getenv("SEED_ADMIN_PASSWORD"))
    parser.add_argument("--trabajador-password", default=os.getenv("SEED_TRABAJADOR_PASSWORD"))
    parser.add_argument("--solo-admin", action="store_true")
    args = parser.parse_args()
    if not args.admin_email or not args.admin_password or len(args.admin_password) < 10:
        parser.error("Indica --admin-email y --admin-password (mínimo 10 caracteres).")

    with SessionLocal() as db:
        with db.begin():
            fila = db.execute(text("SELECT idtrabajador, nombre, email, rol FROM trabajador WHERE email = :e"),
                              {"e": args.admin_email.lower()}).mappings().first()
            if not fila:
                db.execute(
                    text("INSERT INTO trabajador (nombre, documento, email, rol, password_hash) "
                         "VALUES ('Administrador', '1000000000', :e, 'ADMIN', :h)"),
                    {"e": args.admin_email.lower(), "h": hash_password(args.admin_password)},
                )
                fila = db.execute(text("SELECT idtrabajador, nombre, email, rol FROM trabajador WHERE email = :e"),
                                  {"e": args.admin_email.lower()}).mappings().first()
                print(f"  + ADMIN {args.admin_email}")
            else:
                print(f"  · ADMIN {args.admin_email} ya existía")
        admin = Usuario(**fila)
        if args.solo_admin:
            return

        if args.trabajador_password:
            _crear("TRABAJADOR cajero@example.com", servicesTrabajador.crear, db, admin, {
                "nombre": "Cajero de Prueba", "tipo_documento": "13", "documento": "1020304050",
                "email": "cajero@example.com", "telefono": "3110000000", "rol": "TRABAJADOR",
                "estado": "ACTIVO", "password": args.trabajador_password})
        for cliente in CLIENTES:
            datos = {"tribute_code": "ZZ", "estado": "ACTIVO", "dv": None, "names": None, "company": None,
                     "trade_name": None, "phone": None, "municipality_code": None, **cliente}
            _crear(f"cliente {cliente['identification']}", servicesCliente.crear, db, admin, datos)
        for producto in PRODUCTOS:
            datos = {"descripcion": None, "is_excluded": False, "tax_code": "01", "unit_measure_code": "94",
                     "standard_code": "999", "codigo_unspsc": None, "discount_rate": "0", "estado": "ACTIVO",
                     "idcategoria": None, "url_imagen": None, **producto}
            _crear(f"producto {producto['code_reference']}", servicesProducto.crear, db, admin, datos)


if __name__ == "__main__":
    main()
