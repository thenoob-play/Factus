"""Punto de entrada de la API de Factu."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from starlette.concurrency import run_in_threadpool

from backend.core.errores import registrar_manejadores
from backend.crudDataBase.configDataBase.conf import settings
from backend.crudDataBase.configDataBase.dataBase import SessionLocal
from backend.models.auth import router as auth_router
from backend.models.facturas import catalogos_router, facturas, reportes
from backend.models.gestion import clientes, productos, trabajadores
from backend.models.ventas import cajas, pagos, ventas
from backend.services.servicesPago import expirar_pagos_vencidos

logging.basicConfig(level=settings.LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("factu")


def _verificar_configuracion() -> None:
    problemas = []
    if len(settings.JWT_SECRET) < 32:
        problemas.append("JWT_SECRET (mínimo 32 caracteres)")
    if len(settings.PAYMENT_SIGNING_SECRET) < 32:
        problemas.append("PAYMENT_SIGNING_SECRET (mínimo 32 caracteres)")
    if problemas:
        mensaje = "Configuración insegura o incompleta: " + ", ".join(problemas)
        if settings.APP_ENV == "production":
            raise RuntimeError(mensaje)
        logger.warning("%s. Los endpoints que los usan responderán 500 hasta configurarlos.", mensaje)


MIGRACIONES_DIR = Path(__file__).resolve().parent / "backend" / "crudDataBase" / "migraciones"


def _migraciones_pendientes() -> list[str]:
    """Versiones de migración que aún no se aplicaron a la base configurada."""
    esperadas = sorted(p.stem for p in MIGRACIONES_DIR.glob("*.sql"))
    try:
        with SessionLocal() as db:
            aplicadas = {fila[0] for fila in db.execute(text("SELECT version FROM schema_migrations"))}
    except ProgrammingError:  # la tabla schema_migrations no existe: nunca se migró
        aplicadas = set()
    return [v for v in esperadas if v not in aplicadas]


def _ejecutar_expiracion() -> dict[str, int]:
    with SessionLocal() as db:
        return expirar_pagos_vencidos(db)


async def _job_expiracion() -> None:
    """Expira pagos vencidos y libera el stock reservado, periódicamente."""
    while True:
        try:
            resultado = await run_in_threadpool(_ejecutar_expiracion)
            if any(resultado.values()):
                logger.info("Job de expiración: %s", resultado)
        except Exception:
            logger.exception("Fallo en el job de expiración de pagos.")
        await asyncio.sleep(settings.EXPIRATION_JOB_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _verificar_configuracion()
    pendientes = await run_in_threadpool(_migraciones_pendientes)
    if pendientes:
        logger.error(
            "La base '%s' tiene migraciones pendientes: %s. Haz un respaldo y ejecuta: "
            "python -m scripts.migrar  (el job de expiración no se iniciará hasta entonces).",
            settings.DB_NAME, ", ".join(pendientes),
        )
    iniciar_job = settings.EXPIRATION_JOB_ENABLED and not pendientes
    tarea = asyncio.create_task(_job_expiracion()) if iniciar_job else None
    yield
    if tarea:
        tarea.cancel()
        with suppress(asyncio.CancelledError):
            await tarea


app = FastAPI(
    title="API Factu",
    description=(
        "Clientes, trabajadores, productos, ventas con pagos verificables (efectivo, transferencia, "
        "tarjeta) y facturación electrónica DIAN a través de Factus.\n\n"
        "Autentícate en `POST /auth/login` y usa el token con el botón **Authorize**."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
registrar_manejadores(app)

for router in (auth_router, trabajadores, clientes, productos, ventas, pagos, cajas, facturas,
               catalogos_router, reportes):
    app.include_router(router)


FRONTEND_DIR = Path(__file__).resolve().parent / "frontend"
if FRONTEND_DIR.is_dir():
    # Interfaz web servida desde el mismo origen que la API (sin CORS).
    app.mount("/ui", StaticFiles(directory=FRONTEND_DIR, html=True), name="ui")


@app.get("/", tags=["Sistema"], summary="Información de la API")
def read_root() -> dict[str, str]:
    return {"message": "API Factu está activa", "documentation": "/docs", "interfaz": "/ui/"}


@app.get("/health", tags=["Sistema"], summary="Estado del servicio y de la base de datos")
def health_check() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
