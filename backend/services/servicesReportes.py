import csv
import io
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import ValidacionError
from backend.core.utilidades import ZONA_COLOMBIA, a_utc
from backend.crudDataBase import CRUDreportes


def rango_utc(desde: date, hasta: date) -> tuple[datetime, datetime]:
    """Convierte días calendario de Colombia a un rango UTC [desde, hasta+1día)."""
    if hasta < desde:
        raise ValidacionError("'hasta' no puede ser anterior a 'desde'.")
    if (hasta - desde).days > 366:
        raise ValidacionError("El rango máximo es de 366 días.")
    inicio = datetime(desde.year, desde.month, desde.day, tzinfo=ZONA_COLOMBIA)
    fin = datetime(hasta.year, hasta.month, hasta.day, tzinfo=ZONA_COLOMBIA) + timedelta(days=1)
    return a_utc(inicio), a_utc(fin)


def dashboard(db: Session) -> dict[str, Any]:
    hoy = datetime.now(ZONA_COLOMBIA).date()
    dia = rango_utc(hoy, hoy)
    mes = rango_utc(hoy.replace(day=1), hoy)
    ultimos_30 = rango_utc(hoy - timedelta(days=29), hoy)
    with db.begin():
        return {
            "fecha": hoy,
            "ventas_hoy": CRUDreportes.totales_ventas(db, *dia),
            "ventas_mes": CRUDreportes.totales_ventas(db, *mes),
            "por_metodo_mes": CRUDreportes.totales_por_metodo(db, *mes),
            "ventas_por_dia": CRUDreportes.ventas_por_dia(db, *ultimos_30),
            "facturas_mes": CRUDreportes.facturas_por_estado(db, *mes),
            "mas_vendidos_mes": CRUDreportes.productos_mas_vendidos(db, *mes),
            "stock_bajo": CRUDreportes.productos_stock_bajo(db),
            "facturas_fallidas": CRUDreportes.facturas_fallidas(db),
        }


def resumen(db: Session, desde: date, hasta: date) -> dict[str, Any]:
    """Totales de ventas y facturas por rango de fechas (días de Colombia)."""
    inicio, fin = rango_utc(desde, hasta)
    with db.begin():
        return {
            "desde": desde,
            "hasta": hasta,
            "ventas": CRUDreportes.totales_ventas(db, inicio, fin),
            "por_metodo": CRUDreportes.totales_por_metodo(db, inicio, fin),
            "por_dia": CRUDreportes.ventas_por_dia(db, inicio, fin),
            "facturas": CRUDreportes.facturas_por_estado(db, inicio, fin),
            "mas_vendidos": CRUDreportes.productos_mas_vendidos(db, inicio, fin),
        }


def csv_reporte(db: Session, tipo: str, desde: date, hasta: date) -> str:
    inicio, fin = rango_utc(desde, hasta)
    with db.begin():
        filas = CRUDreportes.reporte_ventas(db, inicio, fin) if tipo == "ventas" \
            else CRUDreportes.reporte_facturas(db, inicio, fin)
    salida = io.StringIO()
    # BOM + ';' para que Excel en español lo abra con columnas y tildes correctas.
    salida.write("﻿")
    if filas:
        escritor = csv.DictWriter(salida, fieldnames=list(filas[0].keys()), delimiter=";")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow({k: _celda(v) for k, v in fila.items()})
    return salida.getvalue()


def _celda(valor: Any) -> Any:
    # Evita inyección de fórmulas al abrir el CSV en Excel.
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@"):
        return "'" + valor
    return valor
