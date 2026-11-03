from pydantic import BaseModel, EmailStr, Field

"""
tabla usuario
CREATE TABLE `usuario` (
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci

"""

class UsuarioClienteCreate(BaseModel):
    
    tipo_persona: str
    tipo_documento: str
    numero_documeto_nit: str
    nombre: str
    correo: EmailStr
    direccion: str
    municipio_departamento: str
    telefono_celular: str
    rol: str #solo puedes ser cliente
    
class UsuarioTrabajadorCreate(BaseModel):
    
    tipo_persona: str
    tipo_documento: str
    numero_documeto_nit: str
    nombre: str
    correo: EmailStr
    direccion: str
    municipio_departamento: str
    telefono_celular: str
    rol: str #solo puedes ser trabajador
    correotrabajador: EmailStr
    contraseña: str = Field(min_length=8)

class loginUsarioCreate(BaseModel):
    correo: str
    contraseña: str = Field(min_length=1)