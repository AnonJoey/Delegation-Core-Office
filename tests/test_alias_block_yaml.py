"""`ensure_aliases` nao pode gravar um bloco que o YAML recusa.

`_alias_block` so punha aspas quando o alias tinha `:`, `#`, `[` ou `]`, e nao
escapava aspas dentro do texto. Medido em 04/11/2026 com o ensure_aliases real:
`Decisao: servidor "x" (a)` (aspas dentro de alias com dois pontos), `@mencao`,
`*estrela`, `!bang`, `%pct`, `'aspa`, `>maior`, `|pipe` e `` `crase `` quebram o
frontmatter da nota inteira. O organizer chama isso em toda nota que cria, com
titulo vindo de modelo, e o vault tinha 62 notas fora de Reference/graphs com
o bloco ilegivel.
"""
from __future__ import annotations

import pytest
import yaml

from delegation_core.linker import ensure_aliases
from delegation_core.notes import _frontmatter_parses

BASE = "---\ntitle: t\nstatus: active\n---\ncorpo da nota\n"

HOSTIS = [
    'Decisao: servidor "x" (a)', "@mencao", "*estrela", "&ancora", "!bang", "%pct",
    "'aspa simples", "a \"b\" c", ">maior", "|pipe", "`crase", "- traco", "? duvida",
    "# hash", "termina com dois pontos:", "[colchete", "{chave}", "com\\barra",
]


def _aliases(texto: str) -> list:
    bloco = texto.split("---\n", 2)[1]
    return yaml.safe_load(bloco)["aliases"]


@pytest.mark.parametrize("alias", HOSTIS)
def test_alias_hostil_gera_frontmatter_legivel_e_volta_igual(alias):
    novo = ensure_aliases(BASE, [alias])
    assert _frontmatter_parses(novo), repr(alias)
    assert _aliases(novo) == [alias]


def test_alias_simples_continua_sem_aspas():
    novo = ensure_aliases(BASE, ["Titulo simples"])
    assert "  - Titulo simples" in novo
    assert _aliases(novo) == ["Titulo simples"]


def test_valor_que_o_yaml_leria_como_outro_tipo_vai_entre_aspas():
    novo = ensure_aliases(BASE, ["null", "true", "123"])
    assert _aliases(novo) == ["null", "true", "123"]


def test_idempotente_e_preserva_os_existentes():
    um = ensure_aliases(BASE, ['A: "b"'])
    dois = ensure_aliases(um, ['A: "b"', "outro"])
    assert _aliases(dois) == ['A: "b"', "outro"]
    assert ensure_aliases(dois, ["outro"]) == dois


# ── leitura dos aliases ──────────────────────────────────────────────────────

def test_leitura_nao_arranca_aspa_que_e_parte_do_texto():
    from delegation_core.notes import frontmatter_aliases
    novo = ensure_aliases(BASE, ['A: "b"'])
    assert frontmatter_aliases(novo) == {'A: "b"'}


def test_leitura_preserva_a_ordem_na_hora_de_regravar():
    novo = ensure_aliases(BASE, ["zeta", "alfa", "meio"])
    novo = ensure_aliases(novo, ["omega"])
    assert _aliases(novo) == ["zeta", "alfa", "meio", "omega"]


def test_bloco_ja_quebrado_cai_na_leitura_por_linha():
    from delegation_core.notes import frontmatter_aliases
    quebrado = '---\ntitle: a: b: c\naliases:\n  - "um"\n  - dois\n---\ncorpo\n'
    assert not _frontmatter_parses(quebrado)
    assert frontmatter_aliases(quebrado) == {"um", "dois"}


def test_aliases_em_linha_e_texto_unico():
    from delegation_core.notes import frontmatter_aliases
    assert frontmatter_aliases("---\naliases: [a, b]\n---\nx\n") == {"a", "b"}
    assert frontmatter_aliases("---\naliases: solo\n---\nx\n") == {"solo"}
    assert frontmatter_aliases("---\ntitle: t\n---\nx\n") == set()


def test_alias_repetido_na_nota_nao_se_repete_ao_regravar():
    nota = "---\ntitle: t\naliases:\n  - um\n  - um\n  - dois\n---\ncorpo\n"
    novo = ensure_aliases(nota, ["tres"])
    assert _aliases(novo) == ["um", "dois", "tres"]
