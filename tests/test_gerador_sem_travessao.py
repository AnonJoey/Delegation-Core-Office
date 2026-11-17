"""O gerador de wiki e de relatorio nao acrescenta travessao ao que vai para o vault.

## O que foi medido em 26/09/2026

A regra de escrita desta casa proibe travessao em nota do vault, e o gerador de
artigos punha travessao em toda linha de lista, todo cabecalho de secao e no
proprio rotulo de comunidade, que vira **nome de arquivo**.

No grafo deste repo, antes:

| | |
|---|---|
| artigos do wiki com travessao | **336 de 346** |
| ocorrencias no `GRAPH_REPORT.md` | 76 |

Depois de corrigir as dez linhas de saida e o rotulo de comunidade
(`cluster.py:198`), sobraram 42 artigos, e a natureza dos que sobraram e
**outra**: sao docstrings do codigo-fonte sendo grafado, que o extrator cita.
Confirmado linha a linha, por exemplo
`stdio_bridge.py — a stdio MCP server that forwards to the HTTP daemon`, que
existe literalmente no arquivo.

Citacao e citacao: reescrever faria o artigo deixar de refletir o codigo, e
grafar qualquer base de terceiro traria o travessao dela de volta. O ponto de
parada correto e o gerador nao ACRESCENTAR.

## Por que o grafo deste teste e sintetico

Justamente para separar as duas coisas. Com rotulos e caminhos sem travessao,
qualquer travessao na saida so pode ter vindo do gerador, que e o que este
arquivo guarda. Um teste sobre o grafo real mediria os docstrings junto e nunca
poderia ficar verde.

## O que NAO mudou, e de proposito

O `cluster.py:198` mudou o rotulo de comunidade, que vira nome de arquivo de
artigo. Isso renomeia ate 118 artigos ja no vault, e foi conferido antes:
nenhum contrato de parsing separa pelo travessao, e **zero** wikilinks de fora
da pasta de grafos apontam para esses nomes. Os links internos do wiki sao
regerados junto com os artigos.
"""

from __future__ import annotations

import networkx as nx
import pytest

TRAVESSAO = "—"


@pytest.fixture
def grafo_limpo():
    """Um grafo pequeno sem travessao em lugar nenhum.

    Rotulo, id e caminho de fonte todos limpos, para a saida so poder ganhar
    travessao do gerador.
    """
    G = nx.DiGraph()
    for i in range(14):
        G.add_node(f"mod_{i}", label=f"modulo_{i}", source_file=f"src/mod_{i}.py",
                   rationale="Faz uma coisa simples e util.")
    for i in range(13):
        G.add_edge(f"mod_{i}", f"mod_{i+1}", relation="calls")
    G.add_edge("mod_0", "mod_7", relation="calls")
    return G


def _agrupar(G):
    from delegation_core.graph.cluster import cluster, label_communities_by_hub, score_all
    com = cluster(G)
    return com, label_communities_by_hub(G, com), score_all(G, com)


def test_o_wiki_gerado_nao_tem_travessao(tmp_path, grafo_limpo):
    """Conferido por mutacao: devolver o travessao a qualquer linha de saida do
    `wiki.py`, ou ao rotulo do `cluster.py`, derruba este teste."""
    from delegation_core.graph.analyze import god_nodes
    from delegation_core.graph.wiki import to_wiki

    com, rotulos, coesao = _agrupar(grafo_limpo)
    saida = tmp_path / "wiki"
    to_wiki(grafo_limpo, com, saida, community_labels=rotulos,
            cohesion=coesao, god_nodes_data=god_nodes(grafo_limpo))

    artigos = list(saida.glob("*.md"))
    assert artigos, "o gerador nao escreveu artigo nenhum; o teste nao prova nada"

    sujos = []
    for f in artigos:
        if TRAVESSAO in f.name:
            sujos.append(f"nome do arquivo: {f.name}")
        for n, linha in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
            if TRAVESSAO in linha:
                sujos.append(f"{f.name}:{n}: {linha.strip()[:70]}")
    assert not sujos, "o gerador acrescentou travessao:\n  " + "\n  ".join(sujos[:8])


def test_o_relatorio_gerado_nao_tem_travessao(grafo_limpo):
    from delegation_core.graph.analyze import god_nodes, suggest_questions, surprising_connections
    from delegation_core.graph.report import generate

    com, rotulos, coesao = _agrupar(grafo_limpo)
    texto = generate(grafo_limpo, com, coesao, rotulos, god_nodes(grafo_limpo),
                     surprising_connections(grafo_limpo, com),
                     {"files": {"code": ["src/mod_0.py"]}, "total_files": 1,
                      "total_words": 500, "by_extension": {".py": 1}},
                     {"input_tokens": 0, "output_tokens": 0}, "/raiz",
                     suggested_questions=suggest_questions(grafo_limpo, com, {}))

    sujas = [l.strip()[:70] for l in texto.split("\n") if TRAVESSAO in l]
    assert not sujas, "o relatorio ganhou travessao:\n  " + "\n  ".join(sujas[:8])


@pytest.fixture
def grafo_so_de_prosa():
    """Comunidade sem NENHUM rotulo em forma de identificador.

    E o unico caso que alcanca `cluster.py:198`, o ramo que compoe
    `<stem> - <discriminador>`. Com rotulo de identificador o codigo nomeia
    pelo hub e aquela linha nunca roda: a primeira versao deste teste passava
    por vacuidade, e a mutacao do travessao no rotulo SOBREVIVEU por isso.
    """
    G = nx.DiGraph()
    frases = [
        "Esta funcao faz alguma coisa util e tem descricao longa",
        "Outra descricao comprida que nao parece identificador nenhum",
        "Mais uma frase inteira servindo de rotulo de no do grafo",
        "E ainda outra frase para a comunidade ter tamanho decente",
        "Uma quinta frase porque comunidade pequena e descartada",
        "Sexta frase, para o agrupador ter com o que trabalhar",
    ]
    for i, frase in enumerate(frases):
        G.add_node(f"prosa_{i}", label=frase, source_file="src/modulo_de_prosa.py",
                   rationale=frase)
    for i in range(len(frases) - 1):
        G.add_edge(f"prosa_{i}", f"prosa_{i+1}", relation="calls")
    G.add_edge("prosa_0", "prosa_3", relation="calls")
    return G


def test_o_rotulo_de_comunidade_nao_usa_travessao(grafo_so_de_prosa):
    """`cluster.py:198` compoe `<stem> - <discriminador>`, e esse rotulo vira
    NOME DE ARQUIVO de artigo no vault.

    Conferido por mutacao: devolver o travessao aquela linha derruba este
    teste. A versao anterior usava um grafo de identificadores e NAO derrubava,
    porque o ramo nem era alcancado.
    """
    from delegation_core.graph.cluster import _is_identifier_label

    _, rotulos, _ = _agrupar(grafo_so_de_prosa)
    assert rotulos, "sem rotulo nenhum o teste nao prova nada"

    # guarda de que o ramo certo foi exercitado
    assert not any(_is_identifier_label(grafo_so_de_prosa, n)
                   for n in grafo_so_de_prosa.nodes), (
        "o grafo precisa ser todo de prosa, senao o ramo do discriminador nao roda")

    for cid, rotulo in rotulos.items():
        assert TRAVESSAO not in rotulo, f"comunidade {cid} rotulada com travessao: {rotulo}"


def test_o_teste_reconheceria_um_travessao(tmp_path, grafo_limpo):
    """Guarda do proprio teste: se a deteccao estivesse quebrada, tudo acima
    ficaria verde por nao olhar nada."""
    alvo = tmp_path / "sujo.md"
    alvo.write_text(f"# um titulo {TRAVESSAO} com travessao\n", encoding="utf-8")
    assert TRAVESSAO in alvo.read_text(encoding="utf-8")


def test_o_marcador_de_merge_nao_usa_travessao():
    """Terceiro produtor de conteudo de vault, achado depois dos outros dois.

    Quando duas notas sao fundidas, o `merger` acrescenta
    `*Merged from \\`x.md\\` - <data>*` ao CORPO da nota. E texto de nota do
    vault, entao vale a mesma regra.

    Conferido antes de mexer, como nos outros dois: nada parseia esse marcador
    (so um teste, que casa ate a crase) e ZERO notas do vault ja o carregam,
    entao a troca nao mexe em dado gravado.

    Conferido por mutacao: devolver o travessao ao `merger` derruba este teste.
    """
    import inspect

    from delegation_core import merger

    fonte = inspect.getsource(merger)
    marcadores = [l for l in fonte.split("\n") if "Merged from" in l and 'f"' in l]
    assert marcadores, "o marcador de merge sumiu; este teste precisa de outro alvo"
    for linha in marcadores:
        assert TRAVESSAO not in linha, (
            f"o merger voltou a escrever travessao no corpo da nota: {linha.strip()}")
