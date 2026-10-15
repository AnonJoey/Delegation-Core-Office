"""A verificacao da migracao nao pode reprovar uma busca certa por causa de empate.

Em 15/10/2026 o `index-migrate` de uma instalacao reprovou duas vezes com "11 consultas
diferem da busca exata" num indice cujas 10.077 linhas (texto, metadados e vetores) eram
identicas. Eram trechos de nota igual atravessando o 10o lugar: qualquer desempate e
valido, mas o criterio comparava conjuntos de ids. Estes testes nao precisam do chromadb:
montam a exportacao neutra direto.
"""
import json

import numpy as np
import pytest

from delegation_core import migracao_indice as mig
from delegation_core.indice_sqlite import ColecaoSqlite

D = 64
K = mig.VIZINHOS


def _exportacao(tmp_path, M, posicoes):
    export = tmp_path / "export"
    col = export / "vault_bge"
    col.mkdir(parents=True)
    ids = [f"n{i}" for i in range(len(M))]
    with open(col / "linhas.jsonl", "w", encoding="utf-8") as f:
        for i, id_ in enumerate(ids):
            f.write(json.dumps({"id": id_, "documento": f"doc {i}", "metadados": {"i": i}}) + "\n")
    np.save(col / "vetores.npy", M.astype(np.float32))
    # o que o Chroma respondeu so alimenta a sobreposicao, nao o veredito
    Mn = M.astype(np.float64)
    Mn /= np.linalg.norm(Mn, axis=1, keepdims=True)
    viz = {str(p): [ids[j] for j in np.argsort(-(Mn @ Mn[p]))[:K]] for p in posicoes}
    (col / "vizinhos_chroma.json").write_text(json.dumps(viz))
    (export / "export.json").write_text(json.dumps({"colecoes": {"vault_bge": {
        "linhas": len(ids), "contagem_declarada": len(ids), "dim": int(M.shape[1]), "metadata": {}}}}))
    return export


def _verificar(tmp_path, M, posicoes):
    export = _exportacao(tmp_path, M, posicoes)
    alvo = tmp_path / "sqlite"
    mig.importar(export, alvo)
    return mig.verificar(export, alvo)["colecoes"]["vault_bge"]


def _matriz_com_quase_duplicatas(n=1500, grupos=40, tamanho=12, ruido=1e-7, semente=7):
    """Grupos de `tamanho` vetores quase iguais: o mesmo texto embutido varias vezes."""
    rng = np.random.default_rng(semente)
    M = rng.normal(size=(n, D)).astype(np.float32)
    for g in range(grupos):
        ini = g * tamanho
        M[ini + 1:ini + tamanho] = M[ini] + rng.normal(scale=ruido, size=(tamanho - 1, D)).astype(np.float32)
    return M


# ── o criterio em si ─────────────────────────────────────────────────────────

def _caso(notas):
    notas = np.asarray(notas, dtype=np.float64)
    return notas, {f"n{i}": i for i in range(len(notas))}


def test_desempate_diferente_do_exato_e_equivalente_mesmo_com_conjunto_diferente():
    # n2, n3 e n4 empatam no 3o lugar: o exato (ordem estavel) pega n2, o indice pegou n4
    notas, posicao = _caso([0.9, 0.8, 0.5, 0.5, 0.5, 0.1])
    meu = ["n0", "n1", "n4"]
    v = mig._confere_contra_o_exato(meu, [1 - notas[posicao[i]] for i in meu], notas, posicao, 3)
    assert v["equivalente"] is True
    assert v["conjunto_igual"] is False


def test_trocar_um_melhor_por_um_pior_nao_e_empate():
    notas, posicao = _caso([0.9, 0.8, 0.7, 0.5, 0.4, 0.3])
    meu = ["n0", "n2", "n3"]   # faltou n1 (0.8), entrou n3 (0.5)
    v = mig._confere_contra_o_exato(meu, [1 - notas[posicao[i]] for i in meu], notas, posicao, 3)
    assert v["equivalente"] is False
    assert v["maior_diferenca"] > 0.1


def test_o_pior_que_cabe_na_tolerancia_nao_mascara_um_melhor_que_ficou_de_fora():
    # todos os devolvidos tem nota >= a do 3o exato, e mesmo assim n1 (0.8) sumiu:
    # olhar so "a nota do 3o" aprovaria isto
    notas, posicao = _caso([0.9, 0.8, 0.5, 0.5, 0.5])
    meu = ["n0", "n2", "n3"]
    v = mig._confere_contra_o_exato(meu, [1 - notas[posicao[i]] for i in meu], notas, posicao, 3)
    assert v["equivalente"] is False


def test_nota_declarada_errada_reprova_mesmo_com_o_ranking_certo():
    notas, posicao = _caso([0.9, 0.8, 0.7, 0.1])
    meu = ["n0", "n1", "n2"]
    v = mig._confere_contra_o_exato(meu, [0.0, 0.0, 0.0], notas, posicao, 3)   # 1 - nota = 0.1, 0.2, 0.3
    assert v["equivalente"] is False


@pytest.mark.parametrize("meu", [["n0", "n1"], ["n0", "n0", "n1"], ["n0", "n1", "fantasma"]])
def test_resposta_com_tamanho_errado_repetida_ou_com_id_inexistente_reprova(meu):
    notas, posicao = _caso([0.9, 0.8, 0.7, 0.1])
    v = mig._confere_contra_o_exato(meu, [0.1] * len(meu), notas, posicao, 3)
    assert v["equivalente"] is False


# ── de ponta a ponta ─────────────────────────────────────────────────────────

def test_verificar_aprova_indice_correto_cheio_de_quase_duplicatas(tmp_path):
    M = _matriz_com_quase_duplicatas()
    posicoes = list(range(0, 480, 12)) + [700, 900, 1100, 1300]   # dentro dos grupos e fora deles
    r = _verificar(tmp_path, M, posicoes)
    assert r["problemas"] == []
    assert r["ok"]
    assert r["consultas"] == len(posicoes)
    assert r["consultas_iguais_a_busca_exata"] == len(posicoes)
    assert "consultas_com_empate" in r


def test_verificar_reprova_busca_que_some_com_o_melhor_resultado(tmp_path, monkeypatch):
    M = _matriz_com_quase_duplicatas()
    original = ColecaoSqlite.query

    def sem_o_melhor(self, *a, n_results=10, **kw):
        r = original(self, *a, n_results=n_results + 1, **kw)
        for chave in ("ids", "distances", "metadatas", "documents"):
            if r.get(chave) is not None:
                r[chave] = [linha[1:] for linha in r[chave]]
        return r

    monkeypatch.setattr(ColecaoSqlite, "query", sem_o_melhor)
    # fora dos grupos: dentro de um grupo de clones, trocar um por outro e valido
    r = _verificar(tmp_path, M, [700, 900, 1100, 1300, 1400, 1450])
    assert not r["ok"]
    assert any("diferem da busca exata" in p for p in r["problemas"])
    assert r["consultas_iguais_a_busca_exata"] == 0


def test_verificar_reprova_busca_que_devolve_distancia_errada(tmp_path, monkeypatch):
    M = _matriz_com_quase_duplicatas()
    original = ColecaoSqlite.query

    def distancia_errada(self, *a, **kw):
        r = original(self, *a, **kw)
        r["distances"] = [[d + 0.05 for d in linha] for linha in r["distances"]]
        return r

    monkeypatch.setattr(ColecaoSqlite, "query", distancia_errada)
    r = _verificar(tmp_path, M, list(range(0, 480, 12)))
    assert not r["ok"]
