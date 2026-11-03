"""Punto de entrada de la API de Factu."""

import uvicorn

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.crudDataBase.configDataBase.dataBase import get_db
from backend.models.login import router as login_router
from backend.models.producto import router as producto_router
from backend.models.modelsComprar import router as compra_router


app = FastAPI(
    title="API Factu",
    description="API para los servicios de Factu.",
    version="1.0.0",
)

app.include_router(login_router)
app.include_router(producto_router)
app.include_router(compra_router)


@app.get("/", tags=["Sistema"], summary="Información de la API")
async def read_root() -> dict[str, str]:
    """Indica que la API está disponible y dónde consultar su documentación."""
    return {
        "message": "API Factu está activa",
        "documentation": "/docs",
    }




@app.get("/health", tags=["Sistema"], summary="Estado del servicio")
async def health_check() -> dict[str, str]:
    """Permite comprobar la disponibilidad del servicio."""
    return {"status": "ok"}


@app.get("/healthcheck")
def check_database_connection(db: Session = Depends(get_db)):
    """
    Endpoint seguro para verificar la salud de la aplicación y la conexión a MySQL
    """
    try:
        # Ejecuta una consulta ligera para verificar que la base de datos responde
        db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error crítico de conexión a la base de datos: {str(e)}"
        )


if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)