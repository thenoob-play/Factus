"""Errores de dominio y manejadores que producen un formato de respuesta uniforme.

Toda respuesta de error tiene la forma:
    {"error": {"codigo": "STOCK_INSUFICIENTE", "mensaje": "...", "detalles": ...}}
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    codigo = "ERROR"

    def __init__(self, mensaje: str, *, codigo: str | None = None, detalles: Any = None,
                 status_code: int | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles
        if codigo:
            self.codigo = codigo
        if status_code:
            self.status_code = status_code


class ValidacionError(AppError):
    status_code = 400
    codigo = "VALIDACION"


class NoAutenticadoError(AppError):
    status_code = 401
    codigo = "NO_AUTENTICADO"


class ProhibidoError(AppError):
    status_code = 403
    codigo = "PROHIBIDO"


class NoEncontradoError(AppError):
    status_code = 404
    codigo = "NO_ENCONTRADO"


class ConflictoError(AppError):
    status_code = 409
    codigo = "CONFLICTO"


class DemasiadasPeticionesError(AppError):
    status_code = 429
    codigo = "DEMASIADAS_PETICIONES"


class ServicioExternoError(AppError):
    status_code = 502
    codigo = "SERVICIO_EXTERNO"


class ConfiguracionError(AppError):
    status_code = 500
    codigo = "CONFIGURACION"


def _respuesta(status: int, codigo: str, mensaje: str, detalles: Any = None,
               headers: dict[str, str] | None = None) -> JSONResponse:
    cuerpo: dict[str, Any] = {"error": {"codigo": codigo, "mensaje": mensaje}}
    if detalles is not None:
        cuerpo["error"]["detalles"] = detalles
    return JSONResponse(status_code=status, content=cuerpo, headers=headers)


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return _respuesta(exc.status_code, exc.codigo, exc.mensaje, exc.detalles, headers)

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        detalles = [
            {
                "campo": ".".join(str(p) for p in err.get("loc", []) if p != "body"),
                "mensaje": err.get("msg"),
                "tipo": err.get("type"),
            }
            for err in exc.errors()
        ]
        return _respuesta(422, "ENTRADA_INVALIDA", "La petición tiene datos inválidos.", detalles)

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException) -> JSONResponse:
        mensaje = exc.detail if isinstance(exc.detail, str) else "Error en la petición."
        detalles = None if isinstance(exc.detail, str) else exc.detail
        return _respuesta(exc.status_code, f"HTTP_{exc.status_code}", mensaje, detalles,
                          getattr(exc, "headers", None))

    @app.exception_handler(IntegrityError)
    async def _integridad(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Violación de integridad: %s", exc.orig)
        return _respuesta(409, "CONFLICTO_DATOS",
                          "La operación viola una restricción de datos (duplicado o referencia inválida).")

    @app.exception_handler(OperationalError)
    async def _operacional(_: Request, exc: OperationalError) -> JSONResponse:
        mensaje = str(exc.orig)
        if "PAGO_INMUTABLE" in mensaje or "PAGO_FINALIZADO" in mensaje:
            return _respuesta(409, "PAGO_INMUTABLE", "El pago no se puede modificar.")
        logger.exception("Error operacional de base de datos.")
        return _respuesta(503, "BASE_DE_DATOS", "La base de datos no está disponible.")

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado.")
        return _respuesta(500, "ERROR_INTERNO", "Ocurrió un error interno.")
