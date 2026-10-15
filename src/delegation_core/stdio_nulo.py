"""Da destino a stdout e stderr quando o processo nasce sem eles.

`pythonw.exe`, o daemon do Windows sem janela de console, parte com `sys.stdout`,
`sys.stderr` e `sys.stdin` valendo `None`. Muita coisa tolera isso (o `print` nao faz
nada), mas o uvicorn pergunta `sys.stdout.isatty()` ao montar o log e cai com
`Unable to configure formatter 'default'`: medido em 15/10/2026, o daemon sai com codigo 1
na partida, e o traceback, escrito num stderr que nao existe, some. O daemon nao sobe e
ninguem sabe por que.

A saida comum vai para o nulo. A de erro vai para `daemon-stderr.log`, ao lado do
`server.log`, para o que escapar do logging (o proprio uvicorn escreve ali). Esse arquivo
tem teto: sem console, nada o esvazia, e o `logging` do daemon tambem escreve no stderr.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

LIMITE_DO_ARQUIVO = 5 * 1024 * 1024


class _Nulo:
    """Descarta o que recebe, e diz que nao e um terminal.

    Nao e `open(os.devnull)`: no Windows `NUL` e um dispositivo de caracteres e
    `isatty()` responde True (medido no CI, Python 3.12), entao o uvicorn ligaria as cores
    e escreveria sequencias ANSI no nada. Aqui `isatty()` e False nas tres plataformas.
    """

    encoding = "utf-8"
    errors = "replace"

    def write(self, texto: str) -> int:
        return len(texto)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


class _ArquivoComTeto:
    """Arquivo de texto que nunca passa de `limite` bytes: ao estourar, o atual vira `.1`."""

    encoding = "utf-8"
    errors = "replace"

    def __init__(self, caminho: Path, limite: int = LIMITE_DO_ARQUIVO):
        self._caminho = Path(caminho)
        self._limite = limite
        self._trava = threading.Lock()
        self._abrir()

    def _abrir(self) -> None:
        self._arquivo = open(self._caminho, "a", encoding="utf-8", errors="replace", buffering=1)
        self._tamanho = self._caminho.stat().st_size

    def write(self, texto: str) -> int:
        if not texto:
            return 0
        with self._trava:
            if self._tamanho + len(texto) > self._limite:
                self._arquivo.close()
                os.replace(self._caminho, self._caminho.with_name(self._caminho.name + ".1"))
                self._abrir()
            self._arquivo.write(texto)
            self._tamanho += len(texto)
        return len(texto)

    def flush(self) -> None:
        with self._trava:
            self._arquivo.flush()

    def close(self) -> None:
        with self._trava:
            self._arquivo.close()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def garantir_stdio() -> None:
    """Troca por um destino real o stdout, o stderr e o stdin que forem `None`."""
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8")
    if sys.stdout is not None and sys.stderr is not None:
        return
    if sys.stdout is None:
        sys.stdout = _Nulo()
    if sys.stderr is None:
        from .config import CONFIG_DIR
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            sys.stderr = _ArquivoComTeto(CONFIG_DIR / "daemon-stderr.log")
        except OSError:
            sys.stderr = _Nulo()
