from typing import Any

from sqlalchemy.orm import Session

from backend.core.errores import NoAutenticadoError, ValidacionError
from backend.core.rate_limit import LimitadorVentana
from backend.core.seguridad import Usuario, crear_token, hash_password, verificar_password
from backend.crudDataBase import CRUDtrabajador
from backend.crudDataBase.CRUDauditoria import registrar_auditoria
from backend.crudDataBase.configDataBase.conf import settings

limitador_login = LimitadorVentana(settings.LOGIN_RATE_LIMIT, settings.LOGIN_RATE_WINDOW_SECONDS)


def login(db: Session, email: str, password: str, ip: str) -> dict[str, Any]:
    email = email.strip().lower()
    # Límite por IP y por cuenta: frena fuerza bruta y relleno de credenciales.
    limitador_login.verificar(f"ip:{ip}")
    limitador_login.verificar(f"email:{email}")

    with db.begin():
        trabajador = CRUDtrabajador.buscar_por_email(db, email)
        valido = verificar_password(password, trabajador["password_hash"] if trabajador else None)
        exito = bool(trabajador and valido and trabajador["estado"] == "ACTIVO")
        if exito:
            CRUDtrabajador.registrar_login(db, trabajador["idtrabajador"])
            registrar_auditoria(db, "trabajador", trabajador["idtrabajador"], "LOGIN",
                                trabajador["idtrabajador"], {"ip": ip})
        else:
            # Se confirma el registro del intento fallido antes de responder 401.
            registrar_auditoria(db, "trabajador", email, "LOGIN_FALLIDO", None, {"ip": ip})
    if not exito:
        raise NoAutenticadoError("Credenciales incorrectas.", codigo="CREDENCIALES_INVALIDAS")

    limitador_login.reiniciar(f"email:{email}")
    token, expira_en = crear_token(trabajador["idtrabajador"], trabajador["rol"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expira_en,
        "usuario": {
            "idtrabajador": trabajador["idtrabajador"],
            "nombre": trabajador["nombre"],
            "email": trabajador["email"],
            "rol": trabajador["rol"],
        },
    }


def cambiar_password(db: Session, usuario: Usuario, actual: str, nueva: str) -> None:
    with db.begin():
        trabajador = CRUDtrabajador.buscar_por_email(db, usuario.email)
        if not trabajador or not verificar_password(actual, trabajador["password_hash"]):
            raise ValidacionError("La contraseña actual no es correcta.")
        if actual == nueva:
            raise ValidacionError("La nueva contraseña debe ser distinta de la actual.")
        CRUDtrabajador.actualizar(db, usuario.idtrabajador, {"password_hash": hash_password(nueva)},
                                  usuario.idtrabajador)
        registrar_auditoria(db, "trabajador", usuario.idtrabajador, "CAMBIO_PASSWORD", usuario.idtrabajador)
