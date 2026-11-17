"""Comparar a medicao de hoje com a de ontem, com a margem que a amostra permite.

## Por que a referencia existe

Sem ela o `afericao` devolve um numero solto, e numero solto nao detecta
regressao nenhuma. Foi exatamente assim que a calibracao de 31/07/2026
envelheceu em silencio: mediram uma vez, escreveram na nota, e o vault foi de
1.159 para 10.234 notas sem ninguem medir de novo.

E vale dizer, porque e o ponto: **eu criei o `afericao.py` sem chamador
nenhum**, que e precisamente o defeito que passei a noite inteira medindo em
capacidades alheias. Esta fatia e a ligacao.

## A margem nao e um numero escolhido a dedo

Uma amostra de 50 tem erro padrao de cerca de 0,065 no recall. Cravar "queda de
5% e regressao" produziria alarme toda semana por ruido de amostragem.

O corte e **duas vezes o erro padrao**, que e o que o tamanho da amostra
sustenta: 0,130 para 50 amostras e 0,154 para 30. Aumentar `--amostras`
estreita a margem sozinho, sem ninguem reescrever limite.
"""

from __future__ import annotations

import json

import pytest

from delegation_core import afericao


@pytest.fixture(autouse=True)
def arquivo_temporario(tmp_path, monkeypatch):
    """Nunca tocar a afericao real da maquina."""
    monkeypatch.setattr(afericao, "ARQUIVO", tmp_path / "afericao_busca.json")


def test_sem_referencia_gravada_le_None():
    assert afericao.ler_referencia() is None


def test_ida_e_volta():
    afericao.gravar_referencia({"recall": 0.7, "amostras": 50})
    lido = afericao.ler_referencia()
    assert lido["recall"] == 0.7


def test_referencia_ilegivel_vale_como_ausente():
    """O pior caso e nao ter com o que comparar, que e o estado de quem nunca
    gravou. Levantar aqui derrubaria a medicao por causa do arquivo dela."""
    afericao.ARQUIVO.write_text("{ nao e json", encoding="utf-8")
    assert afericao.ler_referencia() is None


def test_referencia_sem_recall_nao_conta():
    """Um dicionario qualquer nao e uma medicao."""
    afericao.ARQUIVO.write_text(json.dumps({"qualquer": 1}), encoding="utf-8")
    assert afericao.ler_referencia() is None


def test_primeira_medicao_nao_inventa_regressao():
    """None e diferente de "recall zero", e dizer que piorou seria invencao."""
    d = afericao.comparar_com_referencia({"recall": 0.7, "amostras": 50}, None)
    assert d["tem_referencia"] is False
    assert "piorou" not in d


def test_queda_dentro_da_margem_nao_e_regressao():
    """Com n=50 e p=0,7 a margem e 0,130: uma queda de 0,04 e ruido."""
    d = afericao.comparar_com_referencia({"recall": 0.66, "amostras": 50},
                                         {"recall": 0.70})
    assert d["piorou"] is False


def test_queda_acima_da_margem_e_regressao():
    d = afericao.comparar_com_referencia({"recall": 0.50, "amostras": 50},
                                         {"recall": 0.70})
    assert d["piorou"] is True
    assert "0.200" in d["veredito"] or "0.2" in d["veredito"]


def test_a_margem_ENCOLHE_com_mais_amostras():
    """A propriedade que faz o corte ser calculado e nao constante.

    Um limite fixo nao sabe quantas amostras voce tomou, e por isso alarma por
    ruido numa amostra pequena e deixa passar regressao numa grande.

    Conferido por mutacao: trocar a margem por uma constante derruba este
    teste.
    """
    pequena = afericao.comparar_com_referencia({"recall": 0.7, "amostras": 30},
                                               {"recall": 0.7})
    grande = afericao.comparar_com_referencia({"recall": 0.7, "amostras": 200},
                                              {"recall": 0.7})
    assert grande["margem"] < pequena["margem"], (
        f"amostra maior tem que dar margem menor: "
        f"{grande['margem']} contra {pequena['margem']}")


def test_a_mesma_queda_decide_diferente_conforme_a_amostra():
    """O efeito pratico da margem calculada: uma queda de 0,10 e ruido em 30
    amostras e regressao em 200."""
    queda = {"recall": 0.60}
    antes = {"recall": 0.70}
    assert afericao.comparar_com_referencia({**queda, "amostras": 30}, antes)["piorou"] is False
    assert afericao.comparar_com_referencia({**queda, "amostras": 200}, antes)["piorou"] is True


def test_o_comando_esta_registrado_e_despachado():
    """A LIGACAO, e ela e a razao desta fatia existir.

    O `afericao.py` entrou sem nenhum chamador fora dos testes, que e o mesmo
    defeito que este trabalho passou a noite medindo em capacidade alheia.

    Conferido por mutacao: tirar a entrada do despacho derruba este teste.
    """
    import inspect

    from delegation_core import cli

    fonte = inspect.getsource(cli)
    assert "def cmd_aferir_busca" in fonte, "o handler precisa existir"
    assert '"aferir-busca": cmd_aferir_busca' in fonte, (
        "o comando precisa estar no despacho; fora dele ninguem o alcanca")
    assert 'sub.add_parser("aferir-busca"' in fonte, (
        "o comando precisa estar no parser")
