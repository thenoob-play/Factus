import re
from typing import Optional

# ---------------------------------------------------------------------------
# CONFIGURACIÓN (ajústala a tu negocio)
# ---------------------------------------------------------------------------

# Prefijo que debe tener el código interno según la categoría.
# Ej: categoría 1 = Tecnología -> "TEC-000123"
PREFIJOS_POR_CATEGORIA = {
    1: "TEC",
    2: "ALI",
    3: "ASE",
    4: "PAP",
}

# Segmentos (primeros 2 dígitos) de UNSPSC que existen oficialmente
SEGMENTOS_UNSPSC_VALIDOS = (
    set(range(10, 16)) | set(range(20, 28)) | set(range(30, 33))
    | set(range(39, 61)) | set(range(70, 74)) | {76}
    | set(range(78, 87)) | set(range(90, 96))
)

# Qué segmentos UNSPSC son coherentes con cada categoría de TU negocio.
SEGMENTOS_POR_CATEGORIA = {
    1: {43, 44, 45, 52},   # Tecnología, equipos de oficina, electrodomésticos
    2: {50},               # Alimentos
    3: {47, 53},           # Aseo / limpieza
    4: {14, 44},           # Papelería
}

# Catálogo oficial UNSPSC (código -> descripción). Cárgalo desde el CSV/Excel
# oficial o desde una tabla en tu BD. Si está vacío, se omite esta verificación.
CATALOGO_UNSPSC: dict[str, str] = {
    # "43211503": "Computadores portátiles",
}

UNIDADES_MEDIDA_VALIDAS = {"UND", "KG", "GR", "LT", "ML", "MT", "CM", "CJ", "PAQ"}
TARIFAS_IVA_VALIDAS = {0, 5, 19}   # Colombia


# ---------------------------------------------------------------------------
# VALIDACIÓN CÓDIGO INTERNO
# ---------------------------------------------------------------------------
def validar_codigo_interno(codigo: str, idcategoria: int, existe_en_bd=None) -> str:
    """
    Formato esperado: PREFIJO-NNNNNN  (ej: TEC-000123)
    - Prefijo de 3 letras mayúsculas, que corresponda a la categoría.
    - Guion y entre 3 y 6 dígitos.
    - `existe_en_bd`: función opcional que recibe el código y devuelve True si ya existe.
    """
    if not isinstance(codigo, str):
        raise ValueError("El 'codigo_interno' debe ser texto.")

    codigo = codigo.strip().upper()

    if not re.fullmatch(r"[A-Z]{3}-\d{3,6}", codigo):
        raise ValueError(
            "El 'codigo_interno' debe tener el formato AAA-000123 "
            "(3 letras, guion y de 3 a 6 dígitos)."
        )

    prefijo = codigo.split("-")[0]
    esperado = PREFIJOS_POR_CATEGORIA.get(idcategoria)
    if esperado is None:
        raise ValueError(f"La categoría {idcategoria} no tiene un prefijo configurado.")
    if prefijo != esperado:
        raise ValueError(
            f"El prefijo '{prefijo}' no corresponde a la categoría {idcategoria} "
            f"(se esperaba '{esperado}')."
        )

    if existe_en_bd and existe_en_bd(codigo):
        raise ValueError(f"El 'codigo_interno' {codigo} ya existe.")

    return codigo


# ---------------------------------------------------------------------------
# VALIDACIÓN CÓDIGO UNSPSC
# ---------------------------------------------------------------------------
def _palabras(texto: str) -> set:
    return {p for p in re.findall(r"[a-záéíóúñ]+", texto.lower()) if len(p) > 3}


def validar_codigo_unspsc(codigo, idcategoria: int, nombre: str, descripcion: str) -> str:
    """
    UNSPSC = 8 dígitos: Segmento(2) Familia(2) Clase(2) Producto(2).
    """
    codigo = str(codigo).strip()

    if not re.fullmatch(r"\d{8}", codigo):
        raise ValueError("El 'codigo_UNSPSC' debe tener exactamente 8 dígitos numéricos.")

    segmento, familia, clase, producto = (int(codigo[i:i + 2]) for i in range(0, 8, 2))

    if segmento not in SEGMENTOS_UNSPSC_VALIDOS:
        raise ValueError(f"El segmento {segmento:02d} no existe en el estándar UNSPSC.")

    # Para un producto concreto, ningún nivel puede ser 00
    if 0 in (familia, clase, producto):
        raise ValueError("El 'codigo_UNSPSC' debe llegar hasta nivel de producto (sin niveles en 00).")

    # Coherencia con la categoría del negocio
    permitidos = SEGMENTOS_POR_CATEGORIA.get(idcategoria)
    if permitidos and segmento not in permitidos:
        raise ValueError(
            f"El segmento UNSPSC {segmento:02d} no es coherente con la categoría {idcategoria}."
        )

    # Coherencia con el nombre/descripción usando el catálogo oficial
    if CATALOGO_UNSPSC:
        if codigo not in CATALOGO_UNSPSC:
            raise ValueError(f"El código UNSPSC {codigo} no existe en el catálogo.")
        if not (_palabras(CATALOGO_UNSPSC[codigo]) & _palabras(f"{nombre} {descripcion}")):
            raise ValueError(
                f"El código UNSPSC {codigo} ('{CATALOGO_UNSPSC[codigo]}') "
                "no parece corresponder al nombre/descripción del producto."
            )

    return codigo


# ---------------------------------------------------------------------------
# FUNCIÓN PRINCIPAL
# ---------------------------------------------------------------------------
def validar_producto(datos_dict: dict, existe_codigo_en_bd=None) -> dict:
    try:
        campos = [
            "idcategoria", "codigo_interno", "codigo_UNSPSC", "nombre", "descripcion",
            "Uni_medida", "cantidad", "precio_unitario", "descuento", "tarifa_iva", "URL_imagen",
        ]

        # Obligatorios (0 es válido en numéricos, por eso comparo con None / vacío)
        faltantes = [
            c for c in campos
            if datos_dict.get(c) is None
            or (isinstance(datos_dict.get(c), str) and not datos_dict[c].strip())
        ]
        if faltantes:
            raise ValueError(f"Campos obligatorios faltantes: {', '.join(faltantes)}.")

        idcategoria = datos_dict["idcategoria"]
        nombre = str(datos_dict["nombre"]).strip()
        descripcion = str(datos_dict["descripcion"]).strip()
        uni_medida = str(datos_dict["Uni_medida"]).strip().upper()
        cantidad = datos_dict["cantidad"]
        precio = datos_dict["precio_unitario"]
        descuento = datos_dict["descuento"]
        tarifa_iva = datos_dict["tarifa_iva"]
        url_imagen = str(datos_dict["URL_imagen"]).strip()

        # Tipos
        if isinstance(idcategoria, bool) or not isinstance(idcategoria, int) or idcategoria <= 0:
            raise ValueError("El campo 'idcategoria' debe ser un número entero positivo.")

        for campo, valor in (("cantidad", cantidad), ("precio_unitario", precio),
                             ("descuento", descuento), ("tarifa_iva", tarifa_iva)):
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                raise ValueError(f"El campo '{campo}' debe ser numérico.")

        # Rangos
        if not (3 <= len(nombre) <= 150):
            raise ValueError("El 'nombre' debe tener entre 3 y 150 caracteres.")
        if len(descripcion) < 10:
            raise ValueError("La 'descripcion' debe tener al menos 10 caracteres.")
        if uni_medida not in UNIDADES_MEDIDA_VALIDAS:
            raise ValueError(f"'Uni_medida' inválida. Opciones: {sorted(UNIDADES_MEDIDA_VALIDAS)}.")
        if cantidad < 0:
            raise ValueError("La 'cantidad' no puede ser negativa.")
        if precio <= 0:
            raise ValueError("El 'precio_unitario' debe ser mayor que 0.")
        if not (0 <= descuento <= 100):
            raise ValueError("El 'descuento' debe estar entre 0 y 100.")
        if tarifa_iva not in TARIFAS_IVA_VALIDAS:
            raise ValueError(f"'tarifa_iva' inválida. Opciones: {sorted(TARIFAS_IVA_VALIDAS)}.")
        if not re.fullmatch(r"https?://\S+\.(jpg|jpeg|png|webp|gif)(\?\S*)?", url_imagen, re.I):
            raise ValueError("La 'URL_imagen' debe ser una URL http(s) a una imagen (jpg, png, webp, gif).")

        # Validación de los dos códigos
        codigo_interno = validar_codigo_interno(
            datos_dict["codigo_interno"], idcategoria, existe_codigo_en_bd
        )
        codigo_unspsc = validar_codigo_unspsc(
            datos_dict["codigo_UNSPSC"], idcategoria, nombre, descripcion
        )

        dato = {
            "idcategoria": idcategoria,
            "codigo_interno": codigo_interno,
            "codigo_UNSPSC": codigo_unspsc,
            "nombre": nombre,
            "descripcion": descripcion,
            "Uni_medida": uni_medida,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "descuento": descuento,
            "tarifa_iva": tarifa_iva,
            "URL_imagen": url_imagen,
        }
        return {"estado": True, "dato": dato}

    except ValueError as e:
        return {"estado": False, "error": str(e)}