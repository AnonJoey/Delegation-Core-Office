"""Limite de taxa por (cliente, ferramenta), em janela deslizante, so na memoria.

Na memoria de proposito: o limite protege o daemon de um agente em laco, e um
reinicio do daemon ja interrompe o laco. Gravar em disco a cada chamada custaria
mais que o que protege.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class LimiteDeTaxa:
    def __init__(self, relogio=time.monotonic):
        self._relogio = relogio
        self._janelas: dict[tuple[str, str], deque] = {}
        self._trava = threading.Lock()

    def tentar(self, cliente: str, ferramenta: str, maximo: int, segundos: int) -> float:
        """0 se a chamada cabe (e conta). Senao, quantos segundos faltam para caber."""
        agora = self._relogio()
        with self._trava:
            fila = self._janelas.setdefault((cliente, ferramenta), deque())
            while fila and agora - fila[0] >= segundos:
                fila.popleft()
            if len(fila) >= maximo:
                return round(segundos - (agora - fila[0]), 3)
            fila.append(agora)
            return 0.0
