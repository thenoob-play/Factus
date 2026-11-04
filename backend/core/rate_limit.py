"""Rate limiting en memoria (ventana deslizante) para login y webhooks.

Es suficiente para una sola instancia. Con varias réplicas detrás de un balanceador
habría que moverlo a un almacén compartido (p. ej. Redis).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from backend.core.errores import DemasiadasPeticionesError


class LimitadorVentana:
    def __init__(self, limite: int, ventana_segundos: int):
        self.limite = limite
        self.ventana = ventana_segundos
        self._eventos: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def verificar(self, clave: str) -> None:
        ahora = time.monotonic()
        with self._lock:
            eventos = self._eventos[clave]
            while eventos and ahora - eventos[0] > self.ventana:
                eventos.popleft()
            if len(eventos) >= self.limite:
                espera = int(self.ventana - (ahora - eventos[0])) + 1
                raise DemasiadasPeticionesError(
                    "Demasiadas peticiones. Intenta de nuevo más tarde.",
                    detalles={"reintentar_en_segundos": espera},
                )
            eventos.append(ahora)

    def reiniciar(self, clave: str | None = None) -> None:
        with self._lock:
            if clave is None:
                self._eventos.clear()
            else:
                self._eventos.pop(clave, None)


def ip_cliente(request: Request) -> str:
    return request.client.host if request.client else "desconocido"
