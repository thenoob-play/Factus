"""Hash de contraseñas (bcrypt), JWT y dependencias de autorización por rol."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from backend.core.errores import ConfiguracionError, NoAutenticadoError, ProhibidoError
from backend.crudDataBase.configDataBase.conf import settings
from backend.crudDataBase.configDataBase.dataBase import SessionLocal

ROLES = ("ADMIN", "TRABAJADOR")
_bearer = HTTPBearer(auto_error=False)
# Hash válido de una contraseña aleatoria: se compara contra él cuando el usuario no
# existe, para que el tiempo de respuesta no revele qué correos están registrados.
_HASH_SEÑUELO = bcrypt.hashpw(b"senuelo-no-usar", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    datos = password.encode("utf-8")
    if len(datos) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes.")
    return bcrypt.hashpw(datos, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verificar_password(password: str, password_hash: str | None) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:72], (password_hash or _HASH_SEÑUELO).encode("utf-8")
        ) and password_hash is not None
    except ValueError:
        return False


def _secreto_jwt() -> str:
    if len(settings.JWT_SECRET) < 32:
        raise ConfiguracionError("JWT_SECRET debe tener al menos 32 caracteres.")
    return settings.JWT_SECRET


def crear_token(idtrabajador: int, rol: str) -> tuple[str, int]:
    ahora = datetime.now(UTC)
    expira = ahora + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    token = jwt.encode(
        {"sub": str(idtrabajador), "rol": rol, "iat": ahora, "exp": expira},
        _secreto_jwt(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, settings.JWT_EXPIRE_MINUTES * 60


@dataclass(frozen=True)
class Usuario:
    idtrabajador: int
    nombre: str
    email: str
    rol: str

    @property
    def es_admin(self) -> bool:
        return self.rol == "ADMIN"


def _cargar_trabajador_activo(idtrabajador: int) -> Usuario | None:
    # Sesión propia: no deja abierta una transacción en la sesión de la petición.
    with SessionLocal() as db:
        fila = db.execute(
            text(
                """
                SELECT idtrabajador, nombre, email, rol
                FROM trabajador
                WHERE idtrabajador = :id AND estado = 'ACTIVO' AND eliminado_en IS NULL
                """
            ),
            {"id": idtrabajador},
        ).mappings().first()
    return Usuario(**fila) if fila else None


def usuario_actual(
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Usuario:
    if credenciales is None or credenciales.scheme.lower() != "bearer":
        raise NoAutenticadoError("Falta el token de acceso (Authorization: Bearer ...).")
    try:
        datos = jwt.decode(
            credenciales.credentials,
            _secreto_jwt(),
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["sub", "exp", "rol"]},
        )
        idtrabajador = int(datos["sub"])
    except jwt.ExpiredSignatureError as error:
        raise NoAutenticadoError("El token expiró.", codigo="TOKEN_EXPIRADO") from error
    except (jwt.PyJWTError, ValueError, KeyError) as error:
        raise NoAutenticadoError("Token inválido.", codigo="TOKEN_INVALIDO") from error

    usuario = _cargar_trabajador_activo(idtrabajador)
    if usuario is None:
        raise NoAutenticadoError("El usuario no existe o está inactivo.")
    return usuario


def requiere_rol(*roles: str):
    def _dependencia(usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
        if usuario.rol not in roles:
            raise ProhibidoError("No tienes permiso para esta operación.")
        return usuario

    return _dependencia


UsuarioActual = Annotated[Usuario, Depends(requiere_rol("ADMIN", "TRABAJADOR"))]
SoloAdmin = Annotated[Usuario, Depends(requiere_rol("ADMIN"))]
