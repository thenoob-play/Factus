from pydantic import BaseModel, EmailStr, Field

"""CREATE TABLE `productos` (
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
  CONSTRAINT `fk_productos_categoria` FOREIGN KEY (`idcategoria`) REFERENCES `categoria` (`idcategoria`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
"""


class ProductoCreate(BaseModel):
    idcategoria: int
    codigo_interno: str
    codigo_UNSPSC: str
    nombre: str
    descripcion: str
    Uni_medida: str
    cantidad: int
    precio_unitario: float
    descuento: float
    tarifa_iva: float
    URL_imagen: str