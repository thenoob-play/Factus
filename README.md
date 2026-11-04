# Factus

## Registrar una compra y emitir su factura

`POST /Comprar` requiere `Idempotency-Key` como encabezado HTTP. No lo envíes en la
URL. Envía una clave nueva por cada compra y reutiliza esa misma clave y el mismo
cuerpo únicamente al reintentar esa compra:

```powershell
curl.exe -X POST "http://127.0.0.1:8000/Comprar" `
  -H "Content-Type: application/json" `
  -H "Idempotency-Key: compra-2026-001" `
  -d '{"idusuario":1,"items":[{"idproducto":1,"cantidad":2},{"idproducto":2,"cantidad":1}]}'
```

La compra, sus detalles y el descuento de inventario se confirman primero en MySQL.
Después se emite la factura en Factus. Si Factus falla o no está disponible, la
compra queda guardada y la respuesta informa del error; reintenta con la misma
cabecera y el mismo cuerpo. Una clave reutilizada con un cuerpo diferente devuelve
`409 Conflict`. Cada compra nueva recibe una referencia Factus UUID distinta; los
reintentos conservan la referencia guardada para evitar duplicar la factura. El
número de factura lo asigna Factus según el rango de numeración y no se envía en el
payload.

Para una base ya creada, ejecuta una vez
[`migrar_idempotencia_factus.sql`](backend/crudDataBase/migrar_idempotencia_factus.sql).
Configura en `.env` las credenciales de Factus y el ID de un rango de facturación
activo y vigente de la misma cuenta (`FACTUS_BASE_URL`, `FACTUS_CLIENT_ID`,
`FACTUS_CLIENT_SECRET`, `FACTUS_USERNAME`, `FACTUS_PASSWORD` y
`FACTUS_NUMBERING_RANGE_ID`; en `.env` configura, por ejemplo,
`FACTUS_NUMBERING_RANGE_ID=12` solo si `12` es el ID real de tu cuenta. Antes
de emitir, la API consulta el endpoint oficial de detalle
`GET /v2/numbering-ranges/{FACTUS_NUMBERING_RANGE_ID}` y comprueba que el rango
exista, esté activo, vigente y corresponda a una factura. Si Factus deniega el
acceso o no devuelve el rango, la API informa el problema claramente. En los
reintentos también actualiza el payload guardado si cambió el ID configurado.
El endpoint de factura utilizado es `POST /v2/bills/validate`.

Factus documenta `payment_details` como los medios utilizados para pagar una
factura; no inicia un cobro ni confirma pagos. `factus_estado=emitida` indica
que se emitió la factura, no que la compra haya sido pagada. La respuesta
completa de Factus, incluido cualquier dato de verificación que retorne, se
devuelve y queda almacenada con la compra. Para cobrar en línea y marcar la
compra como pagada se necesita integrar una pasarela de pago y su webhook
firmado; esa funcionalidad no se simula en la integración Factus. Los valores
`FACTUS_PAYMENT_FORM` y `FACTUS_PAYMENT_METHOD_CODE` son datos fiscales de la
factura y deben reflejar un pago real; no crean opciones de pago ni un QR de cobro.
