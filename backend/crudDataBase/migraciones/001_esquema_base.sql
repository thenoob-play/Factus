-- 001: esquema original del proyecto (categoria, usuario, productos, compra,
-- compra_detalle, factura). Usa IF NOT EXISTS: en una base ya creada no cambia nada.

CREATE TABLE IF NOT EXISTS `categoria` (
  `idcategoria` int NOT NULL AUTO_INCREMENT,
  `nombre_categoria` varchar(45) NOT NULL,
  PRIMARY KEY (`idcategoria`),
  UNIQUE KEY `nombre_UNIQUE` (`nombre_categoria`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `usuario` (
  `idusuario` int NOT NULL AUTO_INCREMENT,
  `tipo_persona` enum('natural','juridica') NOT NULL,
  `tipo_documento` enum('CC','TI','CE') DEFAULT NULL,
  `numero_documeto_nit` varchar(20) NOT NULL,
  `nombre` varchar(70) NOT NULL,
  `correo` varchar(45) NOT NULL,
  `direccion` varchar(45) NOT NULL,
  `municipio_departamento` varchar(45) NOT NULL,
  `telefono_celular` varchar(45) NOT NULL,
  `rol` enum('trabajador','cliente') NOT NULL,
  `contraseña` varchar(255) DEFAULT NULL,
  `correo_trabajdor` varchar(45) DEFAULT NULL,
  PRIMARY KEY (`idusuario`),
  UNIQUE KEY `numero_documeto_UNIQUE` (`numero_documeto_nit`),
  UNIQUE KEY `correo_UNIQUE` (`correo`),
  UNIQUE KEY `telefono_celular_UNIQUE` (`telefono_celular`),
  UNIQUE KEY `correo_trabajdor_UNIQUE` (`correo_trabajdor`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `productos` (
  `idproductos` int NOT NULL AUTO_INCREMENT,
  `idcategoria` int NOT NULL,
  `codigo_interno` varchar(50) DEFAULT NULL,
  `codigo_UNSPSC` varchar(8) NOT NULL,
  `nombre` varchar(100) NOT NULL,
  `descripcion` varchar(255) DEFAULT NULL,
  `Uni_medida` enum('unidad','kilos','gramos','litros','metros','horas','servicio','mes','otro') NOT NULL,
  `cantidad` int NOT NULL DEFAULT '0',
  `precio_unitario` decimal(12,2) NOT NULL,
  `descuento` decimal(12,2) DEFAULT '0.00',
  `tarifa_iva` decimal(5,2) NOT NULL DEFAULT '19.00',
  `URL_imagen` varchar(255) NOT NULL,
  PRIMARY KEY (`idproductos`),
  UNIQUE KEY `uk_codigo_interno` (`codigo_interno`),
  KEY `idx_unspsc` (`codigo_UNSPSC`),
  KEY `idx_nombre` (`nombre`),
  KEY `fk_productos_categoria_idx` (`idcategoria`),
  CONSTRAINT `fk_productos_categoria` FOREIGN KEY (`idcategoria`)
    REFERENCES `categoria` (`idcategoria`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `compra` (
  `idcompra` int NOT NULL AUTO_INCREMENT,
  `idusuario` int NOT NULL,
  `fecha_compra` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `idempotency_key` varchar(128) DEFAULT NULL,
  `request_hash` char(64) DEFAULT NULL,
  `factus_reference_code` varchar(64) DEFAULT NULL,
  `factus_source` json DEFAULT NULL,
  `factus_payload` json DEFAULT NULL,
  `factus_totales` json DEFAULT NULL,
  `factus_response` json DEFAULT NULL,
  `factus_estado` enum('pendiente','error','emitida') NOT NULL DEFAULT 'pendiente',
  PRIMARY KEY (`idcompra`),
  UNIQUE KEY `uk_compra_idempotency` (`idusuario`,`idempotency_key`),
  KEY `fk_compra_usuario_idx` (`idusuario`),
  CONSTRAINT `fk_compra_usuario` FOREIGN KEY (`idusuario`)
    REFERENCES `usuario` (`idusuario`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `compra_detalle` (
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
    REFERENCES `compra` (`idcompra`) ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT `fk_compra_detalle_producto` FOREIGN KEY (`idproducto`)
    REFERENCES `productos` (`idproductos`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `factura` (
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
    REFERENCES `compra` (`idcompra`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
