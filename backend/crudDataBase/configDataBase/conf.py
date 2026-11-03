from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, computed_field

class Settings(BaseSettings):
    DB_HOST: str = Field(validation_alias="MYSQL_HOST")
    DB_USER: str = Field(validation_alias="MYSQL_USER")
    DB_PASSWORD: str = Field(validation_alias="MYSQL_PASSWORD")
    DB_NAME: str = Field(validation_alias="MYSQL_DB")
    DB_PORT: int = Field(default=3306, validation_alias="MYSQL_PORT")

    FACTUS_BASE_URL: str | None = None
    FACTUS_CLIENT_ID: str | None = None
    FACTUS_CLIENT_SECRET: str | None = None
    FACTUS_USERNAME: str | None = None
    FACTUS_PASSWORD: str | None = None
    FACTUS_DOCUMENT_TYPE_ID: int = 1
    FACTUS_NUMBERING_RANGE_ID: int | None = None
    FACTUS_PAYMENT_FORM: int = 1
    FACTUS_PAYMENT_METHOD_CODE: str = "10"
    FACTUS_TRIBUTE_CODE: str = "21"
    FACTUS_DEFAULT_MUNICIPALITY_ID: str | None = None
    FACTUS_MUNICIPALITIES_URL: str = (
        "https://developers.factus.com.co/tablas-de-referencia/municipios"
    )
    FACTUS_UNIT_MEASURES_URL: str = (
        "https://developers.factus.com.co/tablas-de-referencia/unit-measures/"
    )
    FACTUS_MUNICIPALITIES_CACHE_SECONDS: int = 86400
    # SUPUESTO: De los dos códigos Factus llamados "gramo", se usa el código GRM.
    FACTUS_UNIT_CODES_JSON: str = '{"gramos":"GRM","servicio":"","otro":""}'

    # Construye la URL de conexión automáticamente y de forma segura
    @computed_field
    def db_url(self) -> str:
        return f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Busca el archivo .env una carpeta arriba de app/
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Instancia única para compartir en toda la aplicación (Singleton)
settings = Settings()
