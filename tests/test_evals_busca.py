"""Evals da busca: um numero que muda quando a busca muda.

O que isto mede, e o que nao mede
---------------------------------
Mede o CAMINHO de busca do indice SQLite: a busca vetorial exata, a lexical
(BM25 sobre trigramas, FTS5) e a hibrida por fusao RRF, sobre um vault de teste
de 40 notas e 40 perguntas com a nota esperada de cada uma
(`tests/evals_busca/corpus.json`).

NAO mede a qualidade do BGE-M3. O embedder aqui e um saco de palavras
deterministico, porque o CI roda offline e sem baixar modelo. Trocar o modelo de
embeddings pede outra avaliacao, com o modelo real; esta pega regressao do
indice, do filtro, da fusao e da busca de texto.

Como funciona a guarda
----------------------
`tests/evals_busca/baseline.json` guarda as metricas medidas de cada modo. A
suite falha se alguma cair abaixo do valor guardado. Melhorar nao falha: depois
de uma melhora de verdade, rode

    pytest tests/test_evals_busca.py -s --atualizar-baseline-evals

para regravar o arquivo, e explique a mudanca no commit. O teste de
sensibilidade garante que a guarda enxerga uma busca pior: uma busca que
devolve a ordem invertida derruba o MRR.

Metricas, por modo: acerto na 1a posicao (hit@1), no top 3 (hit@3), no top 5
(hit@5) e MRR (media do inverso da posicao da nota esperada; 0 se ela nao vem
nos 5 primeiros).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pytest

from delegation_core.indice_sqlite import ClienteSqlite

PASTA = Path(__file__).parent / "evals_busca"
CORPUS = json.loads((PASTA / "corpus.json").read_text(encoding="utf-8"))
BASELINE = PASTA / "baseline.json"
N = 5
MODOS = ("vetorial", "lexical", "hibrida")
METRICAS = ("hit@1", "hit@3", "hit@5", "mrr")

DIM = 512
_PARADAS = frozenset(
    "the and for with that this from are was were has have had not but how what why when who where "
    "does did can could should would our out any all one two into than then they them their its "
    "about after before over under per via only still".split())


def _radical(p: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if p.endswith(suf) and len(p) - len(suf) >= 3:
            return p[: -len(suf)]
    return p


def _tokens(texto: str) -> list[str]:
    return [_radical(p) for p in re.findall(r"[a-z0-9]+", texto.lower())
            if len(p) >= 3 and p not in _PARADAS]


class EmbedderLexico:
    """Saco de palavras com hash em 512 dimensoes: deterministico e sem rede."""

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002 (nome do protocolo)
        saida = []
        for texto in input:
            v = np.zeros(DIM, dtype=np.float32)
            for t in _tokens(texto):
                h = int(hashlib.md5(t.encode()).hexdigest(), 16)
                v[h % DIM] += 1.0
            saida.append(v.tolist())
        return saida


def _construir(tmp_path):
    cliente = ClienteSqlite(tmp_path / "indice")
    col = cliente.get_or_create_collection("evals", embedding_function=EmbedderLexico())
    ids = list(CORPUS["notas"])
    col.add(ids=ids, documents=[CORPUS["notas"][i] for i in ids],
            metadatas=[{"nota": i} for i in ids])
    return cliente, col


def _buscar(col, modo: str, pergunta: str) -> list[str]:
    if modo == "vetorial":
        return col.query(query_texts=[pergunta], n_results=N)["ids"][0]
    if modo == "lexical":
        return col.buscar_texto(pergunta, n_results=N)["ids"]
    return col.hibrida(pergunta, n_results=N)["ids"]


def avaliar(col, modo: str, buscar=_buscar) -> dict[str, float]:
    posicoes = []
    for q in CORPUS["perguntas"]:
        ids = buscar(col, modo, q["pergunta"])
        posicoes.append(ids.index(q["esperada"]) + 1 if q["esperada"] in ids else None)
    n = len(posicoes)
    return {
        "hit@1": sum(p == 1 for p in posicoes) / n,
        "hit@3": sum(p is not None and p <= 3 for p in posicoes) / n,
        "hit@5": sum(p is not None for p in posicoes) / n,
        "mrr": sum(1 / p for p in posicoes if p) / n,
    }


@pytest.fixture(scope="module")
def indice(tmp_path_factory):
    cliente, col = _construir(tmp_path_factory.mktemp("evals"))
    yield col
    cliente.close()


@pytest.fixture(scope="module")
def medidas(indice):
    return {m: avaliar(indice, m) for m in MODOS}


def _tabela(medidas: dict) -> str:
    linhas = [f"{'modo':10s} " + " ".join(f"{k:>7s}" for k in METRICAS)]
    for m in MODOS:
        linhas.append(f"{m:10s} " + " ".join(f"{medidas[m][k]:7.3f}" for k in METRICAS))
    return "\n".join(linhas)


def test_o_corpus_e_coerente():
    notas = CORPUS["notas"]
    assert len(notas) == 40 and len(CORPUS["perguntas"]) == 40
    esperadas = [q["esperada"] for q in CORPUS["perguntas"]]
    assert all(e in notas for e in esperadas)
    assert len(set(esperadas)) == len(esperadas), "duas perguntas para a mesma nota escondem regressao"


def test_nenhum_modo_cai_abaixo_da_linha_de_base(medidas, request, capsys):
    with capsys.disabled():
        print("\n" + _tabela(medidas))
    if request.config.getoption("--atualizar-baseline-evals"):
        BASELINE.write_text(json.dumps(
            {m: {k: round(v, 4) for k, v in medidas[m].items()} for m in MODOS}, indent=1) + "\n",
            encoding="utf-8")
        pytest.skip("linha de base regravada")
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    quedas = [f"{m} {k}: {medidas[m][k]:.3f} < {base[m][k]:.3f}"
              for m in MODOS for k in METRICAS if medidas[m][k] + 5e-4 < base[m][k]]
    assert not quedas, "a busca piorou nos evals:\n  " + "\n  ".join(quedas)


def test_a_guarda_enxerga_uma_busca_pior(indice, medidas):
    """Se a ordem do resultado for invertida, o numero tem que cair de verdade."""
    def invertida(col, modo, pergunta):
        return list(reversed(_buscar(col, modo, pergunta)))

    for modo in MODOS:
        pior = avaliar(indice, modo, buscar=invertida)
        assert pior["mrr"] < medidas[modo]["mrr"] - 0.1, (
            f"{modo}: inverter a ordem nao mexeu no MRR ({pior['mrr']:.3f} contra {medidas[modo]['mrr']:.3f}); "
            "a metrica nao enxerga a ordem")


def test_a_hibrida_nao_e_pior_que_o_melhor_dos_dois_por_mais_de_uma_margem(medidas):
    melhor = max(medidas["vetorial"]["mrr"], medidas["lexical"]["mrr"])
    assert medidas["hibrida"]["mrr"] >= melhor - 0.05, (
        "a fusao RRF ficou claramente pior que o melhor dos dois modos sozinhos")
