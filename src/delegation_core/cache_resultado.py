"""Cache de resultado do modelo local, por identidade exata da entrada.

Trazido dos snapshots do REA: um resultado so e reusado quando TUDO que o
produziu e igual (texto do prompt, system, limite de tokens, temperatura,
modelo e idioma). Mudou um byte, e outra chave. Nada que muda estado entra:
so `compress`, que e funcao pura da entrada.

O modelo entra na chave pelo caminho, tamanho e data do arquivo: trocar o
GGUF invalida tudo sem ninguem precisar lembrar de limpar.

Guarda no maximo `MAXIMO` entradas (as mais antigas de uso saem primeiro), em
SQLite em CONFIG_DIR. Resultado ruim (marcado `poor`) nao entra.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

MAXIMO = 2000
_TRAVA = threading.Lock()
_CONEXOES: dict[str, sqlite3.Connection] = {}


def _con() -> sqlite3.Connection:
    from . import config
    caminho = str(config.CONFIG_DIR / "cache_resultados.sqlite3")
    if caminho not in _CONEXOES:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(caminho, check_same_thread=False)
        c.execute("CREATE TABLE IF NOT EXISTS r (chave TEXT PRIMARY KEY, valor TEXT, usado REAL, criado REAL)")
        _CONEXOES[caminho] = c
    return _CONEXOES[caminho]


def identidade_do_modelo(cfg) -> str:
    m = str(getattr(cfg, "llama_model", "") or "")
    try:
        st = Path(m).stat()
        return f"{m}|{st.st_size}|{int(st.st_mtime)}"
    except OSError:
        return m


def chave(operacao: str, **partes) -> str:
    texto = json.dumps({"op": operacao, **partes}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ler(k: str) -> str | None:
    with _TRAVA:
        c = _con()
        linha = c.execute("SELECT valor FROM r WHERE chave = ?", (k,)).fetchone()
        if linha:
            c.execute("UPDATE r SET usado = ? WHERE chave = ?", (time.time(), k))
            c.commit()
        return linha[0] if linha else None


def gravar(k: str, valor: str) -> None:
    agora = time.time()
    with _TRAVA:
        c = _con()
        c.execute("INSERT OR REPLACE INTO r VALUES (?, ?, ?, ?)", (k, valor, agora, agora))
        n = c.execute("SELECT COUNT(*) FROM r").fetchone()[0]
        if n > MAXIMO:
            c.execute("DELETE FROM r WHERE chave IN (SELECT chave FROM r ORDER BY usado LIMIT ?)", (n - MAXIMO,))
        c.commit()


def limpar() -> int:
    with _TRAVA:
        c = _con()
        n = c.execute("SELECT COUNT(*) FROM r").fetchone()[0]
        c.execute("DELETE FROM r")
        c.commit()
        return n
