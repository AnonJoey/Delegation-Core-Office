"""O que o servidor diz de si mesmo nao pode falar de um indice que ja nao e o padrao.

Desde a v0.16.0 o indice e um arquivo SQLite. As descricoes das ferramentas MCP sao o
que um agente le para decidir o que a ferramenta faz; uma que diga "ChromaDB index"
faz o agente raciocinar sobre o indice errado. Quatro descricoes e o `--help` do CLI
ainda diziam isso depois da troca (achado em 09/10/2026).

So os comandos cujo assunto E o indice antigo podem nomeia-lo: a migracao, a
comparacao e a limpeza de segmentos orfaos do Chroma.
"""
import asyncio
import re

import pytest

PERMITIDOS_NO_HELP = ("index-migrate", "index-compare", "--orphans", "orphan", "recover-index", "ingest-registry")


def _descricoes_das_ferramentas() -> dict[str, str]:
    from delegation_core import server
    ferramentas = asyncio.run(server.mcp.list_tools())
    return {t.name: (t.description or "") for t in ferramentas}


def test_nenhuma_ferramenta_mcp_descreve_o_indice_como_chromadb():
    ruins = {n: d.splitlines()[0] for n, d in _descricoes_das_ferramentas().items()
             if re.search(r"chroma", d, re.I)}
    assert not ruins, f"ferramentas que ainda falam em ChromaDB: {ruins}"


def test_o_help_do_cli_nao_fala_em_chromadb_fora_dos_comandos_do_indice_antigo(monkeypatch, capsys):
    import sys
    from delegation_core import cli
    monkeypatch.setattr(sys, "argv", ["delegation-core", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    saida = capsys.readouterr().out
    # junta as linhas quebradas de cada comando numa so, para ver o comando e o texto juntos
    blocos = re.split(r"\n(?=    \S)", saida)
    ruins = [b.replace("\n", " ")[:100] for b in blocos
             if re.search(r"chroma", b, re.I) and not any(p in b for p in PERMITIDOS_NO_HELP)]
    assert not ruins, f"comandos do --help que ainda falam em ChromaDB: {ruins}"
    assert "ChromaDB" not in saida.split("positional arguments")[0], "a descricao do programa fala em ChromaDB"


def test_a_api_do_painel_traz_o_nome_novo_e_mantem_o_antigo():
    """O painel ja instalado le `chroma_indexed_notes`; o nome neutro e o que vale daqui em diante."""
    from pathlib import Path
    fonte = (Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "dashboard_api.py").read_text(encoding="utf-8")
    assert '"indexed_notes": indexed_count' in fonte and '"chroma_indexed_notes": indexed_count' in fonte
