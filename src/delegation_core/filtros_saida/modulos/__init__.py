"""Modulos Rust do RTK portados para Python, um por arquivo, por familia.

Cada modulo tem `COMANDOS` (o primeiro token que ele trata) e
`filtrar(bruto, codigo) -> str`. Um modulo portado tem prioridade sobre os
filtros TOML do mesmo comando, como no RTK, e sobre o desvio para os
compressores que os modulos so anotados recebem (rtk_modulos.json).

Dois ganchos opcionais, para modulos que tratam so parte dos subcomandos ou que
rodam mais de um processo (git, gh):

- `trata(args) -> bool`: o `filtrar` sabe reduzir a saida de ESTE comando. Sem
  ele, vale todo comando cujo primeiro token esta em `COMANDOS`.
- `executa(args) -> bool` e `rodar(args, amb) -> int`: o `shell` entrega o comando
  ao modulo, que roda o que precisar (`ambiente.Ambiente`) e imprime o resultado.

Um modulo que atende mais de um executavel (grep e rg) declara o parametro
`comando` em `trata`, `executa` e `rodar` e recebe o primeiro token do comando.

A paridade de cada um e medida contra o binario real do RTK, rodando sobre um
executavel falso que imprime a saida gravada (`scripts/paridade_rtk_modulos.py`).
"""

from __future__ import annotations

import importlib
import inspect
import shlex
from typing import Callable

from .base import guard_stdout

#: modulo do RTK (como em rtk_modulos.json) -> modulo Python aqui.
PORTADOS = {
    "python/mypy_cmd": "python.mypy",
    "python/pytest_cmd": "python.pytest",
    "python/ruff_cmd": "python.ruff",
    "git/git_cmd": "git.git",
    "git/gh_cmd": "git.gh",
    "system/search": "system.search",
    "system/wc_cmd": "system.wc",
    "system/ls": "system.ls",
    "system/find_cmd": "system.find",
}

#: Modulos portados so em parte: rtk_modulos.json os marca `partial`, com a lista do que cobrem.
PARCIAIS = ("git/git_cmd", "git/gh_cmd")


def _carregar(nome: str):
    return importlib.import_module(f"{__name__}.{nome}")


def _tokens(comando: str) -> list[str]:
    try:
        return shlex.split(comando)
    except ValueError:
        return comando.split()


def _primeiro_token(comando: str) -> str:
    partes = _tokens(comando)
    return partes[0] if partes else ""


def _aceita(f, nome: str) -> bool:
    return nome in inspect.signature(f).parameters


def _chamar(f, *args, comando: str):
    """Chama `f(*args)`, com `comando=` quando `f` declara esse parametro."""
    return f(*args, comando=comando) if _aceita(f, "comando") else f(*args)


def filtrar(m, bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """Chama o `filtrar` do modulo com os argumentos que ele declara aceitar."""
    kw = {}
    if _aceita(m.filtrar, "args"):
        kw["args"] = list(args)
    if _aceita(m.filtrar, "injetado"):
        kw["injetado"] = injetado
    return m.filtrar(bruto, codigo, **kw)


def comando_do_rtk(comando: str) -> str:
    """O comando que o RTK rodaria: o modulo com `argumentos` reescreve os args
    (ruff check ganha --output-format=json). Sem `argumentos`, fica como veio."""
    achado = modulo_para(comando)
    if achado is None or not hasattr(achado[1], "argumentos"):
        return comando
    partes = _tokens(comando)
    return shlex.join([partes[0], *achado[1].argumentos(partes[1:])])


def _simples(comando: str) -> bool:
    """Comando simples: sem pipe, `;`, `&&`, redirecionamento ou substituicao (o criterio do hook)."""
    from ..cli import _COMPOSTO
    return not _COMPOSTO.search(comando)


def modulo_para(comando: str):
    """(modulo do RTK, modulo Python) do portado que reduz a saida do comando, ou None."""
    token = _primeiro_token(comando)
    for rtk, py in PORTADOS.items():
        m = _carregar(py)
        if token not in m.COMANDOS:
            continue
        if hasattr(m, "trata") and not (_simples(comando)
                                        and _chamar(m.trata, _tokens(comando)[1:], comando=token)):
            continue
        return rtk, m
    return None


def argumentos_do_shell(comando: str) -> list[str] | None:
    """Os argumentos de `comando` depois de expandidos pelo shell (aspas, `~`, `$VAR`, `*.py`),
    como o `sh -c` os entregaria ao programa. O proprio shell os expande: `printf '%s\\0'`
    no lugar do executavel imprime cada um terminado em NUL."""
    import re
    import subprocess
    achado = re.match(r"\s*(\S+)\s*(.*)\Z", comando, re.S)
    if achado is None:
        return None
    resto = achado.group(2)
    if not resto:
        return []
    p = subprocess.run(["/bin/sh", "-c", "printf '%s\\0' " + resto], capture_output=True)
    if p.returncode != 0:
        return None
    return p.stdout.decode("utf-8", "replace").split("\0")[:-1]


def rodavel(comando: str):
    """(modulo do RTK, modulo Python, argumentos, executavel) do modulo que roda o comando por conta propria."""
    if not _simples(comando):
        return None
    token = _primeiro_token(comando)
    for rtk, py in PORTADOS.items():
        m = _carregar(py)
        if token not in m.COMANDOS or not hasattr(m, "rodar"):
            continue
        args = argumentos_do_shell(comando)
        if args is not None and _chamar(m.executa, args, comando=token):
            return rtk, m, args, token
    return None


def rodar_modulo(achado, amb) -> int:
    """Roda o que `rodavel` achou e devolve o codigo de saida do comando."""
    _, m, args, token = achado
    return _chamar(m.rodar, args, amb, comando=token)


def portado_para(comando: str) -> tuple[str, Callable[[str, int], str], tuple] | None:
    """(modulo do RTK, filtrar, clean_outputs) do modulo portado que trata o comando."""
    achado = modulo_para(comando)
    if achado is None:
        return None
    rtk, m = achado
    return rtk, m.filtrar, getattr(m, "CLEAN_OUTPUTS", ())


def mostrar(m, bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """O texto que o RTK imprimiria. Modulo com `tee` (dica de recuperacao) traz
    o proprio `mostrar`; os outros passam pela guarda simples."""
    if hasattr(m, "mostrar"):
        return m.mostrar(bruto, codigo)
    limpas = m.clean_outputs(list(args)) if callable(getattr(m, "clean_outputs", None)) \
        else getattr(m, "CLEAN_OUTPUTS", ())
    return guard_stdout(bruto, filtrar(m, bruto, codigo, args, injetado), limpas)


def aplicar(comando: str, bruto: str, codigo: int, injetado: bool = False) -> dict | None:
    """O que o RTK mostraria para este comando, ou None se nenhum modulo portado o trata.

    `injetado`: o comando rodou com a reescrita de `comando_do_rtk` (o shell);
    no filter_output o agente ja rodou o comando como quis.
    """
    achado = modulo_para(comando)
    if achado is None:
        return None
    rtk, m = achado
    mostrado = mostrar(m, bruto, codigo, _tokens(comando)[1:], injetado)
    return {"output": mostrado, "rtk_module": rtk, "ported": True,
            "lossy": mostrado != bruto}
