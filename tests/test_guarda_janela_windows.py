"""Guarda global contra janela de console no Windows (procs.instalar_guarda, 24/11/2026).

`sem_janela()` so protege a chamada que lembra dele; a guarda corrige todo `Popen` do processo,
inclusive o que as bibliotecas lancam. Os testes de logica rodam em qualquer sistema, sobre uma
classe falsa; o ultimo so roda no Windows (CI windows-latest) com o Popen de verdade.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from delegation_core import procs

NOVO, SEM, DESANEXADO, GRUPO = (procs.CREATE_NEW_CONSOLE, procs.CREATE_NO_WINDOW,
                                procs.DETACHED_PROCESS, 0x00000200)


@pytest.mark.parametrize("flags,tem_console,esperado", [
    (0, False, SEM),                         # pythonw: o filho ganharia console visivel
    (0, True, 0),                            # terminal (ou console oculto): herda, sem janela
    (GRUPO, False, GRUPO | SEM),
    (DESANEXADO | GRUPO, True, SEM | GRUPO),   # desanexado vira console oculto
    (DESANEXADO, False, SEM),
    (NOVO, False, NOVO),                     # janela pedida de proposito (--visible)
    (SEM, False, SEM),
    (None, False, SEM),
])
def test_tabela_dos_flags(flags, tem_console, esperado):
    assert procs.ajustar_flags(flags, tem_console) == esperado


def _classe_falsa():
    class Falsa:
        def __init__(self, *args, **kwargs):
            self.args, self.kwargs = args, kwargs
    return Falsa


def test_a_guarda_corrige_todo_popen_e_os_system(monkeypatch):
    Falsa = _classe_falsa()
    falso_os = types.SimpleNamespace(system=None)
    monkeypatch.setattr(procs, "tem_console", lambda: False)
    assert procs.instalar_guarda(classe=Falsa, modulo_os=falso_os, forcar=True)
    assert Falsa(["cmd"]).kwargs["creationflags"] == SEM
    assert Falsa(["llama"], creationflags=DESANEXADO | GRUPO).kwargs["creationflags"] == SEM | GRUPO
    assert getattr(falso_os.system, "_dc_sem_janela", False)


def test_a_guarda_respeita_quem_tem_console(monkeypatch):
    Falsa = _classe_falsa()
    monkeypatch.setattr(procs, "tem_console", lambda: True)
    procs.instalar_guarda(classe=Falsa, modulo_os=types.SimpleNamespace(), forcar=True)
    assert Falsa(["git", "status"]).kwargs["creationflags"] == 0


def test_a_guarda_e_idempotente(monkeypatch):
    Falsa = _classe_falsa()
    monkeypatch.setattr(procs, "tem_console", lambda: False)
    for _ in range(3):
        procs.instalar_guarda(classe=Falsa, modulo_os=types.SimpleNamespace(), forcar=True)
    assert Falsa.__init__.__wrapped__.__name__ == "__init__"
    assert not getattr(Falsa.__init__.__wrapped__, "_dc_sem_janela", False)


def test_fora_do_windows_a_guarda_nao_liga(monkeypatch):
    monkeypatch.setattr(procs, "_e_windows", lambda: False)
    Falsa = _classe_falsa()
    assert procs.instalar_guarda(classe=Falsa) is False
    assert not getattr(Falsa.__init__, "_dc_sem_janela", False)


def test_o_pacote_liga_a_guarda_no_import():
    texto = (Path(procs.__file__).with_name("__init__.py")).read_text(encoding="utf-8")
    assert "_procs.instalar_guarda()" in texto


def test_ninguem_lanca_processo_desanexado():
    """DETACHED_PROCESS deixa o filho sem console: cada neto de console abriria janela."""
    src = Path(procs.__file__).parent
    achados = []
    for p in src.rglob("*.py"):
        if p.name == "procs.py" or "headroom_py" in p.parts:
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(n, ast.keyword) and n.arg == "creationflags":
                nomes = {x.attr for x in ast.walk(n.value) if isinstance(x, ast.Attribute)}
                nomes |= {x.id for x in ast.walk(n.value) if isinstance(x, ast.Name)}
                if "DETACHED_PROCESS" in nomes:
                    achados.append(f"{p.relative_to(src)}:{n.value.lineno}")
            if isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if isinstance(k, ast.Constant) and k.value == "creationflags" and \
                            "DETACHED_PROCESS" in ast.dump(v):
                        achados.append(f"{p.relative_to(src)}:{v.lineno}")
    assert not achados, achados


@pytest.mark.skipif(os.name != "nt", reason="so o Windows tem console por processo")
def test_no_windows_o_filho_desanexado_ganha_console_oculto():
    """Popen de verdade: pedir DETACHED_PROCESS deve dar ao filho um console (GetConsoleCP != 0)."""
    import delegation_core  # noqa: F401  liga a guarda
    assert getattr(subprocess.Popen.__init__, "_dc_sem_janela", False)
    sonda = "import ctypes, sys; sys.exit(0 if ctypes.windll.kernel32.GetConsoleCP() else 7)"
    r = subprocess.run([sys.executable, "-c", sonda], creationflags=subprocess.DETACHED_PROCESS, check=False)
    assert r.returncode == 0, "o filho ficou sem console: os netos dele abririam janela"
