import logging

from fastapi import APIRouter, Header, HTTPException, status
from backend.shemas.compra import CompraCreate
from backend.services.servicesCompra import (
    CompraConflictoError,
    CompraNoEncontradaError,
    servicio_crear_compra,
)
from backend.services.servicesFactus import FactusConfigurationError, FactusIntegrationError

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/Comprar", status_code=status.HTTP_201_CREATED, response_model=dict)
def comprar(
    compra: CompraCreate,
    idempotency_key: str = Header(
        min_length=1,
        max_length=128,
        alias="Idempotency-Key",
        description="Clave única que debes reutilizar al reintentar la misma compra.",
    ),
) -> dict:
    datos_dict = compra.model_dump()

    try:
        resultado = servicio_crear_compra(datos_dict, idempotency_key)
    except CompraNoEncontradaError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CompraConflictoError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except FactusIntegrationError as error:
        detail = error.detail
        if error.provider_status is not None and not (
            isinstance(detail, dict)
            and detail.get("provider_status") == error.provider_status
        ):
            detail = {
                "provider_status": error.provider_status,
                "factus": detail,
            }
        raise HTTPException(status_code=error.http_status, detail=detail) from error
    except FactusConfigurationError as error:
        logger.error("Factus integration is not configured: %s", error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except Exception as error:
        logger.exception("Unexpected error while creating a purchase.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la compra.",
        ) from error

    return resultado