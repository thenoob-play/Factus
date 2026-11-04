-- 002: trabajadores, clientes alineados con Factus v2, productos ampliados, ventas,
-- pagos verificables, cajas, facturación electrónica, notas crédito y auditoría.
-- Solo agrega: no borra tablas ni columnas. Los datos de `usuario` se copian a
-- `cliente` y `trabajador`; las tablas antiguas se conservan intactas.
-- Haz un respaldo antes de aplicarla: en MySQL el DDL no se puede revertir.

-- ------------------------------------------------------------------ trabajador
CREATE TABLE `trabajador` (
  `idtrabajador` int NOT NULL AUTO_INCREMENT,
  `nombre` varchar(120) NOT NULL,
  `tipo_documento` varchar(3) NOT NULL DEFAULT '13',
  `documento` varchar(20) NOT NULL,
  `email` varchar(120) NOT NULL,
  `telefono` varchar(20) DEFAULT NULL,
  `rol` enum('ADMIN','TRABAJADOR') NOT NULL DEFAULT 'TRABAJADOR',
  `password_hash` varchar(255) NOT NULL,
  `estado` enum('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
  `ultimo_login_en` datetime DEFAULT NULL,
  `creado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creado_por` int DEFAULT NULL,
  `actualizado_por` int DEFAULT NULL,
  `eliminado_en` datetime DEFAULT NULL,
  `legacy_idusuario` int DEFAULT NULL,
  PRIMARY KEY (`idtrabajador`),
  UNIQUE KEY `uk_trabajador_email` (`email`),
  UNIQUE KEY `uk_trabajador_documento` (`tipo_documento`,`documento`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- --------------------------------------------------------------------- cliente
CREATE TABLE `cliente` (
  `idcliente` int NOT NULL AUTO_INCREMENT,
  `identification_document_code` varchar(3) NOT NULL,
  `identification` varchar(20) NOT NULL,
  `dv` char(1) DEFAULT NULL,
  `legal_organization_code` char(1) NOT NULL,
  `tribute_code` varchar(3) NOT NULL DEFAULT 'ZZ',
  `names` varchar(150) DEFAULT NULL,
  `company` varchar(150) DEFAULT NULL,
  `trade_name` varchar(150) DEFAULT NULL,
  `email` varchar(120) DEFAULT NULL,
  `phone` varchar(20) DEFAULT NULL,
  `address` varchar(200) DEFAULT NULL,
  `municipality_code` varchar(10) DEFAULT NULL,
  `estado` enum('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
  `creado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `creado_por` int DEFAULT NULL,
  `actualizado_por` int DEFAULT NULL,
  `eliminado_en` datetime DEFAULT NULL,
  `legacy_idusuario` int DEFAULT NULL,
  -- Un mismo documento solo puede existir una vez entre los clientes no eliminados.
  `documento_vigente` varchar(30) GENERATED ALWAYS AS (
    IF(`eliminado_en` IS NULL,
       CONCAT(`identification_document_code`, '-', `identification`), NULL)
  ) STORED,
  PRIMARY KEY (`idcliente`),
  UNIQUE KEY `uk_cliente_documento_vigente` (`documento_vigente`),
  KEY `idx_cliente_identification` (`identification`),
  KEY `idx_cliente_names` (`names`),
  KEY `idx_cliente_company` (`company`),
  KEY `idx_cliente_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------- productos (ampliación)
ALTER TABLE `productos`
  MODIFY `idcategoria` int DEFAULT NULL,
  MODIFY `URL_imagen` varchar(255) DEFAULT NULL,
  MODIFY `descuento` decimal(5,2) NOT NULL DEFAULT '0.00',
  ADD COLUMN `stock_reservado` int NOT NULL DEFAULT 0 AFTER `cantidad`,
  ADD COLUMN `stock_minimo` int NOT NULL DEFAULT 0 AFTER `stock_reservado`,
  ADD COLUMN `is_excluded` tinyint(1) NOT NULL DEFAULT 0 AFTER `tarifa_iva`,
  ADD COLUMN `tax_code` varchar(3) NOT NULL DEFAULT '01' AFTER `is_excluded`,
  ADD COLUMN `unit_measure_code` varchar(10) DEFAULT NULL AFTER `Uni_medida`,
  ADD COLUMN `standard_code` varchar(3) NOT NULL DEFAULT '999' AFTER `codigo_UNSPSC`,
  ADD COLUMN `estado` enum('ACTIVO','INACTIVO') NOT NULL DEFAULT 'ACTIVO',
  ADD COLUMN `creado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  ADD COLUMN `creado_por` int DEFAULT NULL,
  ADD COLUMN `actualizado_por` int DEFAULT NULL,
  ADD COLUMN `eliminado_en` datetime DEFAULT NULL,
  ADD CONSTRAINT `chk_productos_stock` CHECK (`cantidad` >= 0),
  ADD CONSTRAINT `chk_productos_reservado` CHECK (`stock_reservado` >= 0 AND `stock_reservado` <= `cantidad`),
  ADD CONSTRAINT `chk_productos_descuento` CHECK (`descuento` >= 0 AND `descuento` <= 100);

-- Códigos de unidad (UN/ECE, los que usa Factus v2). Verifícalos contra el catálogo.
UPDATE `productos` SET `unit_measure_code` = CASE `Uni_medida`
  WHEN 'unidad' THEN '94'
  WHEN 'kilos' THEN 'KGM'
  WHEN 'gramos' THEN 'GRM'
  WHEN 'litros' THEN 'LTR'
  WHEN 'metros' THEN 'MTR'
  WHEN 'horas' THEN 'HUR'
  WHEN 'mes' THEN 'MON'
  ELSE '94'
END
WHERE `unit_measure_code` IS NULL;

-- Si el producto tenía un UNSPSC, se declara ese estándar (001) en lugar del propio (999).
UPDATE `productos` SET `standard_code` = '001' WHERE `codigo_UNSPSC` REGEXP '^[0-9]{8}$';
UPDATE `productos` SET `is_excluded` = 1 WHERE `tarifa_iva` = 0;

-- ----------------------------------------------- copia de datos desde `usuario`
INSERT INTO `cliente` (
  `identification_document_code`, `identification`, `legal_organization_code`,
  `tribute_code`, `names`, `company`, `email`, `phone`, `address`, `legacy_idusuario`
)
SELECT
  CASE
    WHEN u.`tipo_persona` = 'juridica' THEN '31'
    WHEN u.`tipo_documento` = 'TI' THEN '12'
    WHEN u.`tipo_documento` = 'CE' THEN '22'
    ELSE '13'
  END,
  u.`numero_documeto_nit`,
  IF(u.`tipo_persona` = 'juridica', '1', '2'),
  'ZZ',
  IF(u.`tipo_persona` = 'juridica', NULL, u.`nombre`),
  IF(u.`tipo_persona` = 'juridica', u.`nombre`, NULL),
  u.`correo`, u.`telefono_celular`, u.`direccion`, u.`idusuario`
FROM `usuario` u
WHERE u.`rol` = 'cliente';

INSERT INTO `trabajador` (
  `nombre`, `tipo_documento`, `documento`, `email`, `telefono`, `rol`,
  `password_hash`, `legacy_idusuario`
)
SELECT
  u.`nombre`,
  CASE u.`tipo_documento` WHEN 'TI' THEN '12' WHEN 'CE' THEN '22' ELSE '13' END,
  u.`numero_documeto_nit`, u.`correo_trabajdor`, u.`telefono_celular`, 'TRABAJADOR',
  u.`contraseña`, u.`idusuario`
FROM `usuario` u
WHERE u.`rol` = 'trabajador'
  AND u.`correo_trabajdor` IS NOT NULL
  AND u.`contraseña` IS NOT NULL;

-- ------------------------------------------------------------------------ caja
CREATE TABLE `caja` (
  `idcaja` int NOT NULL AUTO_INCREMENT,
  `idtrabajador` int NOT NULL,
  `estado` enum('ABIERTA','CERRADA') NOT NULL DEFAULT 'ABIERTA',
  `base_inicial` decimal(14,2) NOT NULL,
  `abierta_en` datetime NOT NULL,
  `cerrada_en` datetime DEFAULT NULL,
  `efectivo_esperado` decimal(14,2) DEFAULT NULL,
  `efectivo_contado` decimal(14,2) DEFAULT NULL,
  `diferencia` decimal(14,2) DEFAULT NULL,
  `observacion` varchar(255) DEFAULT NULL,
  -- Solo una caja abierta por trabajador.
  `abierta_por` int GENERATED ALWAYS AS (IF(`estado` = 'ABIERTA', `idtrabajador`, NULL)) STORED,
  PRIMARY KEY (`idcaja`),
  UNIQUE KEY `uk_caja_abierta_por` (`abierta_por`),
  KEY `idx_caja_trabajador` (`idtrabajador`),
  CONSTRAINT `fk_caja_trabajador` FOREIGN KEY (`idtrabajador`) REFERENCES `trabajador` (`idtrabajador`),
  CONSTRAINT `chk_caja_base` CHECK (`base_inicial` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ----------------------------------------------------------------------- venta
CREATE TABLE `venta` (
  `idventa` int NOT NULL AUTO_INCREMENT,
  `referencia` varchar(40) NOT NULL,
  `idcliente` int NOT NULL,
  `idtrabajador` int NOT NULL,
  `metodo_pago` enum('EFECTIVO','TRANSFERENCIA','TARJETA') NOT NULL,
  `estado` enum('PENDIENTE_PAGO','PAGADA','FACTURADA','EXPIRADA','CANCELADA','FACTURA_FALLIDA')
    NOT NULL DEFAULT 'PENDIENTE_PAGO',
  `moneda` char(3) NOT NULL DEFAULT 'COP',
  `subtotal` decimal(14,2) NOT NULL,
  `descuento_total` decimal(14,2) NOT NULL,
  `base_gravable` decimal(14,2) NOT NULL,
  `iva_total` decimal(14,2) NOT NULL,
  `total` decimal(14,2) NOT NULL,
  `idempotency_key` varchar(128) DEFAULT NULL,
  `request_hash` char(64) DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  `pagada_en` datetime DEFAULT NULL,
  `facturada_en` datetime DEFAULT NULL,
  PRIMARY KEY (`idventa`),
  UNIQUE KEY `uk_venta_referencia` (`referencia`),
  UNIQUE KEY `uk_venta_idempotency` (`idtrabajador`,`idempotency_key`),
  KEY `idx_venta_estado` (`estado`),
  KEY `idx_venta_creado_en` (`creado_en`),
  KEY `idx_venta_cliente` (`idcliente`),
  CONSTRAINT `fk_venta_cliente` FOREIGN KEY (`idcliente`) REFERENCES `cliente` (`idcliente`),
  CONSTRAINT `fk_venta_trabajador` FOREIGN KEY (`idtrabajador`) REFERENCES `trabajador` (`idtrabajador`),
  CONSTRAINT `chk_venta_total` CHECK (`total` >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Snapshot de cada producto vendido: cambios futuros del catálogo no lo alteran.
CREATE TABLE `venta_detalle` (
  `iddetalle` int NOT NULL AUTO_INCREMENT,
  `idventa` int NOT NULL,
  `idproducto` int NOT NULL,
  `code_reference` varchar(50) NOT NULL,
  `nombre` varchar(150) NOT NULL,
  `unit_measure_code` varchar(10) NOT NULL,
  `standard_code` varchar(3) NOT NULL,
  `cantidad` int NOT NULL,
  `precio_unitario` decimal(14,2) NOT NULL,
  `discount_rate` decimal(5,2) NOT NULL,
  `descuento` decimal(14,2) NOT NULL,
  `base_gravable` decimal(14,2) NOT NULL,
  `tax_code` varchar(3) NOT NULL,
  `tax_rate` decimal(5,2) NOT NULL,
  `is_excluded` tinyint(1) NOT NULL,
  `iva` decimal(14,2) NOT NULL,
  `total` decimal(14,2) NOT NULL,
  PRIMARY KEY (`iddetalle`),
  UNIQUE KEY `uk_venta_detalle_producto` (`idventa`,`idproducto`),
  KEY `idx_venta_detalle_producto` (`idproducto`),
  CONSTRAINT `fk_venta_detalle_venta` FOREIGN KEY (`idventa`) REFERENCES `venta` (`idventa`),
  CONSTRAINT `fk_venta_detalle_producto` FOREIGN KEY (`idproducto`) REFERENCES `productos` (`idproductos`),
  CONSTRAINT `chk_venta_detalle_cantidad` CHECK (`cantidad` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `venta_estado_historial` (
  `idhistorial` int NOT NULL AUTO_INCREMENT,
  `idventa` int NOT NULL,
  `estado_anterior` varchar(20) DEFAULT NULL,
  `estado_nuevo` varchar(20) NOT NULL,
  `motivo` varchar(255) DEFAULT NULL,
  `idtrabajador` int DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  PRIMARY KEY (`idhistorial`),
  KEY `idx_historial_venta` (`idventa`),
  CONSTRAINT `fk_historial_venta` FOREIGN KEY (`idventa`) REFERENCES `venta` (`idventa`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------------------------ pago
CREATE TABLE `pago` (
  `idpago` int NOT NULL AUTO_INCREMENT,
  `idventa` int NOT NULL,
  `metodo` enum('EFECTIVO','TRANSFERENCIA','TARJETA') NOT NULL,
  `canal` enum('EFECTIVO','WOMPI','BREB_MANUAL','DATAFONO') NOT NULL,
  `monto_esperado_centavos` bigint NOT NULL,
  `moneda` char(3) NOT NULL,
  `referencia` varchar(64) NOT NULL,
  `firma_integridad` char(64) NOT NULL,
  `estado` enum('PENDIENTE','APROBADO','RECHAZADO','EXPIRADO','ANULADO') NOT NULL DEFAULT 'PENDIENTE',
  `expira_en` datetime NOT NULL,
  `checkout_url` varchar(1000) DEFAULT NULL,
  `qr_payload` text,
  `qr_png_base64` mediumtext,
  `proveedor_transaccion_id` varchar(64) DEFAULT NULL,
  `proveedor_estado` varchar(30) DEFAULT NULL,
  `proveedor_metodo` varchar(40) DEFAULT NULL,
  `comprobante_numero` varchar(64) DEFAULT NULL,
  `comprobante_banco` varchar(80) DEFAULT NULL,
  `comprobante_fecha` datetime DEFAULT NULL,
  `comprobante_monto_centavos` bigint DEFAULT NULL,
  `comprobante_imagen` varchar(255) DEFAULT NULL,
  `comprobante_registrado_en` datetime DEFAULT NULL,
  `tarjeta_franquicia` varchar(30) DEFAULT NULL,
  `tarjeta_ultimos4` char(4) DEFAULT NULL,
  `tarjeta_tipo` enum('CREDITO','DEBITO') DEFAULT NULL,
  `codigo_autorizacion` varchar(30) DEFAULT NULL,
  `recibo_numero` varchar(64) DEFAULT NULL,
  `monto_recibido_centavos` bigint DEFAULT NULL,
  `cambio_centavos` bigint DEFAULT NULL,
  `idcaja` int DEFAULT NULL,
  `verificado_por` int DEFAULT NULL,
  `verificado_en` datetime DEFAULT NULL,
  `motivo_rechazo` varchar(255) DEFAULT NULL,
  `sospechoso` tinyint(1) NOT NULL DEFAULT 0,
  `creado_por` int DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`idpago`),
  UNIQUE KEY `uk_pago_referencia` (`referencia`),
  UNIQUE KEY `uk_pago_transaccion` (`proveedor_transaccion_id`),
  UNIQUE KEY `uk_pago_comprobante` (`comprobante_numero`),
  UNIQUE KEY `uk_pago_recibo` (`recibo_numero`),
  KEY `idx_pago_venta` (`idventa`),
  KEY `idx_pago_estado_expira` (`estado`,`expira_en`),
  CONSTRAINT `fk_pago_venta` FOREIGN KEY (`idventa`) REFERENCES `venta` (`idventa`),
  CONSTRAINT `fk_pago_caja` FOREIGN KEY (`idcaja`) REFERENCES `caja` (`idcaja`),
  CONSTRAINT `fk_pago_verificador` FOREIGN KEY (`verificado_por`) REFERENCES `trabajador` (`idtrabajador`),
  CONSTRAINT `chk_pago_monto` CHECK (`monto_esperado_centavos` > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Inmutabilidad: monto, moneda, referencia, firma, expiración y venta no cambian
-- nunca, y un pago en estado final no vuelve a cambiar de estado. Aplica a
-- cualquier cliente de la base (API, ORM o consola).
DELIMITER $$
CREATE TRIGGER `trg_pago_inmutable` BEFORE UPDATE ON `pago`
FOR EACH ROW
BEGIN
  IF NOT (NEW.`monto_esperado_centavos` <=> OLD.`monto_esperado_centavos`)
     OR NOT (NEW.`moneda` <=> OLD.`moneda`)
     OR NOT (NEW.`referencia` <=> OLD.`referencia`)
     OR NOT (NEW.`firma_integridad` <=> OLD.`firma_integridad`)
     OR NOT (NEW.`expira_en` <=> OLD.`expira_en`)
     OR NOT (NEW.`idventa` <=> OLD.`idventa`)
     OR NOT (NEW.`metodo` <=> OLD.`metodo`) THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'PAGO_INMUTABLE: monto, moneda, referencia, firma, expiracion y venta no se pueden modificar.';
  END IF;
  IF OLD.`estado` <> 'PENDIENTE' AND NEW.`estado` <> OLD.`estado` THEN
    SIGNAL SQLSTATE '45000'
      SET MESSAGE_TEXT = 'PAGO_FINALIZADO: un pago en estado final no puede cambiar de estado.';
  END IF;
END$$

CREATE TRIGGER `trg_pago_sin_borrado` BEFORE DELETE ON `pago`
FOR EACH ROW
BEGIN
  SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'PAGO_INMUTABLE: los pagos no se eliminan; se anulan.';
END$$
DELIMITER ;

-- Cada intento de confirmación (webhook, verificación manual, efectivo, datáfono).
CREATE TABLE `pago_intento` (
  `idintento` int NOT NULL AUTO_INCREMENT,
  `idpago` int DEFAULT NULL,
  `origen` varchar(30) NOT NULL,
  `monto_recibido_centavos` bigint DEFAULT NULL,
  `moneda` char(3) DEFAULT NULL,
  `firma_valida` tinyint(1) DEFAULT NULL,
  `monto_valido` tinyint(1) DEFAULT NULL,
  `resultado` varchar(30) NOT NULL,
  `sospechoso` tinyint(1) NOT NULL DEFAULT 0,
  `detalle` json DEFAULT NULL,
  `idtrabajador` int DEFAULT NULL,
  `ip` varchar(45) DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  PRIMARY KEY (`idintento`),
  KEY `idx_intento_pago` (`idpago`),
  KEY `idx_intento_sospechoso` (`sospechoso`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- Eventos de webhook ya recibidos (idempotencia).
CREATE TABLE `webhook_evento` (
  `idevento` int NOT NULL AUTO_INCREMENT,
  `proveedor` varchar(20) NOT NULL,
  `evento_hash` char(64) NOT NULL,
  `tipo` varchar(60) DEFAULT NULL,
  `referencia` varchar(64) DEFAULT NULL,
  `transaccion_id` varchar(64) DEFAULT NULL,
  `resultado` varchar(40) DEFAULT NULL,
  `payload` json NOT NULL,
  `creado_en` datetime NOT NULL,
  PRIMARY KEY (`idevento`),
  UNIQUE KEY `uk_webhook_evento` (`proveedor`,`evento_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------- facturación electrónica
CREATE TABLE `factura_electronica` (
  `idfactura` int NOT NULL AUTO_INCREMENT,
  `idventa` int NOT NULL,
  `idcliente` int NOT NULL,
  `idtrabajador` int NOT NULL,
  `reference_code` varchar(64) NOT NULL,
  `estado` enum('PENDIENTE','PROCESANDO','EMITIDA','FALLIDA','ANULADA') NOT NULL DEFAULT 'PENDIENTE',
  `numero` varchar(50) DEFAULT NULL,
  `prefijo` varchar(10) DEFAULT NULL,
  `cufe` varchar(255) DEFAULT NULL,
  `qr_url` text,
  `public_url` text,
  `is_validated` tinyint(1) NOT NULL DEFAULT 0,
  `validated_at` datetime DEFAULT NULL,
  `payment_method_code` varchar(5) DEFAULT NULL,
  `total` decimal(14,2) NOT NULL,
  `mensaje` varchar(500) DEFAULT NULL,
  `errores` json DEFAULT NULL,
  `payload_enviado` json DEFAULT NULL,
  `respuesta` json DEFAULT NULL,
  `intentos` int NOT NULL DEFAULT 0,
  `procesando_desde` datetime DEFAULT NULL,
  `pdf_path` varchar(255) DEFAULT NULL,
  `xml_path` varchar(255) DEFAULT NULL,
  `email_enviado_en` datetime DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`idfactura`),
  UNIQUE KEY `uk_factura_venta` (`idventa`),
  UNIQUE KEY `uk_factura_reference` (`reference_code`),
  UNIQUE KEY `uk_factura_numero` (`numero`),
  UNIQUE KEY `uk_factura_cufe` (`cufe`),
  KEY `idx_factura_estado` (`estado`),
  KEY `idx_factura_cliente` (`idcliente`),
  KEY `idx_factura_creado_en` (`creado_en`),
  CONSTRAINT `fk_factura_e_venta` FOREIGN KEY (`idventa`) REFERENCES `venta` (`idventa`),
  CONSTRAINT `fk_factura_e_cliente` FOREIGN KEY (`idcliente`) REFERENCES `cliente` (`idcliente`),
  CONSTRAINT `fk_factura_e_trabajador` FOREIGN KEY (`idtrabajador`) REFERENCES `trabajador` (`idtrabajador`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `nota_credito` (
  `idnota` int NOT NULL AUTO_INCREMENT,
  `idfactura` int NOT NULL,
  `reference_code` varchar(64) NOT NULL,
  `correction_concept_code` varchar(2) NOT NULL,
  `motivo` varchar(500) NOT NULL,
  `estado` enum('PENDIENTE','EMITIDA','FALLIDA') NOT NULL DEFAULT 'PENDIENTE',
  `numero` varchar(50) DEFAULT NULL,
  `cufe` varchar(255) DEFAULT NULL,
  `total` decimal(14,2) NOT NULL,
  `restaura_stock` tinyint(1) NOT NULL DEFAULT 0,
  `stock_restaurado` tinyint(1) NOT NULL DEFAULT 0,
  `items` json NOT NULL,
  `payload_enviado` json DEFAULT NULL,
  `respuesta` json DEFAULT NULL,
  `errores` json DEFAULT NULL,
  `idtrabajador` int NOT NULL,
  `creado_en` datetime NOT NULL,
  `actualizado_en` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`idnota`),
  UNIQUE KEY `uk_nota_reference` (`reference_code`),
  KEY `idx_nota_factura` (`idfactura`),
  CONSTRAINT `fk_nota_factura` FOREIGN KEY (`idfactura`) REFERENCES `factura_electronica` (`idfactura`),
  CONSTRAINT `fk_nota_trabajador` FOREIGN KEY (`idtrabajador`) REFERENCES `trabajador` (`idtrabajador`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- ------------------------------------------------------- catálogos y auditoría
CREATE TABLE `factus_catalogo` (
  `tipo` varchar(40) NOT NULL,
  `datos` json NOT NULL,
  `actualizado_en` datetime NOT NULL,
  PRIMARY KEY (`tipo`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `auditoria` (
  `idauditoria` bigint NOT NULL AUTO_INCREMENT,
  `entidad` varchar(40) NOT NULL,
  `entidad_id` varchar(40) NOT NULL,
  `accion` varchar(40) NOT NULL,
  `idtrabajador` int DEFAULT NULL,
  `datos` json DEFAULT NULL,
  `creado_en` datetime NOT NULL,
  PRIMARY KEY (`idauditoria`),
  KEY `idx_auditoria_entidad` (`entidad`,`entidad_id`),
  KEY `idx_auditoria_trabajador` (`idtrabajador`),
  KEY `idx_auditoria_creado_en` (`creado_en`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
