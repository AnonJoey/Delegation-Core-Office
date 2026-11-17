"""Medir a qualidade da busca sem perguntas escritas a mao.

## O problema que motivou

Os limiares do `search_vault` foram calibrados em 31/07/2026 com 1.159 notas e
ninguem mediu de novo. Em 26/09/2026 o vault tem 10.234 notas e a banda de par
irrelevante subiu: p95 de 0,480 para 0,540.

Envelheceu em silencio porque a calibracao dependia de **cinco perguntas
escritas a mao**, e ninguem reescreve cinco perguntas toda vez que o vault
cresce. O que nao se mede sozinho nao se mede.

## A ressalva que estes testes protegem

Este instrumento **nao serve para escolher o limiar**. A calibracao de 31/07
mediu acerto entre 0,518 e 0,550, abaixo do minimo de 0,552 que ele observa, e
a razao e o instrumento: frase do corpo e quase verbatim, pergunta de gente e
parafrase. Ele mede um caso **mais facil** que o real.

Por isso a ressalva viaja dentro do resultado, e tem teste. Um numero sem ela
seria usado para subir o limiar, o que descartaria as perguntas parafraseadas
que a calibracao de julho existiu para proteger.
"""

from __future__ import annotations

import pytest

from delegation_core.afericao import aferir, frases_utilizaveis


class ColecaoFalsa:
    """Dublê do ChromaDB com as DUAS assinaturas reais e nada mais.

    Aceitar `**kwargs` aqui deixaria verde uma chamada que a colecao de verdade
    recusa, que e um defeito ja catalogado neste projeto.
    """

    def __init__(self, notas: list[tuple[str, str]], acerta: bool = True):
        self._notas = notas
        self._acerta = acerta
        self.consultas: list[str] = []

    def get(self, where=None, include=None, limit=None):
        return {
            "metadatas": [{"path": p, "kind": "note"} for p, _ in self._notas],
            "documents": [d for _, d in self._notas],
        }

    def query(self, query_texts=None, n_results=10, where=None, include=None):
        consulta = (query_texts or [""])[0]
        self.consultas.append(consulta)
        certa = next((p for p, d in self._notas if consulta in d), None)
        if self._acerta and certa:
            ordem = [certa] + [p for p, _ in self._notas if p != certa]
        else:
            ordem = [p for p, _ in self._notas if p != certa]
        ordem = ordem[:n_results]
        return {
            "metadatas": [[{"path": p, "kind": "note"} for p in ordem]],
            "distances": [[0.3 + 0.05 * i for i in range(len(ordem))]],
        }


def _corpo(marca: str) -> str:
    return (f"---\ntitle: {marca}\n---\n\n"
            f"Esta e uma frase de corpo com tamanho suficiente para servir de "
            f"consulta sobre {marca} e ser reconhecida.\n")


def test_frontmatter_nao_vira_consulta():
    fs = frases_utilizaveis("---\ntitle: Uma nota bem comprida para caber no corte de tamanho\n---\n\n"
                            "Uma frase de corpo com tamanho suficiente para servir de consulta aqui.\n")
    assert all("title:" not in f for f in fs)
    assert fs


def test_wikilink_e_codigo_saem():
    """Wikilink casaria pelo NOME do alvo em vez de pelo conteudo, medindo a
    coisa errada; e trecho de codigo nao e prosa que alguem busca."""
    texto = ("Uma frase longa o bastante que menciona [[outra nota qualquer]] e "
             "tambem `um_trecho_de_codigo()` no meio dela para o teste.\n")
    fs = frases_utilizaveis(texto)
    assert fs, "a frase toda nao pode sumir"
    assert "[[" not in fs[0] and "`" not in fs[0]


@pytest.mark.parametrize("texto,esperado", [
    ("curta demais", False),
    ("x" * 300, False),
    ("uma frase com exatamente o tamanho certo para passar no corte de sessenta", True),
])
def test_corte_de_tamanho(texto, esperado):
    assert bool(frases_utilizaveis(texto)) is esperado


def test_recall_um_quando_a_busca_sempre_acerta():
    col = ColecaoFalsa([(f"Ref/n{i}.md", _corpo(f"assunto{i}")) for i in range(8)])
    r = aferir(col, amostras=8, semente=1)
    assert r["recall"] == 1.0
    assert r["posicao_mediana"] == 1


def test_recall_zero_quando_a_busca_nunca_acerta():
    """Sem isto, um instrumento quebrado que sempre devolve 1.0 passaria."""
    col = ColecaoFalsa([(f"Ref/n{i}.md", _corpo(f"assunto{i}")) for i in range(8)],
                       acerta=False)
    assert aferir(col, amostras=8, semente=1)["recall"] == 0.0


def test_a_mesma_semente_da_o_mesmo_resultado():
    """O ponto do instrumento e comparar duas corridas separadas no tempo.

    Sem semente fixa, dois numeros de execucoes diferentes nao querem dizer
    nada um ao lado do outro, e a deteccao de regressao morre.

    Conferido por mutacao: trocar a semente por `random` global derruba este
    teste.
    """
    notas = [(f"Ref/n{i}.md", _corpo(f"assunto{i}")) for i in range(40)]

    # Comparar recall nao serve aqui: com o duble sempre acertando, ele da 1.0
    # nas duas corridas independente do sorteio, e o teste passaria mesmo sem
    # semente nenhuma. O que prova reproducibilidade e a SEQUENCIA SORTEADA.
    ca = ColecaoFalsa(list(notas)); aferir(ca, amostras=6, semente=7)
    cb = ColecaoFalsa(list(notas)); aferir(cb, amostras=6, semente=7)
    assert ca.consultas == cb.consultas, "a mesma semente tem que sortear o mesmo"

    cc = ColecaoFalsa(list(notas)); r = aferir(cc, amostras=6, semente=8)
    assert cc.consultas != ca.consultas, "sementes diferentes tem que sortear diferente"
    assert r["semente"] == 8, "a semente tem que voltar no resultado"


def test_colecao_sem_nota_utilizavel_nao_levanta():
    assert aferir(ColecaoFalsa([]), amostras=5)["recall"] is None


def test_a_ressalva_viaja_dentro_do_resultado():
    """O teste que impede o uso errado.

    Um numero solto seria usado para subir o limiar, e isso descartaria as
    perguntas parafraseadas que a calibracao de julho existiu para proteger.
    A ressalva precisa estar ao lado do numero, e nao num docstring que ninguem
    vai abrir daqui a tres meses.

    Conferido por mutacao: tirar a chave do dicionario derruba este teste.
    """
    col = ColecaoFalsa([(f"Ref/n{i}.md", _corpo(f"a{i}")) for i in range(4)])
    r = aferir(col, amostras=4, semente=1)
    assert "ressalva" in r
    assert "regressao" in r["ressalva"].lower()
    assert "limiar" in r["ressalva"].lower()
