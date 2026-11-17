"""Pacote ranqueamento: indice lexico, RRF e reordenacao.

O reordenador real (cross-encoder de 2 GB) nao carrega aqui: o contrato do
pacote e o metodo `pontuar`, e um dublê com esse metodo prova a composicao.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from delegation_core.ranqueamento import IndiceLexico, combinar, reordenar, rrf
from delegation_core.ranqueamento.lexico import montar_match, termos_da_consulta

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "ranqueamento"


@pytest.fixture
def idx(tmp_path):
    i = IndiceLexico(tmp_path / "lx.sqlite3")
    yield i
    i.fechar()


def _doc(caminho, mtime, titulo, corpo):
    return (caminho, mtime, lambda: (titulo, corpo))


# ── lexico ──────────────────────────────────────────────────────────────────

def test_acento_nao_impede_o_acerto(idx):
    idx.gravar("a.md", 1, "Contenção de GPU", "o llama e o BGE disputavam a placa")
    idx.gravar("b.md", 1, "Receita de bolo", "farinha e ovos")
    assert [c for c, _ in idx.buscar("contencao")] == ["a.md"]


def test_palavra_ausente_nao_zera_a_busca(idx):
    """Unir por AND, o padrao do FTS5, zeraria esta consulta: 'resolver' nao existe na nota."""
    idx.gravar("a.md", 1, "GPU", "contencao entre BGE e llama na placa")
    assert idx.buscar("como resolver a contencao da placa")[0][0] == "a.md"


def test_identificador_com_ponto_e_hifen_acha_a_nota(idx):
    idx.gravar("a.md", 1, "Notas", "a versao v0.12 trocou o bge-m3 de lugar")
    idx.gravar("b.md", 1, "Outra", "versao nova do modelo")
    assert idx.buscar("bge-m3")[0][0] == "a.md"


def test_titulo_pesa_mais_que_corpo(idx):
    """Caso escolhido por medicao: com pesos iguais o corpo vence (duas ocorrencias
    contra uma), e so o peso 3 do titulo inverte. Um caso com titulo de uma palavra
    passava com qualquer peso, porque o BM25 normaliza pelo tamanho do campo."""
    idx.gravar("corpo.md", 1, "Notas diversas sobre o sistema",
               "arbitro arbitro da placa e outras coisas longas")
    idx.gravar("titulo.md", 1, "Arbitro da placa de video",
               "texto sem a palavra, falando de outras coisas longas")
    assert idx.buscar("arbitro")[0][0] == "titulo.md"


def test_pontuacao_maior_e_melhor(idx):
    idx.gravar("forte.md", 1, "gpu gpu", "gpu gpu gpu")
    idx.gravar("fraco.md", 1, "x", "gpu " + "outra " * 40)
    r = idx.buscar("gpu")
    assert r[0][0] == "forte.md" and r[0][1] > r[1][1] > 0


def test_atualizar_so_rele_o_que_mudou_e_remove_o_que_sumiu(idx):
    lidos = []

    def doc(c, m):
        return (c, m, lambda: (lidos.append(c), (c, "texto de " + c))[1])

    assert idx.atualizar([doc("a.md", 1), doc("b.md", 1)])["gravados"] == 2
    lidos.clear()
    r = idx.atualizar([doc("a.md", 1), doc("b.md", 2)])
    assert lidos == ["b.md"] and r["gravados"] == 1
    r = idx.atualizar([doc("b.md", 2)])
    assert r["removidos"] == 1 and len(idx) == 1
    assert idx.buscar("texto") == [("b.md", idx.buscar("texto")[0][1])]


def test_regravar_nao_duplica(idx):
    idx.gravar("a.md", 1, "t", "alfa")
    idx.gravar("a.md", 2, "t", "beta")
    assert idx.buscar("alfa") == [] and len(idx.buscar("beta")) == 1 and len(idx) == 1


def test_consulta_sem_termo_util_devolve_vazio(idx):
    idx.gravar("a.md", 1, "t", "de para com")
    assert idx.buscar("de para com") == [] and idx.buscar("") == []


def test_aspas_na_consulta_nao_quebram(idx):
    idx.gravar("a.md", 1, "t", 'ele disse "ola" ontem')
    assert idx.buscar('disse "ola') and montar_match('ab"cd') == '"ab" OR "cd"'


def test_termos_sem_repeticao_e_sem_vazias():
    assert termos_da_consulta("A GPU e a gpu de novo") == ["gpu", "novo"]


# ── fusao ───────────────────────────────────────────────────────────────────

def test_rrf_premia_quem_aparece_nas_duas():
    r = [d for d, _ in rrf([["a", "b", "c"], ["c", "d", "a"]])]
    assert r[:2] == ["a", "c"]


def test_rrf_ordem_estavel_no_empate():
    """z e a empatam (posicao 1 em listas distintas); vale a ordem de chegada,
    e os ids estao fora da ordem alfabetica para que desempate por nome falhe."""
    assert [d for d, _ in rrf([["z"], ["a"]])] == ["z", "a"]


def test_rrf_repeticao_na_mesma_lista_conta_uma_vez():
    r = dict(rrf([["a", "a", "b"]]))
    assert r["a"] == pytest.approx(1 / 61)


def test_rrf_peso_muda_a_ordem():
    assert rrf([["a"], ["b"]], pesos=[1.0, 2.0])[0][0] == "b"


def test_rrf_peso_por_lista_e_obrigatorio():
    with pytest.raises(ValueError):
        rrf([["a"], ["b"]], pesos=[1.0])


# ── reordenacao e composicao ───────────────────────────────────────────────

class Dublê:
    """Pontua pela contagem da palavra 'certo' no texto."""

    def __init__(self):
        self.chamadas = []

    def pontuar(self, consulta, textos):
        self.chamadas.append(list(textos))
        return [float(t.count("certo")) for t in textos]


def test_reordenar_segue_a_pontuacao_e_estabiliza_empate():
    r = reordenar("q", [("x", "nada"), ("y", "certo"), ("z", "nada")], Dublê())
    assert [d for d, _ in r] == ["y", "x", "z"]


def test_combinar_sem_reordenador_e_so_a_fusao():
    assert combinar("q", ["a", "b"], ["b", "c"], limite=3) == ["b", "a", "c"]


def test_combinar_reordena_so_o_topo_e_preserva_o_resto():
    textos = {"a": "", "b": "", "c": "certo", "d": "certo certo"}
    d = Dublê()
    r = combinar("q", ["a", "b", "c", "d"], [], limite=4, reordenador=d,
                 texto_de=textos.get, profundidade_rerank=3)
    # o topo (a, b, c) e reordenado: c sobe; d fica atras mesmo pontuando mais,
    # porque nao entrou na profundidade
    assert r == ["c", "a", "b", "d"]
    assert d.chamadas == [["", "", "certo"]]


# ── criterio de lego ────────────────────────────────────────────────────────

def test_pacote_nao_importa_o_nucleo():
    """Independente de verdade: nenhum modulo do pacote importa config, vault, server..."""
    proibidos = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            # `texto_bytes` e uma folha de biblioteca padrao (espaco, linha, letra e tamanho como o Rust os ve),
            # compartilhada pelos portes do ai-memory; nao e o nucleo (config, vault, server...).
            if isinstance(no, ast.ImportFrom) and no.level >= 2 and no.module != "texto_bytes":
                proibidos.append(f"{arq.name}: from {'.' * no.level}{no.module}")
            if isinstance(no, ast.ImportFrom) and (no.module or "").startswith("delegation_core"):
                proibidos.append(f"{arq.name}: from {no.module}")
    assert proibidos == []


def test_lexico_dominante_vai_para_o_topo_depois_da_reordenacao():
    textos = {"a": "certo certo", "b": "certo", "lx": ""}
    r = combinar("q", ["a", "b"], ["lx", "a"], limite=3, reordenador=Dublê(), texto_de=textos.get,
                 pontos_lexicos=[3.0, 1.0], razao_dominante=1.5)
    assert r[0] == "lx"


def test_lexico_sem_dominancia_nao_mexe():
    textos = {"a": "certo certo", "b": "certo", "lx": ""}
    r = combinar("q", ["a", "b"], ["lx", "a"], limite=3, reordenador=Dublê(), texto_de=textos.get,
                 pontos_lexicos=[1.4, 1.0], razao_dominante=1.5)
    assert r[0] == "a"


def test_sem_razao_configurada_nao_mexe():
    textos = {"a": "certo certo", "lx": ""}
    r = combinar("q", ["a"], ["lx", "a"], limite=2, reordenador=Dublê(), texto_de=textos.get,
                 pontos_lexicos=[9.0, 1.0])
    assert r[0] == "a"


def test_lexico_unico_e_dominante():
    textos = {"a": "certo", "lx": ""}
    r = combinar("q", ["a"], ["lx"], limite=2, reordenador=Dublê(), texto_de=textos.get,
                 pontos_lexicos=[0.5], razao_dominante=1.5)
    assert r == ["lx", "a"]
