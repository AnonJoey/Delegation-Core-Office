"""A camada do RTK em volta do filtro: perda, recuperacao e a guarda "nunca pior".

Porte do caminho TOML de `src/main.rs` (`run_fallback`), `core/tee.rs`,
`core/retriever.rs` (modo sqlite, o padrao) e `core/guard.rs`:

- O filtro informa se perdeu linhas e de que jeito (`perda`): nenhuma, uma
  cauda contigua (da para recuperar "da linha N em diante") ou o texto todo.
- Se perdeu, a saida original vai para `saidas.sqlite3` e a resposta ganha uma
  linha `[full output: <prefixo> recall <hash>]` ou `[+N hidden: <prefixo>
  recall <hash>]`. Comando que falhou (codigo != 0) com 500 bytes ou mais
  tambem e guardado.
- Se perdeu e nao deu para guardar, mostra o original: nunca um corte sem volta.
- Guarda "nunca pior": se o resultado (com a dica) estimar mais tokens que o
  original (bytes/4, para cima), mostra o original.

O hash e o do RTK: sha256(comando + byte 0 + conteudo), 12 primeiros hex.
"""

from __future__ import annotations

import hashlib
import logging
import math
import sqlite3
import threading
import time
from pathlib import Path

from .motor import Filtro, _linhas, _truncar, _ANSI

logger = logging.getLogger("filtros_saida")

MIN_BYTES_FALHA = 500
# Quanto cada processo espera o arquivo de saidas destravar antes de desistir. O `shell` roda a
# cada comando Bash do agente, sempre como processo novo, e varios podem chegar juntos.
BUSY_TIMEOUT_MS = 5000
_TRAVA = threading.Lock()
_CON: dict[str, sqlite3.Connection] = {}

# ── escritor unico (item 6.1.2) ──
# So o daemon grava em `saidas.sqlite3`. Os outros processos pedem a ele (`cliente_fino`) e so
# gravam por conta propria quando ele nao atende (desligado, outra maquina, versao antiga).
# Os workers do pool de compressao nao gravam nem pedem: juntam o que guardariam (`_COLETOR`) e o
# daemon grava quando o resultado volta (`compressao.pool`).
_ESCRITOR = False
_COLETOR: list | None = None


def marcar_escritor() -> None:
    """Chamado uma vez pelo daemon ao subir: este processo passa a ser o escritor de `saidas.sqlite3`."""
    global _ESCRITOR
    _ESCRITOR = True


def e_escritor() -> bool:
    return _ESCRITOR


def tokens(texto: str) -> int:
    return math.ceil(len(texto.encode("utf-8")) / 4)


def aplicar_com_info(f: Filtro, saida: str):
    """(texto, perda). perda: ("none",), ("tail", payload, a_partir_da_linha) ou ("whole",)."""
    linhas = _linhas(saida)
    if f.strip_ansi:
        linhas = [_ANSI.sub("", l) for l in linhas]
    if f.replace:
        novas = []
        for l in linhas:
            for padrao, rep in f.replace:
                l = padrao.sub(rep, l)
            novas.append(l)
        linhas = novas
    if f.match_output:
        texto = "\n".join(linhas)
        for padrao, mensagem, salvo in f.match_output:
            if padrao.search(texto):
                if salvo is not None and salvo.search(texto):
                    continue
                return mensagem, ("whole",)
    if f.strip:
        linhas = [l for l in linhas if not any(p.search(l) for p in f.strip)]
    elif f.keep:
        linhas = [l for l in linhas if any(p.search(l) for p in f.keep)]
    perda_na_linha = False
    if f.truncate_lines_at is not None:
        novas = []
        for l in linhas:
            t = _truncar(l, f.truncate_lines_at)
            perda_na_linha |= t != l
            novas.append(t)
        linhas = novas
    foto = None
    if not perda_na_linha and f.tail_lines is None and (f.head_lines is not None or f.max_lines is not None):
        foto = list(linhas)
    total = len(linhas)
    h, t = f.head_lines, f.tail_lines
    salto = False
    corte_head = corte_max = None
    if h is not None and t is not None:
        if total > h + t:
            linhas = linhas[:h] + [f"... ({total - h - t} lines omitted)"] + linhas[total - t:]
            salto = True
    elif h is not None:
        if total > h:
            linhas = linhas[:h] + [f"... ({total - h} lines omitted)"]
            corte_head = h
    elif t is not None and total > t:
        omitidas = total - t
        linhas = [f"... ({omitidas} lines omitted)"] + linhas[omitidas:]
        salto = True
    if f.max_lines is not None and len(linhas) > f.max_lines:
        cortadas = len(linhas) - f.max_lines
        linhas = linhas[: f.max_lines] + [f"... ({cortadas} lines truncated)"]
        corte_max = f.max_lines
    resultado = "\n".join(linhas)
    if not resultado.strip() and f.on_empty is not None:
        return f.on_empty, ("none",)
    if foto is not None:
        if corte_head is not None and corte_max is not None:
            return resultado, ("whole",)
        if corte_head is not None:
            return resultado, ("tail", "\n".join(foto), corte_head + 1)
        if corte_max is not None:
            return resultado, ("tail", "\n".join(foto), corte_max + 1)
        return resultado, ("none",)
    if salto or perda_na_linha or corte_head is not None or corte_max is not None:
        return resultado, ("whole",)
    return resultado, ("none",)


# ── guarda das saidas originais ─────────────────────────────────────────────

def _con() -> sqlite3.Connection:
    from .. import config
    caminho = str(config.CONFIG_DIR / "saidas.sqlite3")
    if caminho not in _CON:
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(caminho, check_same_thread=False, timeout=BUSY_TIMEOUT_MS / 1000)
        c.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        # WAL: quem le nao trava quem escreve, e o commit deixa de fazer fsync do arquivo inteiro. Medido
        # com 60 shell em paralelo contra um escritor continuo, em disco real: sem WAL falhava a maior
        # parte das chamadas com `database is locked`. O modo fica gravado no arquivo.
        try:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.Error as e:  # noqa: BLE001 - sistema de arquivos sem memoria compartilhada: segue como estava
            logger.warning("saidas.sqlite3 sem WAL: %s", e)
        c.execute("CREATE TABLE IF NOT EXISTS s (hash TEXT PRIMARY KEY, comando TEXT, conteudo BLOB, "
                  "total INTEGER, mostrado_ate INTEGER, codigo INTEGER, criado REAL)")
        _CON[caminho] = c
    return _CON[caminho]


def contar_linhas(b: bytes) -> int:
    if not b:
        return 0
    n = b.count(b"\n")
    return n if b.endswith(b"\n") else n + 1


def guardar(conteudo: str, comando: str, codigo: int | None = None, mostrado_ate: int = 1) -> dict | None:
    b = conteudo.encode("utf-8")
    if not b:
        return None
    h = hashlib.sha256(comando.encode("utf-8") + b"\x00" + b).hexdigest()[:12]
    total = contar_linhas(b)
    if not _ESCRITOR:
        from .. import cliente_fino
        atendido, g = cliente_fino.guardar(conteudo, comando, codigo, mostrado_ate)
        if atendido:
            return g
    try:
        with _TRAVA:
            c = _con()
            c.execute("INSERT OR REPLACE INTO s VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (h, comando, b, total, mostrado_ate, codigo, time.time()))
            c.commit()
    except sqlite3.Error as e:
        # Um traceback no lugar da saida do comando e o pior resultado possivel. Sem guarda o
        # chamador (`exibir`) mostra a saida original inteira, sem dica de recuperacao.
        logger.warning("saida nao guardada (%s): %s", type(e).__name__, e)
        return None
    return {"hash": h, "hidden_lines": max(0, total - max(0, mostrado_ate - 1))}


def recuperar(h: str, a_partir: int = 0) -> dict | None:
    try:
        with _TRAVA:
            linha = _con().execute("SELECT comando, conteudo, total, mostrado_ate, codigo, criado FROM s WHERE hash = ?",
                                   (h,)).fetchone()
    except sqlite3.Error as e:
        logger.warning("saida nao lida (%s): %s", type(e).__name__, e)
        return None
    if not linha:
        return None
    comando, b, total, mostrado, codigo, criado = linha
    texto = b.decode("utf-8", "replace")
    inicio = a_partir or 1
    if inicio > 1:
        texto = "\n".join(texto.split("\n")[inicio - 1:])
    return {"hash": h, "command": comando, "exit_code": codigo, "total_lines": total,
            "from_line": inicio, "output": texto}


def exibir(f: Filtro, bruto: str, comando: str, codigo: int = 0, prefixo: str = "delegation-core",
           guardar_original: bool = True) -> dict:
    """O que o agente ve, com a mesma decisao do RTK. Devolve texto e o que aconteceu."""
    filtrado, perda = aplicar_com_info(f, bruto)
    perdeu = perda[0] != "none"
    dica = None
    if guardar_original:
        if codigo != 0:
            if len(bruto.encode("utf-8")) >= MIN_BYTES_FALHA:
                g = guardar(bruto, comando, codigo)
                dica = g and f"[full output: {prefixo} recall {g['hash']}]"
        elif perda[0] == "tail":
            g = guardar(perda[1], comando, None, perda[2])
            if g and g["hidden_lines"] > 0:
                dica = f"[+{g['hidden_lines']} hidden: {prefixo} recall {g['hash']}]"
        elif perda[0] == "whole":
            g = guardar(bruto, comando, None) if bruto else None
            dica = g and f"[full output: {prefixo} recall {g['hash']}]"
    if perdeu and dica is None:
        corpo = bruto
    else:
        corpo = filtrado if dica is None else f"{filtrado}\n{dica}"
    mostrado = bruto if tokens(corpo) > tokens(bruto) else corpo
    return {"output": mostrado, "filter": f.nome, "lossy": perdeu, "recall_hint": dica,
            "raw_tokens": tokens(bruto), "shown_tokens": tokens(mostrado)}
