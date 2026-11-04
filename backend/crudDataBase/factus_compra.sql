CREATE DATABASE  IF NOT EXISTS `factus` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;
USE `factus`;
-- MySQL dump 10.13  Distrib 8.0.45, for Win64 (x86_64)
--
-- Host: localhost    Database: factus
-- ------------------------------------------------------
-- Server version	9.6.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
SET @MYSQLDUMP_TEMP_LOG_BIN = @@SESSION.SQL_LOG_BIN;
SET @@SESSION.SQL_LOG_BIN= 0;

--
-- GTID state at the beginning of the backup 
--

SET @@GLOBAL.GTID_PURGED=/*!80000 '+'*/ 'd40ec8a6-2467-11f1-b260-489ebdf55486:1-1119';

--
-- Table structure for table `compra`
--

DROP TABLE IF EXISTS `compra`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `compra` (
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
  CONSTRAINT `fk_compra_usuario` FOREIGN KEY (`idusuario`) REFERENCES `usuario` (`idusuario`) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `compra`
--

LOCK TABLES `compra` WRITE;
/*!40000 ALTER TABLE `compra` DISABLE KEYS */;
INSERT INTO `compra` VALUES (1,1,'2026-11-03 20:24:39','compra-2026-001','b1416ad4df635e2d70ebc8fd0cf42c1acb676057a3319b54b3a43b9cff833d73','FAC-1-4584348c10ca36ab44bacc3f33188b76','{\"usuario\": {\"correo\": \"julian@gmail.com\", \"nombre\": \"Julian Benavides\", \"direccion\": \"Calle 10 # 20-30\", \"tipo_persona\": \"natural\", \"tipo_documento\": \"CC\", \"telefono_celular\": \"3001234567\", \"numero_documeto_nit\": \"1002938485\", \"municipio_departamento\": \"Bogotá D.C.\"}, \"productos\": [{\"cantidad\": 2, \"producto\": {\"nombre\": \"Leche Entera Alquería 1 Litro\", \"cantidad\": 50, \"descuento\": \"0.00\", \"Uni_medida\": \"litros\", \"tarifa_iva\": \"19.00\", \"idproductos\": 1, \"codigo_UNSPSC\": \"50101501\", \"codigo_interno\": \"PROD-ABC-001\", \"precio_unitario\": \"4500.00\"}}, {\"cantidad\": 1, \"producto\": {\"nombre\": \"cafe jskf 1 Litro\", \"cantidad\": 50, \"descuento\": \"0.00\", \"Uni_medida\": \"litros\", \"tarifa_iva\": \"19.00\", \"idproductos\": 3, \"codigo_UNSPSC\": \"50101501\", \"codigo_interno\": \"PROD-ABC-002\", \"precio_unitario\": \"6500.00\"}}]}',NULL,NULL,NULL,'pendiente');
/*!40000 ALTER TABLE `compra` ENABLE KEYS */;
UNLOCK TABLES;
SET @@SESSION.SQL_LOG_BIN = @MYSQLDUMP_TEMP_LOG_BIN;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-03 15:28:12
