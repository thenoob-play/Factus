-- Ejecutar una sola vez sobre una base existente y despues de hacer un respaldo.
ALTER TABLE `compra`
  ADD COLUMN `idempotency_key` varchar(128) DEFAULT NULL,
  ADD COLUMN `request_hash` char(64) DEFAULT NULL,
  ADD COLUMN `factus_reference_code` varchar(64) DEFAULT NULL,
  ADD COLUMN `factus_source` json DEFAULT NULL,
  ADD COLUMN `factus_payload` json DEFAULT NULL,
  ADD COLUMN `factus_totales` json DEFAULT NULL,
  ADD COLUMN `factus_response` json DEFAULT NULL,
  ADD COLUMN `factus_estado`
    enum('pendiente','error','emitida') NOT NULL DEFAULT 'pendiente',
  ADD UNIQUE KEY `uk_compra_idempotency` (`idusuario`,`idempotency_key`);
