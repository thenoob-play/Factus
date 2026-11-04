"""Pruebas unitarias (sin base de datos): cálculos, firma, webhooks y mapeo a Factus."""

import hashlib
from datetime import datetime
from decimal import Decimal

import pytest
import requests

from backend.core.errores import ConflictoError, NoEncontradoError
from backend.services.factus import mapeo
from backend.services.factus.cliente import (
    FactusClient,
    FactusRechazoError,
    FactusTimeoutError,
    extraer_documento,
)
from backend.services.pagos import firma
from backend.services.pagos.proveedores import WompiProvider
from backend.services.servicesVenta import (
    agrupar_items,
    calcular_linea,
    calcular_totales,
    impuestos_por_tarifa,
    validar_disponibilidad,
)


def producto(idp, precio, iva=19, descuento=0, excluido=False, stock=10):
    return {"idproducto": idp, "code_reference": f"P{idp}", "nombre": f"Producto {idp}",
            "precio_unitario": Decimal(str(precio)), "tax_rate": Decimal(iva), "discount_rate": Decimal(descuento),
            "is_excluded": excluido, "tax_code": "01", "unit_measure_code": "94", "standard_code": "999",
            "estado": "ACTIVO", "stock_disponible": stock}


# ------------------------------------------------------------ totales e IVA
def test_calculo_totales_con_iva_descuento_y_excluido():
    lineas = [
        calcular_linea(producto(1, "10000.00", iva=19), 2),               # 20000 + 3800
        calcular_linea(producto(2, "3333.33", iva=5, descuento=10), 3),   # 9999.99 - 1000.00 = 8999.99; iva 450.00
        calcular_linea(producto(3, "1500", iva=0, excluido=True), 1),     # 1500, excluido
    ]
    assert lineas[1]["descuento"] == Decimal("1000.00")
    assert lineas[1]["iva"] == Decimal("450.00")
    assert lineas[2]["iva"] == Decimal("0.00") and lineas[2]["is_excluded"]
    totales = calcular_totales(lineas)
    assert totales == {
        "subtotal": Decimal("31499.99"),
        "descuento_total": Decimal("1000.00"),
        "base_gravable": Decimal("28999.99"),
        "iva_total": Decimal("4250.00"),
        "total": Decimal("34749.99"),
    }
    assert all(isinstance(v, Decimal) and v.as_tuple().exponent == -2 for v in totales.values())


def test_redondeo_half_up_a_dos_decimales():
    linea = calcular_linea(producto(1, "0.05", iva=19), 1)  # IVA 0.0095 → 0.01
    assert linea["iva"] == Decimal("0.01")
    assert linea["total"] == Decimal("0.06")


def test_impuestos_agrupados_por_tarifa():
    lineas = [calcular_linea(producto(1, 100, iva=19), 1), calcular_linea(producto(2, 200, iva=19), 1),
              calcular_linea(producto(3, 50, iva=5), 2)]
    resumen = {g["tax_rate"]: g for g in impuestos_por_tarifa(lineas)}
    assert resumen["19.00"]["base"] == Decimal("300.00") and resumen["19.00"]["impuesto"] == Decimal("57.00")
    assert resumen["5.00"]["impuesto"] == Decimal("5.00")


def test_items_duplicados_se_agrupan():
    assert dict(agrupar_items([{"idproducto": 4, "cantidad": 2}, {"idproducto": 3, "cantidad": 1},
                               {"idproducto": 4, "cantidad": 5}])) == {4: 7, 3: 1}


def test_stock_insuficiente_considera_cantidades_agrupadas():
    cantidades = agrupar_items([{"idproducto": 1, "cantidad": 6}, {"idproducto": 1, "cantidad": 5}])
    with pytest.raises(ConflictoError) as error:
        validar_disponibilidad({1: producto(1, 100, stock=10)}, cantidades)
    assert error.value.codigo == "STOCK_INSUFICIENTE"
    assert error.value.detalles == [{"idproducto": 1, "disponible": 10, "solicitado": 11}]


def test_producto_inexistente_o_inactivo():
    with pytest.raises(NoEncontradoError):
        validar_disponibilidad({1: None}, {1: 1})
    inactivo = {**producto(1, 100), "estado": "INACTIVO"}
    with pytest.raises(ConflictoError):
        validar_disponibilidad({1: inactivo}, {1: 1})


# ----------------------------------------------------------- firma de pagos
def _pago(**cambios):
    expira = datetime(2026, 11, 4, 15, 30, 0)
    base = {"referencia": "VTA-1", "monto_esperado_centavos": 3474999, "moneda": "COP", "expira_en": expira}
    base["firma_integridad"] = firma.firmar(base["referencia"], base["monto_esperado_centavos"], "COP", expira)
    base.update(cambios)
    return base


def test_firma_integridad_valida_y_determinista():
    pago = _pago()
    assert len(pago["firma_integridad"]) == 64
    assert firma.firma_guardada_valida(pago)
    assert firma.verificar_confirmacion(pago, monto_recibido_centavos=3474999, moneda="COP", referencia="VTA-1").ok


def test_monto_alterado_se_rechaza():
    resultado = firma.verificar_confirmacion(_pago(), monto_recibido_centavos=100, moneda="COP")
    assert not resultado.ok and not resultado.monto_valido
    assert "monto" in resultado.motivo()


def test_monto_guardado_alterado_rompe_la_firma():
    # Si alguien cambia el monto en la base (saltándose el trigger), la firma deja de coincidir.
    alterado = _pago(monto_esperado_centavos=100)
    resultado = firma.verificar_confirmacion(alterado, monto_recibido_centavos=100)
    assert resultado.monto_valido and not resultado.firma_valida and not resultado.ok


def test_firma_cambia_con_otro_secreto():
    pago = _pago()
    assert not firma.firma_guardada_valida(pago, secreto="otro-secreto-de-mas-de-32-caracteres!!")


# ------------------------------------------------------------- Wompi
def _evento(secreto="test_events_x", **tx):
    transaccion = {"id": "1234-1610641025-49201", "status": "APPROVED", "amount_in_cents": 4490000,
                   "reference": "VTA-1", "currency": "COP", **tx}
    props = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
    timestamp = 1530291411
    cadena = "".join(str(transaccion[p.split(".")[1]]) for p in props) + str(timestamp) + secreto
    return {"event": "transaction.updated", "data": {"transaction": transaccion},
            "signature": {"properties": props, "checksum": hashlib.sha256(cadena.encode()).hexdigest().upper()},
            "timestamp": timestamp, "environment": "test"}


def test_checksum_wompi_sigue_los_pasos_de_la_documentacion():
    # Pasos de https://docs.wompi.co/docs/colombia/eventos/: valores de signature.properties
    # + timestamp + secreto de eventos, SHA256. (El checksum publicado en ese ejemplo es
    # ilustrativo: no es el SHA256 de la cadena que la propia página construye.)
    secreto = "prod_events_OcHnIzeBl5socpwByQ4hA52Em3USQ93Z"
    cadena = "1234-1610641025-49201APPROVED44900001530291411" + secreto
    esperado = hashlib.sha256(cadena.encode()).hexdigest().upper()
    evento = _evento(secreto=secreto)
    assert evento["signature"]["checksum"] == esperado
    proveedor = WompiProvider("pub", "integ", secreto, "sandbox")
    assert proveedor.evento_valido(evento, None)
    assert proveedor.evento_valido(evento, esperado.lower())  # header X-Event-Checksum


def test_webhook_con_firma_invalida():
    proveedor = WompiProvider("pub", "integ", "test_events_x", "sandbox")
    evento = _evento()
    evento["data"]["transaction"]["amount_in_cents"] = 100  # monto manipulado tras firmar
    assert not proveedor.evento_valido(evento, None)
    assert not proveedor.evento_valido(_evento(), "0" * 64)
    assert not WompiProvider("pub", "integ", "", "sandbox").evento_valido(_evento(), None)


def test_firma_integridad_wompi_y_url_de_checkout():
    proveedor = WompiProvider("pub_test_1", "secreto_integridad", "ev", "sandbox")
    expira = datetime(2026, 11, 4, 15, 30)
    esperado = hashlib.sha256(b"VTA-110000COP2026-11-04T15:30:00.000Zsecreto_integridad").hexdigest()
    assert proveedor.firma_integridad("VTA-1", 10000, "COP", "2026-11-04T15:30:00.000Z") == esperado
    inicio = proveedor.iniciar(referencia="VTA-1", monto_centavos=10000, moneda="COP", expira_en=expira,
                               firma="x", cliente={})
    assert inicio.checkout_url.startswith("https://checkout.wompi.co/p/?")
    assert f"signature%3Aintegrity={esperado}" in inicio.checkout_url


# --------------------------------------------------------------- Factus
def test_dv_nit():
    assert mapeo.calcular_dv_nit("900373115") == "3"
    assert mapeo.calcular_dv_nit("800197268") == "4"  # NIT de la DIAN
    with pytest.raises(ValueError):
        mapeo.calcular_dv_nit("90037311-5")


def _venta_mapeo(metodo="TRANSFERENCIA"):
    detalles = [calcular_linea(producto(1, "10000", iva=19), 2),
                calcular_linea(producto(2, "5000", iva=0, excluido=True), 1)]
    totales = calcular_totales(detalles)
    venta = {"referencia": "VTA-20261104-ABC", "metodo_pago": metodo, **totales}
    cliente = {"identification_document_code": "31", "identification": "900373115", "dv": None,
               "legal_organization_code": "1", "tribute_code": "ZZ", "company": "Empresa SAS",
               "names": None, "email": "f@empresa.co", "municipality_code": "11001"}
    return venta, detalles, cliente


def test_mapeo_venta_a_payload_factus():
    venta, detalles, cliente = _venta_mapeo()
    payload = mapeo.construir_payload_factura(venta, detalles, cliente, {"referencia": "VTA-20261104-ABC"})
    assert payload["reference_code"] == "VTA-20261104-ABC"
    assert payload["document"] == "01" and payload["numbering_range_id"] == 389
    assert payload["customer"] == {
        "identification_document_code": "31", "identification": "900373115", "dv": "3",
        "legal_organization_code": "1", "tribute_code": "ZZ", "company": "Empresa SAS",
        "email": "f@empresa.co", "municipality_code": "11001",
    }
    pago = payload["payment_details"][0]
    assert pago == {"payment_form": "1", "payment_method_code": "47", "reference_code": "VTA-20261104-ABC",
                    "amount": "28800.00"}
    assert payload["items"][0]["taxes"] == [{"code": "01", "rate": "19.00", "is_excluded": False}]
    assert payload["items"][1]["taxes"] == [{"code": "01", "rate": "0.00", "is_excluded": True}]
    assert payload["items"][0]["price"] == "10000.00" and payload["items"][0]["quantity"] == "2.00"


@pytest.mark.parametrize("metodo,tipo,codigo", [("EFECTIVO", None, "10"), ("TRANSFERENCIA", None, "47"),
                                                ("TARJETA", "CREDITO", "48"), ("TARJETA", "DEBITO", "49")])
def test_codigos_de_metodo_de_pago(metodo, tipo, codigo):
    assert mapeo.codigo_metodo_pago(metodo, tipo) == codigo


def test_validacion_local_detecta_errores_antes_de_enviar():
    venta, detalles, cliente = _venta_mapeo()
    payload = mapeo.construir_payload_factura(venta, detalles, cliente, {"referencia": "R"})
    payload["customer"]["dv"] = "9"
    payload["payment_details"][0]["amount"] = "1.00"
    payload["items"][0]["price"] = "10000.123"
    with pytest.raises(ValueError) as error:
        mapeo.validar_payload_factura(payload)
    mensaje = str(error.value)
    assert "dígito de verificación" in mensaje and "máximo 2 decimales" in mensaje


def test_extraer_documento_v2():
    doc = extraer_documento({"message": "ok", "data": {"number": "SETP990000550", "cufe": "c",
                                                       "links": {"qr": "q", "public_url": "u"},
                                                       "is_validated": True}})
    assert doc["numero"] == "SETP990000550" and doc["prefijo"] == "SETP"
    assert doc["qr_url"] == "q" and doc["public_url"] == "u" and doc["is_validated"]


# ------------------------------------------------------- FactusClient (HTTP simulado)
class Resp:
    def __init__(self, status, cuerpo):
        self.status_code, self._cuerpo, self.text = status, cuerpo, ""

    def json(self):
        return self._cuerpo


class SesionFalsa:
    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.peticiones = []

    def _siguiente(self, metodo, url, **kwargs):
        self.peticiones.append((metodo, url, kwargs.get("data") or kwargs.get("json")))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def post(self, url, **kwargs):
        return self._siguiente("POST", url, **kwargs)

    def request(self, metodo, url, **kwargs):
        return self._siguiente(metodo, url, **kwargs)


def _cliente(respuestas):
    sesion = SesionFalsa(respuestas)
    esperas = []
    return FactusClient("https://f", "id", "sec", "u", "p", max_retries=2, session=sesion,
                        sleep=esperas.append), sesion, esperas


TOKEN = Resp(200, {"access_token": "t1", "refresh_token": "r1", "expires_in": 3600})


def test_cliente_factus_reintenta_5xx_con_backoff():
    cliente, sesion, esperas = _cliente([TOKEN, Resp(503, {}), Resp(502, {}), Resp(200, {"data": {"id": 1}})])
    assert cliente.ver_rango(1) == {"id": 1}
    assert esperas == [0.5, 1.0]
    assert sesion.peticiones[0][2]["grant_type"] == "password"


def test_cliente_factus_no_reintenta_post_en_timeout():
    cliente, sesion, _ = _cliente([TOKEN, requests.Timeout()])
    with pytest.raises(FactusTimeoutError):
        cliente.validar_factura({"reference_code": "R"})
    assert len(sesion.peticiones) == 2  # token + un solo POST


def test_cliente_factus_rechazo_422():
    cliente, _, _ = _cliente([TOKEN, Resp(422, {"message": "Error de validación", "data": {"errors": {}}})])
    with pytest.raises(FactusRechazoError) as error:
        cliente.validar_factura({"reference_code": "R"})
    assert error.value.provider_status == 422


def test_cliente_factus_renueva_con_refresh_token():
    cliente, sesion, _ = _cliente([TOKEN, Resp(200, {"data": {"id": 1}}),
                                   Resp(200, {"access_token": "t2", "refresh_token": "r2", "expires_in": 3600}),
                                   Resp(200, {"data": {"id": 1}})])
    cliente.ver_rango(1)
    cliente._token.expira = 0  # fuerza la expiración
    cliente.ver_rango(1)
    assert sesion.peticiones[2][2]["grant_type"] == "refresh_token"
    assert sesion.peticiones[2][2]["refresh_token"] == "r1"
