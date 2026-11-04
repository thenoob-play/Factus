from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.crudDataBase.configDataBase.conf import settings

# create_engine mantiene un pool de conexiones reutilizables.
engine = create_engine(
    settings.db_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,   # evita "MySQL server has gone away"
    pool_pre_ping=True,  # descarta conexiones muertas antes de usarlas
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición, siempre cerrada al final.

    Los servicios abren sus propias transacciones con ``with db.begin():``.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
