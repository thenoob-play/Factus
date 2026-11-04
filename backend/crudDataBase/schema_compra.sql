CREATE TABLE `compra` (
  `idcompra` int NOT NULL AUTO_INCREMENT,
  `idusuario` int NOT NULL,
  `idempotency_key` varchar(128) DEFAULT NULL,
  `request_hash` char(64) DEFAULT NULL,
  `factus_reference_code` varchar(64) DEFAULT NULL,
  `factus_source` json DEFAULT NULL,
  `factus_payload` json DEFAULT NULL,
  `factus_totales` json DEFAULT NULL,
  `factus_response` json DEFAULT NULL,
  `factus_estado` enum('pendiente','error','emitida') NOT NULL DEFAULT 'pendiente',
  `fecha_compra` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`idcompra`),
  UNIQUE KEY `uk_compra_idempotency` (`idusuario`,`idempotency_key`),
  KEY `fk_compra_usuario_idx` (`idusuario`),
  CONSTRAINT `fk_compra_usuario` FOREIGN KEY (`idusuario`)
    REFERENCES `usuario` (`idusuario`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `compra_detalle` (
  `iddetalle` int NOT NULL AUTO_INCREMENT,
  `idcompra` int NOT NULL,
  `idproducto` int NOT NULL,
  `cantidad` int NOT NULL,
  `precio_unitario` decimal(12,2) NOT NULL,
  `subtotal` decimal(12,2) NOT NULL,
  PRIMARY KEY (`iddetalle`),
  KEY `fk_compra_detalle_compra_idx` (`idcompra`),
  KEY `fk_compra_detalle_producto_idx` (`idproducto`),
  CONSTRAINT `fk_compra_detalle_compra` FOREIGN KEY (`idcompra`)
    REFERENCES `compra` (`idcompra`)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_compra_detalle_producto` FOREIGN KEY (`idproducto`)
    REFERENCES `productos` (`idproductos`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `factura` (
  `idfactura` int NOT NULL AUTO_INCREMENT,
  `idcompra` int NOT NULL,
  `prefijo` varchar(10) DEFAULT NULL,
  `numero_factura` varchar(50) NOT NULL,
  `cufe` varchar(255) NOT NULL,
  `fecha_emision` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `fecha_validacion_dian` datetime DEFAULT NULL,
  `total_bruto` decimal(12,2) NOT NULL,
  `total_descuentos` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_iva` decimal(12,2) NOT NULL DEFAULT '0.00',
  `total_neto` decimal(12,2) NOT NULL,
  `qr_dian` text,
  `estado_dian` enum('pendiente','autorizada','rechazada') NOT NULL DEFAULT 'pendiente',
  PRIMARY KEY (`idfactura`),
  UNIQUE KEY `uk_idcompra` (`idcompra`),
  UNIQUE KEY `uk_cufe` (`cufe`),
  UNIQUE KEY `uk_numero_factura` (`prefijo`,`numero_factura`),
  CONSTRAINT `fk_factura_compra` FOREIGN KEY (`idcompra`)
    REFERENCES `compra` (`idcompra`)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
