"""Todo arquivo de codigo do pacote precisa estar no repositorio.

Medido em 04/11/2026: `.git/info/exclude` tinha a linha `skills/`, que casa com
qualquer pasta de nome `skills`, inclusive o pacote de codigo
`cores/agent_harness/skills/`. O arquivo existia no disco do desenvolvedor,
os testes passavam, e um clone limpo (ou o servidor, que instala do clone)
quebrava com `ModuleNotFoundError`. Este teste olha o que o git de fato
versiona, nao o que o disco tem.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "src" / "delegation_core"


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True)


@pytest.mark.skipif(not (RAIZ / ".git").exists(), reason="fora de um clone git")
def test_todo_py_do_pacote_esta_versionado():
    versionados = set(_git("ls-files", "src/delegation_core").stdout.splitlines())
    if not versionados:
        pytest.skip("git indisponivel")
    no_disco = {
        p.relative_to(RAIZ).as_posix()
        for p in FONTE.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    fora = sorted(no_disco - versionados)
    assert not fora, (
        "arquivos de codigo no disco que o git nao versiona (excluidos por "
        ".gitignore ou .git/info/exclude?): " + ", ".join(fora)
    )
