"""Configuración central leída desde variables de entorno / archivo .env."""

import json
from functools import cached_property

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ------------------------------------------------------------------ MySQL
    DB_HOST: str = Field(validation_alias="MYSQL_HOST")
    DB_USER: str = Field(validation_alias="MYSQL_USER")
    DB_PASSWORD: str = Field(validation_alias="MYSQL_PASSWORD")
    DB_NAME: str = Field(validation_alias="MYSQL_DB")
    DB_PORT: int = Field(default=3306, validation_alias="MYSQL_PORT")

    # ------------------------------------------------------------ Aplicación
    APP_ENV: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    STORAGE_DIR: str = "storage"
    LOG_LEVEL: str = "INFO"

    # -------------------------------------------------------- Autenticación
    JWT_SECRET: str = Field(default="", description="Mínimo 32 caracteres.")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = Field(default=480, gt=0)
    LOGIN_RATE_LIMIT: int = Field(default=5, gt=0, description="Intentos por ventana.")
    LOGIN_RATE_WINDOW_SECONDS: int = Field(default=60, gt=0)
    WEBHOOK_RATE_LIMIT: int = Field(default=120, gt=0)
    WEBHOOK_RATE_WINDOW_SECONDS: int = Field(default=60, gt=0)

    # ---------------------------------------------------------------- Pagos
    PAYMENT_SIGNING_SECRET: str = Field(default="", description="Secreto HMAC de pagos.")
    PAYMENT_EXPIRATION_MINUTES: int = Field(default=30, gt=0)
    PAYMENT_CURRENCY: str = "COP"
    # "wompi" usa el proveedor con API; "manual" usa QR Bre-B y comprobante.
    PAYMENT_PROVIDER: str = "manual"
    BREB_LLAVE_COMERCIO: str = ""
    BREB_NOMBRE_COMERCIO: str = ""
    COMPROBANTE_MAX_BYTES: int = Field(default=2_000_000, gt=0)

    WOMPI_ENV: str = "sandbox"  # sandbox | production
    WOMPI_PUBLIC_KEY: str = ""
    WOMPI_PRIVATE_KEY: str = ""
    WOMPI_INTEGRITY_SECRET: str = ""
    WOMPI_EVENTS_SECRET: str = ""
    WOMPI_REDIRECT_URL: str = ""

    # Job de expiración de pagos
    EXPIRATION_JOB_ENABLED: bool = True
    EXPIRATION_JOB_INTERVAL_SECONDS: int = Field(default=60, ge=5)

    # --------------------------------------------------------------- Factus
    FACTUS_BASE_URL: str | None = None
    FACTUS_CLIENT_ID: str | None = None
    FACTUS_CLIENT_SECRET: str | None = None
    FACTUS_USERNAME: str | None = None
    FACTUS_PASSWORD: str | None = None
    FACTUS_DOCUMENT_TYPE_ID: int = 1
    FACTUS_NUMBERING_RANGE_ID: int | None = Field(default=None, gt=0)
    FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID: int | None = Field(default=None, gt=0)
    FACTUS_PAYMENT_FORM: int = 1
    FACTUS_TRIBUTE_CODE: str = "ZZ"
    FACTUS_TIMEOUT_SECONDS: int = Field(default=30, gt=0)
    FACTUS_MAX_RETRIES: int = Field(default=3, ge=0)
    FACTUS_SEND_EMAIL: bool = True
    # Mapeo método de pago -> payment_method_code (tabla oficial de Factus):
    # 10 Efectivo, 47 Transferencia, 42 Consignación, 48 T. crédito, 49 T. débito.
    FACTUS_PAYMENT_METHOD_CODES_JSON: str = (
        '{"EFECTIVO":"10","TRANSFERENCIA":"47","TARJETA_CREDITO":"48","TARJETA_DEBITO":"49"}'
    )
    FACTUS_DEFAULT_MUNICIPALITY_ID: str | None = None
    FACTUS_MUNICIPALITIES_URL: str = (
        "https://developers.factus.com.co/tablas-de-referencia/municipios"
    )
    FACTUS_UNIT_MEASURES_URL: str = (
        "https://developers.factus.com.co/tablas-de-referencia/unit-measures/"
    )
    FACTUS_MUNICIPALITIES_CACHE_SECONDS: int = 86400

    # Compatibilidad con configuraciones anteriores (ya no se usan).
    FACTUS_PAYMENT_METHOD_CODE: str = "10"
    FACTUS_UNIT_CODES_JSON: str = '{"gramos":"GRM","servicio":"","otro":""}'

    @field_validator("FACTUS_NUMBERING_RANGE_ID", "FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID",
                     "FACTUS_DEFAULT_MUNICIPALITY_ID", mode="before")
    @classmethod
    def _vacio_es_none(cls, value: object) -> object:
        # Una variable presente pero vacía en .env (p. ej. "FACTUS_NUMBERING_RANGE_ID=") = sin configurar.
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("PAYMENT_PROVIDER")
    @classmethod
    def _provider(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"wompi", "manual"}:
            raise ValueError("PAYMENT_PROVIDER debe ser 'wompi' o 'manual'.")
        return value

    @computed_field
    def db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

    @cached_property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @cached_property
    def factus_payment_method_codes(self) -> dict[str, str]:
        data = json.loads(self.FACTUS_PAYMENT_METHOD_CODES_JSON)
        if not isinstance(data, dict):
            raise ValueError("FACTUS_PAYMENT_METHOD_CODES_JSON debe ser un objeto JSON.")
        return {str(k).upper(): str(v) for k, v in data.items()}

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Instancia única compartida por toda la aplicación.
settings = Settings()
