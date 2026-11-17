"""docs/reference/ is generated from the code and must match it.

Each page is rendered in memory by scripts/gerar_referencia.py from the same objects the
program uses (tool registry, CLI parser, Config, schedule, alert rules, feature-flag map,
dashboard router, error catalog) and compared with the file on disk. When this fails, the code
changed and the reference did not: run

    PYTHONPATH=src python scripts/gerar_referencia.py

and commit the result. Never edit docs/reference/*.md by hand.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _gerador():
    spec = importlib.util.spec_from_file_location("gerar_referencia", RAIZ / "scripts" / "gerar_referencia.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def paginas():
    return _gerador().renderizar()


def test_toda_pagina_existe_e_bate_com_o_codigo(paginas):
    velhas = []
    for nome, conteudo in paginas.items():
        arq = RAIZ / "docs" / "reference" / nome
        if not arq.exists() or arq.read_text(encoding="utf-8") != conteudo:
            velhas.append(nome)
    assert not velhas, ("docs/reference/ is stale: run `PYTHONPATH=src python scripts/gerar_referencia.py`: "
                        + ", ".join(velhas))


def test_nenhuma_pagina_sobrando_no_diretorio(paginas):
    no_disco = {p.name for p in (RAIZ / "docs" / "reference").glob("*.md")}
    assert no_disco <= set(paginas), f"pages no generator writes: {sorted(no_disco - set(paginas))}"
