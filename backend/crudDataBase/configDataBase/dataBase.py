from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.crudDataBase.configDataBase.conf import settings

# create_engine maneja automáticamente un "Connection Pool" para reutilizar conexiones de forma segura
engine = create_engine(
    settings.db_url,
    pool_size=5,          # Conexiones simultáneas máximas mantenidas abiertas
    max_overflow=10,      # Conexiones adicionales permitidas en picos de tráfico
    pool_recycle=3600     # Evita errores de "MySQL server has gone away" reciclando conexiones cada hora
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependencia para los Endpoints de FastAPI. Garantiza que la conexión siempre se cierre al terminar la petición
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
