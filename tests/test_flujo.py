"""Pruebas de integración contra MySQL (base factus_test) con Factus y Wompi simulados."""

import hashlib
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from backend.core.seguridad import hash_password
from backend.core.utilidades import ahora_utc
from backend.crudDataBase.configDataBase.dataBase import SessionLocal
from backend.services.factus.cliente import FactusRechazoError, FactusTimeoutError

PASSWORD = "Clave-Segura-2026"


def _sql(consulta, **params):
    with SessionLocal() as db, db.begin():
        resultado = db.execute(text(consulta), params)
        return resultado.mappings().all() if resultado.returns_rows else resultado.rowcount


def _crear_admin():
    _sql("INSERT INTO trabajador (nombre, documento, email, rol, password_hash) "
         "VALUES ('Admin', '100000001', 'admin@factu.com.co', 'ADMIN', :h)", h=hash_password(PASSWORD))


def _token(api, email="admin@factu.com.co", password=PASSWORD):
    r = api.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def admin(api):
    _crear_admin()
    return _token(api)


@pytest.fixture()
def trabajador(api, admin):
    r = api.post("/trabajadores", headers=admin, json={
        "nombre": "Cajero Uno", "documento": "200000002", "email": "cajero@factu.com.co",
        "rol": "TRABAJADOR", "password": PASSWORD})
    assert r.status_code == 201, r.text
    return _token(api, "cajero@factu.com.co")


@pytest.fixture()
def datos(api, trabajador):
    cliente = api.post("/clientes", headers=trabajador, json={
        "identification_document_code": "31", "identification": "900373115", "legal_organization_code": "1",
        "company": "Empresa Prueba SAS", "email": "compras@empresa.co", "address": "Calle 1 # 2-3"})
    assert cliente.status_code == 201, cliente.text
    productos = []
    for codigo, precio, iva, stock in (("ARROZ-1", "10000.00", 19, 10), ("PAN-1", "5000.00", 0, 5)):
        r = api.post("/productos", headers=trabajador, json={
            "code_reference": codigo, "nombre": f"Producto {codigo}", "precio_unitario": precio,
            "tax_rate": iva, "is_excluded": iva == 0, "stock": stock, "stock_minimo": 2})
        assert r.status_code == 201, r.text
        productos.append(r.json()["idproducto"])
    return {"idcliente": cliente.json()["idcliente"], "productos": productos, "cliente": cliente.json()}


def _venta(api, headers, datos, metodo="EFECTIVO", cantidades=(2, 1), **extra):
    items = [{"idproducto": p, "cantidad": c} for p, c in zip(datos["productos"], cantidades)]
    return api.post("/ventas", headers=headers, json={"idcliente": datos["idcliente"], "metodoPago": metodo,
                                                      "items": items, **extra.pop("body", {})}, **extra)


def _stock(idproducto):
    fila = _sql("SELECT cantidad, stock_reservado FROM productos WHERE idproductos = :id", id=idproducto)[0]
    return fila["cantidad"], fila["stock_reservado"]


# ------------------------------------------------------------------ auth y roles
def test_login_roles_y_token(api, admin, trabajador):
    assert api.get("/trabajadores", headers=trabajador).status_code == 403
    assert api.get("/trabajadores", headers=admin).status_code == 200
    assert api.get("/clientes").status_code == 401
    r = api.get("/clientes", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401 and r.json()["error"]["codigo"] == "TOKEN_INVALIDO"
    malo = api.post("/auth/login", json={"email": "cajero@factu.com.co", "password": "incorrecta"})
    assert malo.status_code == 401 and malo.json()["error"]["codigo"] == "CREDENCIALES_INVALIDAS"
    assert _sql("SELECT COUNT(*) AS n FROM auditoria WHERE accion = 'LOGIN_FALLIDO'")[0]["n"] == 1


def test_rate_limit_login(api, admin, monkeypatch):
    from backend.services.servicesAuth import limitador_login

    monkeypatch.setattr(limitador_login, "limite", 3)
    for _ in range(3):
        api.post("/auth/login", json={"email": "x@factu.com.co", "password": "malo"})
    r = api.post("/auth/login", json={"email": "x@factu.com.co", "password": "malo"})
    assert r.status_code == 429


# ------------------------------------------------------------------ clientes
def test_cliente_nit_dv_automatico_y_duplicado(api, trabajador, datos):
    assert datos["cliente"]["dv"] == "3"
    duplicado = api.post("/clientes", headers=trabajador, json={
        "identification_document_code": "31", "identification": "900373115", "legal_organization_code": "1",
        "company": "Otra"})
    assert duplicado.status_code == 409
    dv_malo = api.post("/clientes", headers=trabajador, json={
        "identification_document_code": "31", "identification": "800197268", "dv": "1",
        "legal_organization_code": "1", "company": "DIAN"})
    assert dv_malo.status_code == 400
    busqueda = api.get("/clientes", headers=trabajador, params={"buscar": "Prueba"}).json()
    assert busqueda["total"] == 1
    # Borrado lógico: desaparece de la búsqueda y el documento queda libre.
    assert api.delete(f"/clientes/{datos['idcliente']}", headers=trabajador).status_code == 204
    assert api.get("/clientes", headers=trabajador).json()["total"] == 0
    assert _sql("SELECT COUNT(*) AS n FROM cliente")[0]["n"] == 1


# ------------------------------------------------------------------ ventas
def test_venta_no_acepta_precios_ni_trabajador_en_el_body(api, trabajador, datos):
    r = api.post("/ventas", headers=trabajador, json={
        "idcliente": datos["idcliente"], "metodoPago": "EFECTIVO", "idtrabajador": 99,
        "items": [{"idproducto": datos["productos"][0], "cantidad": 1, "precio": 1}]})
    assert r.status_code == 422


def test_stock_insuficiente(api, trabajador, datos):
    r = _venta(api, trabajador, datos, cantidades=(11, 1))
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "STOCK_INSUFICIENTE"
    assert _stock(datos["productos"][0]) == (10, 0)


def test_venta_reserva_stock_y_snapshot(api, trabajador, datos):
    r = _venta(api, trabajador, datos)
    assert r.status_code == 201, r.text
    venta = r.json()
    assert venta["estado"] == "PENDIENTE_PAGO"
    assert venta["total"] == "28800.00" and venta["iva_total"] == "3800.00"
    assert _stock(datos["productos"][0]) == (10, 2)
    # Cambiar el precio después no altera la venta.
    _sql("UPDATE productos SET precio_unitario = 99999 WHERE idproductos = :id", id=datos["productos"][0])
    otra = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert otra["items"][0]["precio_unitario"] == "10000.00"
    assert otra["pago"]["monto"] == "28800.00"


def test_idempotencia_de_venta(api, trabajador, datos):
    h = {**trabajador, "Idempotency-Key": "venta-0001"}
    a = _venta(api, h, datos)
    b = _venta(api, h, datos)
    assert a.status_code == b.status_code == 201
    assert a.json()["idventa"] == b.json()["idventa"]
    assert _stock(datos["productos"][0]) == (10, 2)
    c = _venta(api, h, datos, cantidades=(1, 1))
    assert c.status_code == 409


def test_cancelar_libera_stock(api, trabajador, datos):
    venta = _venta(api, trabajador, datos).json()
    r = api.post(f"/ventas/{venta['idventa']}/cancelar", headers=trabajador, json={"motivo": "Cliente desiste"})
    assert r.status_code == 200 and r.json()["estado"] == "CANCELADA"
    assert _stock(datos["productos"][0]) == (10, 0)
    assert r.json()["pagos"][0]["estado"] == "ANULADO"


# ------------------------------------------------------- efectivo + facturación
def test_flujo_efectivo_caja_y_factura(api, trabajador, datos, factus):
    venta = _venta(api, trabajador, datos).json()
    sin_caja = api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador,
                        json={"monto_recibido": "30000"})
    assert sin_caja.status_code == 409 and sin_caja.json()["error"]["codigo"] == "CAJA_CERRADA"

    assert api.post("/cajas/abrir", headers=trabajador, json={"base_inicial": "50000"}).status_code == 201
    poco = api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador,
                    json={"monto_recibido": "1000"})
    assert poco.status_code == 400

    r = api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador, json={"monto_recibido": "30000"})
    assert r.status_code == 200, r.text
    assert r.json()["aprobado"] and r.json()["cambio"] == "1200.00"
    assert _stock(datos["productos"][0]) == (8, 0)

    # La factura se emitió en segundo plano (BackgroundTasks) con el Factus simulado.
    detalle = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert detalle["estado"] == "FACTURADA", detalle["historial"]
    assert [h["estado_nuevo"] for h in detalle["historial"]] == ["PENDIENTE_PAGO", "PAGADA", "FACTURADA"]
    payload = next(iter(factus.facturas.values()))["payload"]
    assert payload["payment_details"][0]["payment_method_code"] == "10"
    assert payload["customer"]["dv"] == "3"

    comprobante = api.get(f"/ventas/{venta['idventa']}/comprobante", headers=trabajador).json()
    assert comprobante["verificacion"]["cambio"] == "1200.00"
    assert comprobante["factura"]["numero"] == "SETP990000001"

    cierre = api.post("/cajas/cerrar", headers=trabajador, json={"efectivo_contado": "78000"}).json()
    assert cierre["efectivo_esperado"] == "78800.00" and cierre["diferencia"] == "-800.00"


def test_factura_idempotente(api, trabajador, datos, factus):
    venta = _venta(api, trabajador, datos).json()
    api.post("/cajas/abrir", headers=trabajador, json={"base_inicial": "0"})
    api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador, json={"monto_recibido": "28800"})
    assert factus.llamadas.count("validar") == 1
    otra = api.post(f"/facturas/ventas/{venta['idventa']}/emitir", headers=trabajador)
    assert otra.status_code == 200 and otra.json()["estado"] == "EMITIDA"
    assert factus.llamadas.count("validar") == 1  # no se volvió a llamar a Factus
    assert _sql("SELECT COUNT(*) AS n FROM factura_electronica")[0]["n"] == 1


def test_timeout_consulta_por_referencia_antes_de_reintentar(api, trabajador, datos, factus):
    factus.fallo_validar = FactusTimeoutError("timeout")
    factus.crear_aunque_falle = True  # Factus sí creó la factura aunque el cliente vio timeout
    venta = _venta(api, trabajador, datos).json()
    api.post("/cajas/abrir", headers=trabajador, json={"base_inicial": "0"})
    api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador, json={"monto_recibido": "28800"})
    assert factus.llamadas == ["validar", "buscar", "ver"]
    assert len(factus.facturas) == 1
    detalle = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert detalle["estado"] == "FACTURADA"


def test_rechazo_de_factus_y_reintento(api, trabajador, datos, factus):
    factus.fallo_validar = FactusRechazoError("Error de validación", provider_status=422,
                                              detalle={"errors": {"customer": ["inválido"]}})
    venta = _venta(api, trabajador, datos).json()
    api.post("/cajas/abrir", headers=trabajador, json={"base_inicial": "0"})
    api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador, json={"monto_recibido": "28800"})
    detalle = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert detalle["estado"] == "FACTURA_FALLIDA"
    assert detalle["factura"]["estado"] == "FALLIDA"
    idfactura = detalle["factura"]["idfactura"]
    r = api.post(f"/facturas/{idfactura}/reintentar", headers=trabajador)
    assert r.status_code == 200 and r.json()["estado"] == "EMITIDA"
    assert api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()["estado"] == "FACTURADA"

    pdf = api.get(f"/facturas/{idfactura}/pdf", headers=trabajador)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    api.get(f"/facturas/{idfactura}/pdf", headers=trabajador)
    assert factus.llamadas.count("pdf") == 1  # segunda descarga desde la copia local

    nota = api.post(f"/facturas/{idfactura}/nota-credito", headers=trabajador,
                    json={"correction_concept_code": "2", "motivo": "Anulación por error"})
    assert nota.status_code == 200, nota.text
    assert _stock(datos["productos"][0]) == (10, 0)
    assert api.get(f"/facturas/{idfactura}", headers=trabajador).json()["estado"] == "ANULADA"


# ------------------------------------------------------------ transferencia manual
def test_transferencia_manual_qr_y_monto_alterado(api, trabajador, datos):
    venta = _venta(api, trabajador, datos, metodo="TRANSFERENCIA").json()
    qr = api.get(f"/ventas/{venta['idventa']}/qr", headers=trabajador).json()
    assert qr["canal"] == "BREB_MANUAL" and qr["monto"] == "28800.00"
    assert qr["qr_png_base64"].startswith("iVBOR")  # PNG

    comprobante = {"banco_origen": "Bancolombia", "numero_comprobante": "CUS123456",
                   "fecha_hora": ahora_utc().isoformat() + "Z", "monto": "1000.00", "firma": qr["firma"]}
    r = api.post(f"/pagos/publico/{qr['referencia']}/comprobante", json=comprobante)
    assert r.status_code == 200 and r.json()["estado"] == "RECHAZADO" and r.json()["sospechoso"]
    sospechosos = _sql("SELECT resultado FROM pago_intento WHERE sospechoso = 1")
    assert [s["resultado"] for s in sospechosos] == ["RECHAZADO"]


def test_transferencia_manual_aprobada_y_comprobante_unico(api, admin, trabajador, datos, factus):
    v1 = _venta(api, trabajador, datos, metodo="TRANSFERENCIA", cantidades=(1, 1)).json()
    qr = api.get(f"/ventas/{v1['idventa']}/qr", headers=trabajador).json()
    firma_mala = api.post(f"/pagos/publico/{qr['referencia']}/comprobante", json={
        "banco_origen": "Nequi", "numero_comprobante": "M999", "fecha_hora": ahora_utc().isoformat() + "Z",
        "monto": "16900.00", "firma": "0" * 64})
    assert firma_mala.status_code == 401

    cuerpo = {"banco_origen": "Nequi", "numero_comprobante": "M0001", "fecha_hora": ahora_utc().isoformat() + "Z",
              "monto": "16900.00"}
    assert api.post(f"/ventas/{v1['idventa']}/pagos/comprobante", headers=trabajador, json=cuerpo).status_code == 200
    pendientes = api.get("/pagos/comprobantes-pendientes", headers=trabajador).json()
    idpago = pendientes["items"][0]["idpago"]
    r = api.post(f"/pagos/{idpago}/verificar", headers=trabajador, json={"aprobar": True, "monto_verificado": "16900"})
    assert r.status_code == 200 and r.json()["aprobado"]

    v2 = _venta(api, trabajador, datos, metodo="TRANSFERENCIA", cantidades=(1, 1)).json()
    reuso = api.post(f"/ventas/{v2['idventa']}/pagos/comprobante", headers=trabajador, json=cuerpo)
    assert reuso.status_code == 409 and reuso.json()["error"]["codigo"] == "COMPROBANTE_DUPLICADO"
    assert api.get("/pagos/intentos-sospechosos", headers=admin).json()["total"] >= 2


def test_pago_inmutable_en_base_de_datos(api, trabajador, datos):
    venta = _venta(api, trabajador, datos, metodo="TRANSFERENCIA").json()
    with pytest.raises(OperationalError) as error:
        _sql("UPDATE pago SET monto_esperado_centavos = 1 WHERE idventa = :id", id=venta["idventa"])
    assert "PAGO_INMUTABLE" in str(error.value)
    with pytest.raises(OperationalError):
        _sql("DELETE FROM pago WHERE idventa = :id", id=venta["idventa"])


# ------------------------------------------------------------------ Wompi
def _evento_wompi(referencia, monto, estado="APPROVED", tx="tx-1", secreto="test_events_x"):
    transaccion = {"id": tx, "status": estado, "amount_in_cents": monto, "reference": referencia, "currency": "COP"}
    props = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
    cadena = f"{tx}{estado}{monto}1700000000{secreto}"
    return {"event": "transaction.updated", "data": {"transaction": transaccion}, "timestamp": 1700000000,
            "signature": {"properties": props, "checksum": hashlib.sha256(cadena.encode()).hexdigest()}}


def test_webhook_wompi(api, trabajador, datos, factus, monkeypatch):
    from backend.services.pagos.proveedores import WompiProvider

    venta = _venta(api, trabajador, datos, metodo="TARJETA", body={"canal": "WOMPI"}).json()
    referencia, monto = venta["pago"]["referencia"], 2880000
    assert "checkout.wompi.co" in venta["pago"]["checkout_url"]

    consultas = []

    def consultar(self, tx_id):
        consultas.append(tx_id)
        return {"id": tx_id, "status": "APPROVED", "reference": referencia, "amount_in_cents": monto,
                "currency": "COP", "payment_method_type": "CARD",
                "payment_method": {"extra": {"brand": "VISA", "last_four": "4242", "card_type": "DEBIT"}}}

    monkeypatch.setattr(WompiProvider, "consultar_transaccion", consultar)

    invalido = _evento_wompi(referencia, monto, secreto="otro")
    assert api.post("/pagos/webhooks/wompi", json=invalido).status_code == 401
    assert consultas == []  # con firma inválida ni siquiera se consulta a Wompi

    evento = _evento_wompi(referencia, monto)
    r = api.post("/pagos/webhooks/wompi", json=evento)
    assert r.status_code == 200 and r.json()["aprobado"], r.text
    duplicado = api.post("/pagos/webhooks/wompi", json=evento)
    assert duplicado.json() == {"procesado": False, "duplicado": True}

    detalle = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert detalle["estado"] == "FACTURADA"
    assert detalle["pago"]["tarjeta_ultimos4"] == "4242" and detalle["pago"]["tarjeta_tipo"] == "DEBITO"
    pago_factura = next(iter(factus.facturas.values()))["payload"]["payment_details"][0]
    assert pago_factura["payment_method_code"] == "49"
    assert _stock(datos["productos"][0]) == (8, 0)


def test_webhook_monto_alterado(api, trabajador, datos, monkeypatch):
    from backend.services.pagos.proveedores import WompiProvider

    venta = _venta(api, trabajador, datos, metodo="TRANSFERENCIA", body={"canal": "WOMPI"}).json()
    referencia = venta["pago"]["referencia"]
    monkeypatch.setattr(WompiProvider, "consultar_transaccion", lambda self, tx: {
        "id": tx, "status": "APPROVED", "reference": referencia, "amount_in_cents": 100, "currency": "COP"})
    r = api.post("/pagos/webhooks/wompi", json=_evento_wompi(referencia, 100))
    assert r.status_code == 200 and r.json()["aprobado"] is False and r.json()["sospechoso"]
    assert api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()["pago"] is None
    assert _stock(datos["productos"][0]) == (10, 2)  # sigue reservado hasta expirar o regenerar


# ------------------------------------------------------------------ expiración
def test_job_expira_pagos_y_libera_stock(api, trabajador, datos, monkeypatch):
    import backend.crudDataBase.CRUDpago as crud_pago
    import backend.services.servicesPago as servicio_pago

    venta = _venta(api, trabajador, datos, metodo="TRANSFERENCIA").json()
    futuro = ahora_utc() + timedelta(hours=2)
    monkeypatch.setattr(crud_pago, "ahora_utc", lambda: futuro)
    monkeypatch.setattr(servicio_pago, "ahora_utc", lambda: futuro)
    with SessionLocal() as db:
        resultado = servicio_pago.expirar_pagos_vencidos(db)
    assert resultado == {"pagos_expirados": 1, "ventas_expiradas": 1}
    detalle = api.get(f"/ventas/{venta['idventa']}", headers=trabajador).json()
    assert detalle["estado"] == "EXPIRADA" and detalle["pagos"][0]["estado"] == "EXPIRADO"
    assert _stock(datos["productos"][0]) == (10, 0)


def test_tarjeta_nunca_acepta_numero_completo(api, trabajador, datos):
    venta = _venta(api, trabajador, datos, metodo="TARJETA", body={"canal": "DATAFONO"}).json()
    r = api.post(f"/ventas/{venta['idventa']}/pagos/datafono", headers=trabajador, json={
        "codigo_autorizacion": "A1B2C3", "ultimos4": "4111111111111111", "franquicia": "VISA",
        "tipo_tarjeta": "CREDITO", "recibo_numero": "R-1", "monto": "28800", "cvv": "123"})
    assert r.status_code == 422


def test_dashboard_y_reporte(api, admin, trabajador, datos, factus):
    venta = _venta(api, trabajador, datos).json()
    api.post("/cajas/abrir", headers=trabajador, json={"base_inicial": "0"})
    api.post(f"/ventas/{venta['idventa']}/pagos/efectivo", headers=trabajador, json={"monto_recibido": "28800"})
    tablero = api.get("/dashboard", headers=admin).json()
    assert tablero["ventas_hoy"]["cantidad"] == 1 and tablero["ventas_hoy"]["total"] == "28800.00"
    assert tablero["por_metodo_mes"][0]["metodo_pago"] == "EFECTIVO"
    hoy = ahora_utc().date()
    csv = api.get("/reportes/ventas.csv", headers=admin,
                  params={"desde": str(hoy - timedelta(days=1)), "hasta": str(hoy + timedelta(days=1))})
    assert csv.status_code == 200 and venta["referencia"] in csv.text
    assert api.get("/dashboard", headers=trabajador).status_code == 403
