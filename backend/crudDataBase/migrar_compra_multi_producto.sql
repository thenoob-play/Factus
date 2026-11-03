-- Ejecutar una sola vez sobre una base existente y después de hacer un respaldo.
-- Conserva las líneas de compra actuales antes de separar cabecera y detalle.
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

INSERT INTO `compra_detalle` (
  `idcompra`, `idproducto`, `cantidad`, `precio_unitario`, `subtotal`
)
SELECT `idcompra`, `idproductos`, `cantidad`, `precio_unitario`, `subtotal`
FROM `compra`;

ALTER TABLE `compra`
  DROP FOREIGN KEY `fk_compra_productos`,
  DROP INDEX `fk_compra_productos_idx`,
  DROP COLUMN `idproductos`,
  DROP COLUMN `cantidad`,
  DROP COLUMN `precio_unitario`,
  DROP COLUMN `subtotal`;
