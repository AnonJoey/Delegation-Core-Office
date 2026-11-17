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


def test_toda_entrada_tem_texto(paginas):
    """Nenhuma chave, tarefa, regra, rota ou variavel sem descricao em ingles (docs/reference/_text/)."""
    g = _gerador()
    faltando = g.sem_texto(paginas)
    assert not faltando, f"entries without English text: {faltando}"


def test_nenhum_texto_sem_dono():
    """Um texto em _text/ cuja chave saiu do codigo e um texto que ninguem le: apague-o."""
    from dataclasses import fields

    from delegation_core import vigia
    from delegation_core.config import Config
    g = _gerador()
    donos = {
        "config": {f.name for f in fields(Config)},
        "schedule": {t["nome"] for t in vigia.TAREFAS_PADRAO},
        "alerts": {r.nome for r in vigia.regras_padrao()},
        "dashboard-api": {f"{m} {c}" for c, m, _ in g._rotas_do_painel()},
    }
    sobrando = {nome: sorted(set(g._textos(nome)) - chaves) for nome, chaves in donos.items()}
    sobrando = {n: s for n, s in sobrando.items() if s}
    assert not sobrando, f"texts for things that no longer exist: {sobrando}"


def test_todo_comando_e_argumento_da_cli_tem_ajuda():
    """A referencia da CLI sai do texto de ajuda: sem ele, a linha fica vazia na documentacao."""
    import argparse

    from delegation_core.cli import construir_parser
    parser, _ = construir_parser()
    faltando = []

    def andar(p, caminho):
        for a in p._actions:
            if isinstance(a, (argparse._HelpAction, argparse._VersionAction)):
                continue
            if isinstance(a, argparse._SubParsersAction):
                ajuda = {c.dest: c.help for c in a._choices_actions}
                for nome, sub in a.choices.items():
                    if not ajuda.get(nome):
                        faltando.append(f"{caminho} {nome}")
                    andar(sub, f"{caminho} {nome}")
                continue
            if not a.help:
                faltando.append(f"{caminho} {'/'.join(a.option_strings) or a.dest}")

    andar(parser, "delegation-core")
    assert not faltando, f"CLI entries without help text: {faltando}"
