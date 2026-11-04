# API Factu

API REST en **FastAPI + MySQL** para administrar clientes, trabajadores y productos,
registrar ventas con **pagos verificables** (efectivo, transferencia y tarjeta) y emitir
la **factura electrónica DIAN** a través de [Factus](https://developers.factus.com.co) (API v2).

- Login con **JWT** y roles `ADMIN` / `TRABAJADOR`. El trabajador de cada venta sale del token.
- Ventas con **cálculo exacto en `Decimal`**, snapshot de precios e impuestos y **reserva de stock**.
- Pagos con **firma HMAC-SHA256** e importe inmutable (también protegido por un trigger de MySQL).
- Transferencia y tarjeta con **Wompi** (webhook firmado e idempotente) o en **modo manual**
  (QR Bre-B + comprobante verificado por un trabajador, o datáfono).
- **Facturación idempotente** (nunca dos facturas por venta), reintentos, PDF/XML en caché,
  reenvío por correo y **notas crédito** con devolución de stock.
- Caja con arqueo, dashboard, reportes CSV, auditoría, rate limiting y errores con formato uniforme.

---

## Contenido

1. [Requisitos](#requisitos)
2. [Instalación](#instalación)
3. [Base de datos y migraciones](#base-de-datos-y-migraciones)
4. [Variables de entorno](#variables-de-entorno)
5. [Ejecutar](#ejecutar)
6. [Interfaz web](#interfaz-web)
7. [Autenticación y roles](#autenticación-y-roles)
8. [Endpoints](#endpoints)
9. [Ventas](#ventas)
10. [Pagos y verificación](#pagos-y-verificación)
11. [Facturación con Factus](#facturación-con-factus)
12. [Probar el flujo completo en sandbox](#probar-el-flujo-completo-en-sandbox)
13. [Pruebas automatizadas](#pruebas-automatizadas)
14. [Estructura del proyecto](#estructura-del-proyecto)
15. [Decisiones y limitaciones](#decisiones-y-limitaciones)

---

## Requisitos

- Python 3.11 o superior (probado con 3.14).
- MySQL 8.0 o superior (probado con 9.6). Se usan columnas generadas, `CHECK` y triggers.
- Una cuenta de Factus (sandbox o producción) con un rango de numeración de facturas activo.
- Opcional: una cuenta de Wompi para cobrar transferencias y tarjetas en línea.

## Instalación

```powershell
git clone <url-del-repositorio>
cd apiFactu

python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt       # + requirements-dev.txt para las pruebas

copy .env.example .env                # Linux/macOS: cp .env.example .env
```

Completa `.env`. Como mínimo: MySQL, `JWT_SECRET`, `PAYMENT_SIGNING_SECRET` y las credenciales
de Factus. Para generar cada secreto:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Base de datos y migraciones

Las migraciones están en [backend/crudDataBase/migraciones/](backend/crudDataBase/migraciones/)
y se aplican en orden con [scripts/migrar.py](scripts/migrar.py). Cada una se registra en la tabla
`schema_migrations` y solo se ejecuta una vez.

```powershell
# Base nueva (la crea si no existe)
python -m scripts.migrar --crear

# Ver qué migraciones están aplicadas
python -m scripts.migrar --estado
```

| Migración | Qué hace |
|-----------|----------|
| `001_esquema_base.sql` | Tablas originales (`usuario`, `productos`, `compra`…) con `IF NOT EXISTS`: no cambia una base existente. |
| `002_sistema_ventas.sql` | Crea `trabajador`, `cliente`, `venta`, `venta_detalle`, `pago`, `caja`, `factura_electronica`, `nota_credito`, `auditoria`… Amplía `productos` y **copia** los clientes y trabajadores de `usuario`. No borra nada. |

**Si ya tienes datos:** haz un respaldo antes (`mysqldump factus > respaldo.sql`). En MySQL
el DDL no se puede deshacer dentro de una transacción. La migración 002 se probó sobre una copia
de la base real: los clientes y trabajadores se copiaron (el trabajador conserva su contraseña
bcrypt) y las compras antiguas quedaron intactas.

Datos de prueba ([scripts/seed.py](scripts/seed.py), idempotente):

```powershell
python -m scripts.seed --admin-email admin@miempresa.co --admin-password "Una-Clave-Larga-2026" `
                       --trabajador-password "Otra-Clave-Larga-2026"
# Solo el primer administrador:
python -m scripts.seed --solo-admin --admin-email admin@miempresa.co --admin-password "..."
```

> Los archivos `factus_*.sql` de `backend/crudDataBase/` son volcados antiguos con datos de
> ejemplo y `DROP TABLE`. Para instalar, usa las migraciones.

## Variables de entorno

Todas están documentadas en [.env.example](.env.example). Las principales:

| Variable | Descripción |
|----------|-------------|
| `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`, `MYSQL_PORT` | Conexión a MySQL. |
| `APP_ENV` | Con `production` la app no arranca sin secretos válidos. |
| `CORS_ORIGINS` | Orígenes permitidos, separados por comas. |
| `STORAGE_DIR` | Carpeta de PDF/XML en caché y de imágenes de comprobantes. |
| `JWT_SECRET`, `JWT_EXPIRE_MINUTES` | Firma y duración del token (mínimo 32 caracteres). |
| `LOGIN_RATE_LIMIT`, `LOGIN_RATE_WINDOW_SECONDS` | Intentos de login por IP y por cuenta. |
| `WEBHOOK_RATE_LIMIT`, `WEBHOOK_RATE_WINDOW_SECONDS` | Límite para webhooks y comprobantes públicos. |
| `PAYMENT_SIGNING_SECRET` | Secreto HMAC de la firma de integridad de los pagos. |
| `PAYMENT_EXPIRATION_MINUTES` | Vigencia del pago y de la reserva de stock (30 por defecto). |
| `PAYMENT_PROVIDER` | `wompi` o `manual`: canal por defecto de transferencias y tarjetas. |
| `BREB_LLAVE_COMERCIO`, `BREB_NOMBRE_COMERCIO` | Datos para el QR de transferencia manual. |
| `WOMPI_ENV`, `WOMPI_PUBLIC_KEY`, `WOMPI_INTEGRITY_SECRET`, `WOMPI_EVENTS_SECRET`, `WOMPI_REDIRECT_URL` | Integración con Wompi. |
| `EXPIRATION_JOB_ENABLED`, `EXPIRATION_JOB_INTERVAL_SECONDS` | Job que expira pagos y libera stock. |
| `FACTUS_BASE_URL` | `https://api-sandbox.factus.com.co` o `https://api.factus.com.co`. |
| `FACTUS_CLIENT_ID`, `FACTUS_CLIENT_SECRET`, `FACTUS_USERNAME`, `FACTUS_PASSWORD` | Credenciales OAuth2 de Factus. |
| `FACTUS_NUMBERING_RANGE_ID` | Rango de facturas activo de tu cuenta. |
| `FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID` | Rango de notas crédito (obligatorio si tienes más de uno activo). |
| `FACTUS_PAYMENT_METHOD_CODES_JSON` | Método de pago → `payment_method_code`. |
| `FACTUS_TIMEOUT_SECONDS`, `FACTUS_MAX_RETRIES` | Timeout y reintentos con backoff. |

## Ejecutar

```powershell
python app.py              # o: uvicorn app:app --reload
```

- **Interfaz web: <http://127.0.0.1:8000/ui/>**
- Swagger: <http://127.0.0.1:8000/docs> (usa **Authorize** con el token de `/auth/login`)
- ReDoc: <http://127.0.0.1:8000/redoc>
- Estado: `GET /health` (incluye la base de datos)

## Interfaz web

La interfaz está en [frontend/](frontend/). Es HTML, CSS y JavaScript vanilla con módulos ES,
sin frameworks ni build. La API la sirve en **<http://127.0.0.1:8000/ui/>**, en el mismo
origen, así que no hace falta CORS.

```
frontend/
├── index.html            # Login
├── app.html              # Shell: barra lateral, barra superior, contenido
├── css/                  # variables.css (tokens, claro/oscuro), base, layout, components, pages/*
├── img/favicon.svg
└── js/
    ├── config.js         # API_BASE_URL, timeouts, catálogos fijos, SRI de los CDN
    ├── api.js            # fetch central: Bearer, timeouts, errores uniformes, 401/403, descargas
    ├── auth.js · state.js · theme.js · router.js · main.js · login.js
    ├── components/       # dom (h() sin innerHTML), icons (SVG propios), modal (<dialog>), toast,
    │                     # table (paginación/orden/tarjetas en móvil), combobox, form, qr, ui
    ├── pages/            # dashboard, clientes, productos, trabajadores, venta-nueva (POS), pago,
    │                     # ventas, venta-detalle, facturas, factura-detalle, caja, reportes
    └── utils/            # format (COP, fechas es-CO), helpers (debounce, storage, dv NIT, descargas)
```

**Arquitectura.** Hay dos páginas: el login aislado y una SPA con router por hash
(`#/ventas/nueva`, `#/facturas/12`…). Las pantallas se cargan por demanda con `import()`.
Al salir de una pantalla se cancelan sus peticiones, se limpian intervalos y listeners, y se
cierran los modales. Cualquier servidor estático sirve, sin reglas de reescritura.

**Otro origen (opcional).** Para servir `frontend/` desde otro servidor, por ejemplo
`python -m http.server 5500 -d frontend`:

1. Configura la URL de la API. Puedes hacerlo de dos maneras:
   - en [frontend/js/config.js](frontend/js/config.js), o
   - sin tocar el código, desde la consola del navegador:
     `localStorage.setItem("factu.apiBaseUrl", "http://127.0.0.1:8000")`.
2. Agrega el origen del frontend a `CORS_ORIGINS` en el `.env`.
3. Agrega la URL de la API a `connect-src` en la Content-Security-Policy de `index.html` y `app.html`.

**Seguridad.**
- Nunca se usa `innerHTML` con datos: todo se construye con `createElement` y `textContent`.
- CSP estricta, sin `unsafe-inline` ni `unsafe-eval`.
- Chart.js y qrcode-generator se cargan desde el CDN con versión fija e integridad SRI.
- El frontend nunca envía precios ni datos de tarjeta.
- Los botones se deshabilitan mientras hay una petición en curso.
- La venta usa una `Idempotency-Key` por borrador: un reintento tras un error de red no la duplica.

**Pantallas:**

| Pantalla | Endpoints que usa |
|----------|-------------------|
| Login | `POST /auth/login` |
| Inicio | `GET /dashboard` (ADMIN), `GET /ventas`, `GET /cajas/actual`, `GET /productos/stock-bajo` |
| Clientes | `GET/POST /clientes`, `PUT/DELETE /clientes/{id}`, `GET /facturas/cliente/{id}`, `GET /catalogos/factus/municipios` |
| Productos | `GET/POST /productos`, `PUT/DELETE /productos/{id}`, `POST /productos/{id}/stock`, `GET /catalogos/factus/unidades_medida` |
| Trabajadores | `GET/POST /trabajadores`, `PUT/DELETE /trabajadores/{id}` |
| Nueva venta | `GET /productos`, `GET /clientes`, `POST /clientes`, `POST /ventas` (`Idempotency-Key`) |
| Pago | `GET /ventas/{id}`, `GET /ventas/{id}/qr`, `POST /ventas/{id}/pagos/efectivo · datafono · comprobante`, `POST /pagos/{id}/verificar`, `POST /ventas/{id}/pagos/regenerar`, `POST /ventas/{id}/cancelar`, `GET /cajas/actual`, `POST /cajas/abrir`, `GET /ventas/{id}/comprobante`, `POST /facturas/ventas/{id}/emitir` |
| Ventas y detalle | `GET /ventas`, `GET /ventas/{id}`, `POST /ventas/{id}/cancelar` |
| Facturas y detalle | `GET /facturas`, `GET /facturas/cliente/{id}`, `GET /facturas/{id}`, `GET /facturas/{id}/pdf · xml`, `POST /facturas/{id}/enviar-email · reintentar · nota-credito`, `POST /facturas/notas-credito/{id}/reintentar` |
| Caja | `GET /cajas/actual`, `POST /cajas/abrir · cerrar`, `GET /cajas` |
| Reportes | `GET /reportes/resumen`, `GET /reportes/{ventas,facturas}.csv`, `GET/POST /catalogos/factus[/refrescar]` |

**Atajos en Nueva venta:** <kbd>F2</kbd> busca un producto (↑/↓ y Enter para agregarlo),
<kbd>F4</kbd> va al cliente y <kbd>Ctrl</kbd>+<kbd>Enter</kbd> confirma. En toda la app,
<kbd>/</kbd> enfoca el buscador global.

## Autenticación y roles

```http
POST /auth/login
{"email": "admin@miempresa.co", "password": "..."}
→ {"access_token": "...", "token_type": "bearer", "expires_in": 28800, "usuario": {...}}
```

Envía `Authorization: Bearer <token>` en cada petición. En cada una se comprueba que el
trabajador siga activo.

| Rol | Puede |
|-----|-------|
| `ADMIN` | Todo, incluido el CRUD de trabajadores, el dashboard, los reportes, la auditoría, los intentos sospechosos y el refresco de catálogos. |
| `TRABAJADOR` | Clientes, productos, ventas, pagos, caja y facturas. |

Las contraseñas se guardan con bcrypt. El login tiene rate limiting por IP y por cuenta, y deja
auditados tanto los intentos exitosos como los fallidos.

Todos los errores tienen el mismo formato:

```json
{"error": {"codigo": "STOCK_INSUFICIENTE", "mensaje": "Stock insuficiente.",
           "detalles": [{"idproducto": 4, "disponible": 1, "solicitado": 2}]}}
```

## Endpoints

| Método | Ruta | Rol | Descripción |
|--------|------|-----|-------------|
| POST | `/auth/login` | — | Login, devuelve el JWT. |
| GET | `/auth/me` | T/A | Usuario autenticado. |
| POST | `/auth/cambiar-password` | T/A | Cambiar la propia contraseña. |
| GET, POST | `/trabajadores` | A | Listar (paginado y con búsqueda) y crear. |
| GET, PUT, DELETE | `/trabajadores/{id}` | A | Ver, actualizar y borrado lógico. |
| GET, POST | `/clientes` | T/A | Búsqueda paginada por nombre, documento o email; crear. |
| GET, PUT, DELETE | `/clientes/{id}` | T/A | Ver, actualizar y borrado lógico. |
| GET, POST | `/productos` | T/A | Búsqueda paginada (`stock_bajo=true` filtra) y crear. |
| GET | `/productos/stock-bajo` | T/A | Alerta: stock disponible ≤ stock mínimo. |
| GET, PUT, DELETE | `/productos/{id}` | T/A | Ver, actualizar y borrado lógico. |
| POST | `/productos/{id}/stock` | T/A | Ajuste de stock con motivo (auditado). |
| POST, GET | `/ventas` | T/A | Crear venta / listar con filtros. |
| GET | `/ventas/{id}` | T/A | Detalle: ítems, impuestos, pagos, historial y factura. |
| GET | `/ventas/{id}/qr` | T/A | QR del pago (PNG base64, monto, referencia, expiración). |
| GET | `/ventas/{id}/comprobante` | T/A | Comprobante del pago aprobado. |
| POST | `/ventas/{id}/cancelar` | T/A | Cancelar una venta pendiente y liberar su stock. |
| POST | `/ventas/{id}/pagos/regenerar` | T/A | Anular el pago y generar otro (referencia nueva). |
| POST | `/ventas/{id}/pagos/efectivo` | T/A | Pago en efectivo (requiere caja abierta). |
| POST | `/ventas/{id}/pagos/datafono` | T/A | Pago con datáfono físico. |
| POST | `/ventas/{id}/pagos/comprobante` | T/A | Subir el comprobante de una transferencia manual. |
| GET | `/pagos/comprobantes-pendientes` | T/A | Transferencias por verificar. |
| POST | `/pagos/{idpago}/verificar` | T/A | Aprobar o rechazar tras revisar el banco. |
| GET | `/pagos/intentos-sospechosos` | A | Intentos con firma o monto inválido, duplicados… |
| POST | `/pagos/publico/{referencia}/comprobante` | Público (firma del QR) | El cliente sube su comprobante. |
| POST | `/pagos/webhooks/wompi` | Público (firma Wompi) | Webhook de Wompi. |
| POST | `/cajas/abrir`, `/cajas/cerrar` | T/A | Apertura con base y cierre con arqueo. |
| GET | `/cajas/actual`, `/cajas` | T/A | Caja abierta e historial. |
| GET | `/facturas` | T/A | Listado con filtros por fecha, estado, método de pago, trabajador y `buscar`. |
| GET | `/facturas/cliente/{idcliente}` | T/A | Facturas de un cliente. |
| GET | `/facturas/{id}` | T/A | Detalle completo (payload enviado, respuesta de Factus, notas). |
| GET | `/facturas/{id}/pdf`, `/facturas/{id}/xml` | T/A | Descarga (copia local en caché). |
| POST | `/facturas/{id}/enviar-email` | T/A | Reenviar al correo del cliente (u otro). |
| POST | `/facturas/{id}/reintentar` | T/A | Reintentar una emisión fallida. |
| POST | `/facturas/ventas/{idventa}/emitir` | T/A | Emitir manualmente (idempotente). |
| POST | `/facturas/{id}/nota-credito` | T/A | Anulación o devolución, con restauración de stock. |
| POST | `/facturas/notas-credito/{id}/reintentar` | T/A | Reintentar una nota crédito pendiente. |
| GET | `/catalogos/factus`, `/catalogos/factus/{tipo}` | T/A | Catálogos en caché. |
| POST | `/catalogos/factus/refrescar` | A | Sincronizar catálogos desde Factus. |
| GET | `/dashboard` | A | Ventas del día y del mes, ventas por día (30 días), facturas del mes, totales por método, más vendidos, stock bajo, facturas fallidas. |
| GET | `/reportes/resumen?desde&hasta` | A | Totales, ventas por método y por día, facturas por estado y más vendidos del rango. |
| GET | `/reportes/ventas.csv`, `/reportes/facturas.csv` | A | Exportación por rango de fechas (abre en Excel). |
| GET | `/auditoria` | A | Quién creó, modificó, aprobó o anuló cada registro. |

T = TRABAJADOR, A = ADMIN. Los listados aceptan `page` y `page_size` (máximo 100).
`/clientes` y `/productos` también aceptan `ordenar` y `desc`, y `/ventas` acepta `buscar`
(referencia, documento o nombre del cliente). `GET /cajas/actual` devuelve `null` si la caja
está cerrada.

### Clientes

Los campos siguen los nombres de **Factus v2**, que usa códigos (`*_code`) en lugar de los IDs
de v1:

```json
{
  "identification_document_code": "31",
  "identification": "900373115",
  "legal_organization_code": "1",
  "company": "Distribuciones Ejemplo SAS",
  "tribute_code": "01",
  "email": "facturacion@example.com",
  "address": "Carrera 7 # 71-21",
  "municipality_code": "11001"
}
```

- `identification_document_code`: 13 CC, 31 NIT, 22 CE, 41 pasaporte… (catálogo oficial).
- Si es NIT, el `dv` se calcula solo. Si lo envías y no coincide, la petición se rechaza.
- `legal_organization_code` 1 (jurídica) exige `company`; 2 (natural) exige `names`.
- No puede haber dos clientes activos con el mismo tipo y número de documento. El borrado es lógico.

### Productos

```json
{
  "code_reference": "PORT-14", "nombre": "Portátil 14 pulgadas", "precio_unitario": "2499000.00",
  "stock": 4, "stock_minimo": 5, "tax_rate": 19, "is_excluded": false, "tax_code": "01",
  "unit_measure_code": "94", "standard_code": "001", "codigo_unspsc": "43211503", "discount_rate": "0"
}
```

`tax_rate` acepta 0, 5 o 19. `tax_code` es 01 (IVA) o 04 (INC). Si `standard_code` es `001`, se
envía a Factus el código UNSPSC; si no, el `code_reference`. El stock solo cambia con ventas o
con `POST /productos/{id}/stock`, siempre con motivo y auditoría.

## Ventas

```http
POST /ventas
Authorization: Bearer <token>
Idempotency-Key: caja1-2026-11-04-0001      (opcional, recomendado)

{
  "idcliente": 1,
  "metodoPago": "TRANSFERENCIA",            // EFECTIVO | TRANSFERENCIA | TARJETA
  "canal": "WOMPI",                         // opcional: WOMPI | BREB_MANUAL | DATAFONO
  "items": [{"idproducto": 4, "cantidad": 2}, {"idproducto": 3, "cantidad": 1}]
}
```

- El cuerpo es estricto: se rechaza con 422 cualquier precio, `idtrabajador` o campo extra.
- Se valida que el cliente y los productos existan y estén activos, y que haya stock suficiente.
  Los ítems repetidos se agrupan.
- Cálculo por línea con `Decimal` y redondeo HALF_UP a 2 decimales: subtotal → descuento →
  base gravable → IVA por tarifa → total. Es el mismo cálculo que hace Factus.
- Cada línea guarda un **snapshot** (nombre, precio, IVA, unidad, código). Cambios futuros
  del catálogo no alteran la venta.
- Todo ocurre en una transacción: se crea la venta y su pago firmado, y se **reserva** el stock.
- Referencia única `VTA-AAAAMMDD-XXXXXXXXXXXX`. Se usa como referencia del pago y como
  `reference_code` en Factus.

**Estados:** `PENDIENTE_PAGO` → `PAGADA` → `FACTURADA`, más `EXPIRADA`, `CANCELADA` y
`FACTURA_FALLIDA`. Cada cambio queda en `venta_estado_historial`.

**Stock:** se reserva al crear la venta, se descuenta al aprobar el pago y se libera si la
venta expira o se cancela. Disponible = `stock - stock_reservado`.

## Pagos y verificación

Al crear la venta se crea un pago con monto en centavos, moneda COP, referencia única,
expiración y:

```
firma_integridad = HMAC-SHA256(PAYMENT_SIGNING_SECRET, "referencia|centavos|moneda|expira_en")
```

- **Toda** confirmación recalcula la firma desde los datos guardados y compara el monto
  recibido con el firmado. Si no coinciden, el pago pasa a `RECHAZADO` y el intento se registra
  como **sospechoso** en `pago_intento`.
- Ni la API ni el ORM pueden cambiar el monto, la moneda, la referencia, la firma o la
  expiración. Un trigger de MySQL lo impide incluso desde la consola, bloquea los cambios de un
  pago ya finalizado y prohíbe borrar pagos.
- Para cambiar el método de pago, `POST /ventas/{id}/pagos/regenerar` anula el pago y crea uno
  nuevo con otra referencia y otra firma.

| Método | Canal | Cómo se confirma |
|--------|-------|------------------|
| EFECTIVO | `EFECTIVO` | El trabajador registra el monto recibido (≥ total). Se calcula el cambio y el pago queda en su caja abierta. |
| TRANSFERENCIA | `WOMPI` | Checkout de Wompi con firma de integridad y QR. Solo se aprueba por webhook firmado **y** después de consultar la transacción en la API de Wompi. |
| TRANSFERENCIA | `BREB_MANUAL` | QR con la llave Bre-B, el monto, la referencia y la firma HMAC. El cliente o un trabajador sube el comprobante (banco, número/CUS **único**, fecha, monto, imagen opcional). Un trabajador lo verifica contra el banco. |
| TARJETA | `WOMPI` | Igual que la transferencia por Wompi. Se guardan solo la franquicia, los últimos 4 dígitos y el id de la transacción. |
| TARJETA | `DATAFONO` | Registro manual del código de aprobación, los últimos 4, la franquicia y el número de recibo (**único**). |

**PCI DSS:** la API nunca recibe, guarda ni registra en logs el número de tarjeta, el CVV ni el
vencimiento. Cualquier campo de ese tipo se rechaza con 422.

**Webhook de Wompi** (`POST /pagos/webhooks/wompi`), configurado en el panel de Wompi:
1. Valida `X-Event-Checksum` = SHA256(valores de `signature.properties` + `timestamp` +
   secreto de eventos).
2. Consulta `GET /v1/transactions/{id}` en Wompi y compara la referencia y el monto.
3. Es idempotente: un evento repetido responde `{"duplicado": true}` sin procesarse.
4. Si llega un pago aprobado sobre un pago ya expirado, se registra como `PAGO_TARDIO`
   sospechoso para revisar un reembolso.

**Al aprobar** (en una sola transacción): el pago pasa a `APROBADO`, la venta a `PAGADA`, se
descuenta el stock y se audita. Después se dispara la facturación automática en segundo plano.

**Caja:** `POST /cajas/abrir {"base_inicial": "50000"}` → ventas en efectivo →
`POST /cajas/cerrar {"efectivo_contado": "78000"}`. El cierre devuelve lo esperado
(base + ventas en efectivo), lo contado y la diferencia.

**Expiración:** un job interno (cada `EXPIRATION_JOB_INTERVAL_SECONDS`) expira los pagos
vencidos y las ventas sin pago vigente, y libera el stock. Una transferencia manual cuyo
comprobante se subió antes del vencimiento no expira mientras espera la verificación.

## Facturación con Factus

Cliente HTTP aislado en [backend/services/factus/cliente.py](backend/services/factus/cliente.py).
Usa endpoints verificados en la documentación oficial de la v2 y probados contra el sandbox
(OAuth, rangos y búsqueda por referencia):

| Uso | Endpoint |
|-----|----------|
| Token y refresco | `POST /oauth/token` (`password` / `refresh_token`) |
| Emitir | `POST /v2/bills/validate` |
| Buscar por referencia | `GET /v2/bills?filter[reference_code]=` |
| Ver | `GET /v2/bills/{number}` |
| PDF / XML | `GET /v2/bills/{number}/download-pdf` · `/download-xml` (base64) |
| Correo | `POST /v2/bills/{number}/send-email` |
| Eliminar pendiente | `DELETE /v2/bills/destroy/reference/{reference_code}` |
| Nota crédito | `POST /v2/credit-notes/validate` |
| Rangos | `GET /v2/numbering-ranges[/{id}]` |

- El token se guarda en caché y se renueva con `refresh_token` antes de que expire. Se usan
  timeouts, reintentos con backoff exponencial ante errores de red, 5xx y 429, y logs sin
  credenciales ni cuerpos.
- **Mapeo:** `document "01"`, `reference_code` = referencia de la venta, `payment_form "1"`,
  `payment_method_code` según el método (EFECTIVO 10, TRANSFERENCIA **47**, TARJETA crédito 48 o
  débito 49), cliente desde la tabla `cliente` e ítems desde el snapshot. En v2, `price` es neto
  y los impuestos van en `taxes[]`.
- **Validación previa:** campos obligatorios, máximo 2 decimales, dv del NIT y que la suma de los
  pagos coincida con el total de los ítems.
- **Idempotencia:** una factura por venta (`UNIQUE`). Mientras se emite, la factura queda
  `PROCESANDO` y otra llamada recibe 409. Si hay timeout o error de red, primero se consulta en
  Factus por `reference_code`. Si Factus responde 409 por un documento pendiente, se elimina el
  pendiente y se reenvía.
- **Se guarda:** número, prefijo, CUFE, URL del QR de la DIAN, URL pública, validación, mensajes,
  errores y el JSON completo enviado y recibido.
- **Si Factus rechaza:** la factura queda `FALLIDA` y la venta `FACTURA_FALLIDA`, con los errores
  guardados. Luego se reintenta con `POST /facturas/{id}/reintentar`.
- **Nota crédito:** concepto 2 (anulación) o devoluciones parciales por ítem, sin superar las
  unidades facturadas. Restaura el stock una sola vez.
- **Catálogos:** `POST /catalogos/factus/refrescar` guarda en `factus_catalogo` los rangos (API),
  los municipios y las unidades (tablas publicadas en la v2), y las tablas oficiales fijas: tipos
  de documento, organizaciones, tributos, métodos de pago, estándares y conceptos. Cuando están
  sincronizados, se usan para validar clientes y productos.

## Probar el flujo completo en sandbox

1. Configura `.env` con las credenciales de **sandbox** de Factus, `JWT_SECRET`,
   `PAYMENT_SIGNING_SECRET` y `BREB_LLAVE_COMERCIO`.
2. Ejecuta `python -m scripts.migrar --crear` y `python -m scripts.seed ...` (ver arriba).
3. Arranca la API con `python app.py` y abre <http://127.0.0.1:8000/docs>.
4. `POST /auth/login` como ADMIN, y luego **Authorize** con el token.
5. `POST /catalogos/factus/refrescar {}`. En `GET /catalogos/factus/rangos_numeracion`,
   copia el `id` del rango "Factura de Venta" a `FACTUS_NUMBERING_RANGE_ID` y el de
   "Nota Crédito" a `FACTUS_CREDIT_NOTE_NUMBERING_RANGE_ID`. Reinicia la API.
6. Inicia sesión como el trabajador y abre caja: `POST /cajas/abrir {"base_inicial": "0"}`.
7. **Efectivo:** `POST /ventas` con `"metodoPago": "EFECTIVO"` y luego
   `POST /ventas/{id}/pagos/efectivo {"monto_recibido": "<total>"}`. Unos segundos después,
   `GET /ventas/{id}` muestra `FACTURADA` y `GET /facturas/{id}/pdf` descarga el PDF de Factus.
8. **Transferencia manual:** crea la venta con `"metodoPago": "TRANSFERENCIA"`, consulta
   `GET /ventas/{id}/qr`, registra el comprobante con `POST /ventas/{id}/pagos/comprobante` y
   apruébalo con `POST /pagos/{idpago}/verificar {"aprobar": true, "monto_verificado": "<total>"}`.
9. **Monto alterado:** repite el paso 8 con un monto distinto. El pago queda `RECHAZADO` y aparece
   en `GET /pagos/intentos-sospechosos`.
10. **Wompi (opcional):** usa las llaves de prueba con `PAYMENT_PROVIDER=wompi`. Expón la API
    (por ejemplo con ngrok) y configura `https://<tu-url>/pagos/webhooks/wompi` como URL de
    eventos. Abre el `checkout_url` de la venta y paga con las tarjetas o Nequi de prueba de Wompi.
11. **Nota crédito:** `POST /facturas/{id}/nota-credito {"correction_concept_code": "2", "motivo": "Anulación de prueba"}`.
12. Revisa `GET /dashboard`, `GET /reportes/ventas.csv?desde=...&hasta=...` y `GET /auditoria`.

## Pruebas automatizadas

```powershell
pip install -r requirements-dev.txt
python -m pytest
```

- **Unitarias**, sin base de datos: totales e IVA, redondeo, agrupación, stock insuficiente,
  firma de integridad, monto alterado, webhook con firma inválida, firma y checkout de Wompi,
  dv del NIT, mapeo a Factus, validación previa, y el cliente Factus con HTTP simulado
  (backoff, sin reintento del POST tras un timeout, rechazo 422, refresh_token).
- **Integración**, contra MySQL en una base aislada **`factus_test`** que se recrea con las
  migraciones (si MySQL no está disponible, se omiten): roles, rate limit, clientes, ventas,
  idempotencia, efectivo y caja, idempotencia de la factura, timeout con consulta por referencia,
  rechazo y reintento, PDF en caché, nota crédito, transferencia manual, comprobante duplicado,
  trigger de inmutabilidad, webhook (firma inválida, aprobado y duplicado), monto alterado, job
  de expiración, rechazo de datos de tarjeta, dashboard y CSV.

## Estructura del proyecto

```
apiFactu/
├── app.py                          # App FastAPI: CORS, errores, routers y job de expiración
├── scripts/
│   ├── migrar.py                   # Ejecuta migraciones (con DELIMITER para triggers)
│   └── seed.py                     # Datos de prueba
├── tests/                          # pytest: unitarias e integración
└── backend/
    ├── core/                       # Errores uniformes, JWT/roles, rate limit, dinero y fechas
    ├── models/                     # Routers HTTP (auth, gestion, ventas, facturas)
    ├── shemas/esquemas.py          # Esquemas Pydantic de entrada (extra="forbid")
    ├── services/                   # Lógica de negocio
    │   ├── servicesVenta.py        #   Cálculo, snapshot, reservas, estados
    │   ├── servicesPago.py         #   Firma, aprobación/rechazo, webhook, caja, expiración
    │   ├── servicesFacturacion.py  #   Emisión idempotente, PDF/XML, correo, notas crédito
    │   ├── factus/                 #   FactusClient, catálogos y mapeo a v2
    │   └── pagos/                  #   Firma HMAC y proveedores (Wompi, Bre-B manual)
    └── crudDataBase/               # SQL parametrizado (una función por consulta)
        ├── migraciones/            #   001, 002…
        └── configDataBase/         #   Settings (.env) y sesión de SQLAlchemy
```

Capas: **router** (`models/`) → **servicio** (`services/`) → **CRUD** (`crudDataBase/`). Los
servicios abren transacciones cortas con `with db.begin():` y **nunca** llaman a Factus ni a
Wompi con una transacción abierta. El orden de bloqueo es siempre venta → pago → productos, para
evitar deadlocks.

## Decisiones y limitaciones

- **Campos `_code` y no `_id`:** Factus v2 reemplazó `identification_document_id`, `tribute_id`,
  `municipality_id`, `unit_measure_id` y `tax_rate` por `*_code` y `taxes[]`. La API usa los
  nombres de v2.
- **TRANSFERENCIA = 47:** en la tabla oficial de Factus, 42 es *Consignación* y 47 es
  *Transferencia*. Se puede cambiar en `FACTUS_PAYMENT_METHOD_CODES_JSON`.
- **QR Bre-B manual:** es un JSON firmado con la llave, el monto, la referencia y la expiración.
  Las apps bancarias no lo leen para autocompletar el pago; para eso se necesita el QR EMVCo
  que emite el banco o un proveedor (usa `PAYMENT_PROVIDER=wompi`).
- **Fechas:** se guardan en UTC. Las fechas sin zona horaria que envía un cliente (comprobantes)
  y los filtros por día se interpretan en hora de Colombia (UTC-5).
- **Rate limiting en memoria:** sirve para una sola instancia. Con varias réplicas hay que
  moverlo a Redis.
- **Facturación en segundo plano** con `BackgroundTasks`. Si el proceso se reinicia durante una
  emisión, la factura queda `PROCESANDO` y se puede reintentar pasados 5 minutos (la consulta por
  `reference_code` evita duplicados).
- **Envío de correo:** Factus no envía correos en sandbox.
- **Tablas antiguas** (`usuario`, `compra`, `compra_detalle`, `factura`): se conservan con sus
  datos como histórico. El nuevo flujo usa `cliente`, `trabajador`, `venta` y `factura_electronica`.
