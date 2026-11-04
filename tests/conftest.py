"""Configuración de pruebas.

Las pruebas unitarias no necesitan base de datos. Las de integración usan una base
aislada (`factus_test`, o TEST_MYSQL_DB) que se recrea con las migraciones; si MySQL no
está disponible, se omiten.
"""

import os
import tempfile

# Debe ir antes de importar la app: las variables de entorno tienen prioridad sobre .env.
os.environ["MYSQL_DB"] = os.environ.get("TEST_MYSQL_DB", "factus_test")
os.environ.update({
    "APP_ENV": "test",
    "JWT_SECRET": "j" * 40,
    "PAYMENT_SIGNING_SECRET": "s" * 40,
    "PAYMENT_PROVIDER": "manual",
    "BREB_LLAVE_COMERCIO": "@comercio-prueba",
    "EXPIRATION_JOB_ENABLED": "false",
    "STORAGE_DIR": tempfile.mkdtemp(prefix="factu-test-"),
    "WOMPI_PUBLIC_KEY": "pub_test_x",
    "WOMPI_INTEGRITY_SECRET": "test_integrity_x",
    "WOMPI_EVENTS_SECRET": "test_events_x",
    "FACTUS_BASE_URL": "https://factus.invalid",
    "FACTUS_CLIENT_ID": "id", "FACTUS_CLIENT_SECRET": "secret",
    "FACTUS_USERNAME": "user", "FACTUS_PASSWORD": "pass",
    "FACTUS_NUMBERING_RANGE_ID": "389",
    "LOGIN_RATE_LIMIT": "50",
})

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def base_de_datos():
    import pymysql

    from scripts.migrar import aplicar, conectar

    nombre = os.environ["MYSQL_DB"]
    if not nombre.endswith("_test"):
        pytest.exit("Por seguridad, la base de pruebas debe terminar en '_test'.")
    try:
        with conectar(None) as conn, conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{nombre}`")
    except pymysql.MySQLError as error:
        pytest.skip(f"MySQL no disponible para pruebas de integración: {error}")
    aplicar(nombre, crear=True, verbose=False)
    return nombre


TABLAS = ["auditoria", "pago_intento", "webhook_evento", "nota_credito", "factura_electronica", "pago",
          "venta_estado_historial", "venta_detalle", "venta", "caja", "cliente", "productos", "trabajador",
          "factus_catalogo"]


@pytest.fixture()
def db_limpia(base_de_datos):
    from scripts.migrar import conectar

    with conectar(base_de_datos) as conn, conn.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for tabla in TABLAS:
            cur.execute(f"TRUNCATE TABLE `{tabla}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    from backend.services.servicesAuth import limitador_login

    limitador_login.reiniciar()
    yield base_de_datos


@pytest.fixture()
def api(db_limpia):
    from fastapi.testclient import TestClient

    from app import app

    with TestClient(app) as cliente:
        yield cliente


class FactusFalso:
    """Cliente Factus simulado: registra llamadas y permite inyectar fallos."""

    def __init__(self):
        self.facturas: dict[str, dict] = {}
        self.llamadas: list[str] = []
        self.fallo_validar: Exception | None = None
        self.crear_aunque_falle = False
        self.consecutivo = 0

    def ver_rango(self, idrango):
        return {"id": idrango, "is_active": 1, "is_expired": 0}

    def _respuesta(self, factura):
        return {"status": "Created", "message": "Documento creado",
                "data": {**factura, "links": {"qr": "https://catalogo-vpfe.dian.gov.co/qr",
                                               "public_url": "https://factus.test/p"}}}

    def validar_factura(self, payload):
        self.llamadas.append("validar")
        referencia = payload["reference_code"]
        if self.fallo_validar is not None:
            fallo, self.fallo_validar = self.fallo_validar, None
            if self.crear_aunque_falle:  # simula un timeout en el que Factus sí creó la factura
                self._crear(referencia, payload)
            raise fallo
        if referencia not in self.facturas:
            self._crear(referencia, payload)
        return self._respuesta(self.facturas[referencia])

    def _crear(self, referencia, payload):
        self.consecutivo += 1
        self.facturas[referencia] = {
            "number": f"SETP99000{self.consecutivo:04d}", "prefix": "SETP", "cufe": f"cufe-{referencia}",
            "reference_code": referencia, "is_validated": True, "validated_at": "2026-11-04 10:00:00",
            "payload": payload,
        }

    def buscar_factura_por_referencia(self, referencia):
        self.llamadas.append("buscar")
        return self.facturas.get(referencia)

    def ver_factura(self, numero):
        self.llamadas.append("ver")
        factura = next(f for f in self.facturas.values() if f["number"] == numero)
        return self._respuesta(factura)

    def eliminar_factura_por_referencia(self, referencia):
        self.llamadas.append("eliminar")

    def descargar_pdf(self, numero):
        self.llamadas.append("pdf")
        return b"%PDF-1.4 prueba", f"{numero}.pdf"

    def descargar_xml(self, numero):
        return b"<Invoice/>", f"{numero}.xml"

    def enviar_email(self, numero, email):
        self.llamadas.append(f"email:{email}")
        return {"status": "OK"}

    def validar_nota_credito(self, payload):
        self.llamadas.append("nota")
        return {"data": {"number": "NC0001", "cufe": "cude-nc", "is_validated": True}}


@pytest.fixture()
def factus(monkeypatch):
    falso = FactusFalso()
    import backend.services.servicesFacturacion as facturacion

    monkeypatch.setattr(facturacion, "obtener_cliente_factus", lambda: falso)
    monkeypatch.setattr(facturacion, "_rango_validado_hasta", 0.0)
    return falso
