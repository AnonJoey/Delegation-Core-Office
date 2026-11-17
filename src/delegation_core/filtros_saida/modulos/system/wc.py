"""`src/cmds/system/wc_cmd.rs` do RTK: `wc` sem o preenchimento e sem o caminho repetido.

    wc arq.py      ->  30L 96W 978B
    wc -l arq.py   ->  30
    wc -l *.py     ->  uma tabela, sem o diretorio comum

O RTK roda o `wc` com os mesmos argumentos e filtra so o stdout. Sem operando de arquivo o `wc`
le a entrada padrao, e ela segue para o processo filho (`cat arq | rtk wc`).

Diferenca deliberada: o modo (`-l`, `-w`, `-c`, `-m`) sai das letras de todo argumento que
comeca por `-`, como no RTK, inclusive das flags longas (`--lines` conta um `l`).
"""

from __future__ import annotations

import re

from ..ambiente import Ambiente
from ..base import split_whitespace, trim, linhas
from ..runner import run_filtered

COMANDOS = ("wc",)
FULL, LINES, WORDS, BYTES, CHARS, MIXED = "full", "lines", "words", "bytes", "chars", "mixed"
_U64 = re.compile(r"\+?[0-9]+")


def _e_u64(texto: str) -> bool:
    return bool(_U64.fullmatch(texto)) and int(texto) <= 2**64 - 1


def detect_mode(args: list[str]) -> str:
    """Quais colunas o usuario pediu."""
    flags = [a for a in args if a.startswith("-")]
    if not flags:
        return FULL
    tem = {"l": False, "w": False, "c": False, "m": False}
    contagem = 0
    for flag in flags:
        for ch in flag[1:]:
            if ch in tem:
                tem[ch] = True
                contagem += 1
    if contagem == 0:
        return FULL
    if contagem > 1:
        return MIXED
    if tem["l"]:
        return LINES
    if tem["w"]:
        return WORDS
    if tem["c"]:
        return BYTES
    if tem["m"]:
        return CHARS
    return FULL


def find_common_prefix(caminhos: list[str]) -> str:
    if len(caminhos) <= 1:
        return ""
    primeiro = caminhos[0]
    pos = primeiro.rfind("/")
    if pos < 0:
        return ""
    prefixo = primeiro[:pos + 1]
    if all(p.startswith(prefixo) for p in caminhos):
        return prefixo
    candidato = prefixo
    while candidato:
        if all(p.startswith(candidato) for p in caminhos):
            return candidato
        pos = candidato[:-1].rfind("/")
        if pos < 0:
            return ""
        candidato = candidato[:pos + 1]
    return ""


def strip_prefix(caminho: str, prefixo: str) -> str:
    if prefixo and caminho.startswith(prefixo):
        return caminho[len(prefixo):]
    return caminho


def format_single_line(linha: str, modo: str) -> str:
    partes = split_whitespace(linha)
    if modo in (LINES, WORDS, BYTES, CHARS):
        return partes[0] if partes else ""
    if modo == FULL:
        if len(partes) >= 3:
            return f"{partes[0]}L {partes[1]}W {partes[2]}B"
        return trim(linha)
    if len(partes) >= 2:
        # Misto: tira o caminho e fica so com os numeros.
        if not _e_u64(partes[-1]):
            return " ".join(partes[:-1])
        return " ".join(partes)
    return trim(linha)


def format_multi_line(ls: list[str], modo: str) -> str:
    caminhos = [p[-1] for p in (split_whitespace(l) for l in ls) if p and p[-1] != "total"]
    prefixo = find_common_prefix(caminhos)
    resultado: list[str] = []
    for linha in ls:
        partes = split_whitespace(linha)
        if not partes:
            continue
        e_total = partes[-1] == "total"
        if modo in (LINES, WORDS, BYTES, CHARS):
            if e_total:
                resultado.append(f"Σ {partes[0]}")
            else:
                resultado.append(f"{partes[0]} {strip_prefix(partes[-1], prefixo)}")
        elif modo == FULL:
            if e_total:
                p1 = partes[1] if len(partes) > 1 else "0"
                p2 = partes[2] if len(partes) > 2 else "0"
                resultado.append(f"Σ {partes[0]}L {p1}W {p2}B")
            elif len(partes) >= 4:
                resultado.append(f"{partes[0]}L {partes[1]}W {partes[2]}B {strip_prefix(partes[3], prefixo)}")
            else:
                resultado.append(trim(linha))
        else:
            if e_total:
                resultado.append("Σ " + " ".join(partes[:-1]))
            elif len(partes) >= 2:
                if not _e_u64(partes[-1]):
                    resultado.append(" ".join(partes[:-1]) + " " + strip_prefix(partes[-1], prefixo))
                else:
                    resultado.append(" ".join(partes))
            else:
                resultado.append(trim(linha))
    return "\n".join(resultado)


def filter_wc_output(bruto: str, modo: str) -> str:
    ls = linhas(trim(bruto))
    if not ls:
        return ""
    if len(ls) == 1:
        return format_single_line(ls[0], modo)
    return format_multi_line(ls, modo)


def executa(args: list[str]) -> bool:
    return True


def rodar(args: list[str], amb: Ambiente) -> int:
    modo = detect_mode(args)
    le_stdin = not any(not a.startswith("-") for a in args)
    try:
        return run_filtered(amb, [amb.resolver("wc"), *args], "wc", lambda saida: filter_wc_output(saida, modo),
                            stdout_only=True, inherit_stdin=le_stdin)
    except OSError as e:
        amb.err(f"Error: Failed to run wc: {e}\n")
        return 1


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """Para o `filter_output`: o `wc` ja rodou e so ha a saida."""
    return filter_wc_output(bruto, detect_mode(list(args)))
