"""Arquivar no vault so o que mudou.

Dois testes aqui carregam o argumento inteiro, e os dois guardam defeitos que
NAO apareceriam como erro, so como lentidao ou como ausencia:

- `test_a_data_do_frontmatter_nao_pode_invalidar_artigo_intocado` reproduz a
  armadilha que teria zerado a economia na virada do dia, em silencio.
- `test_nota_apagada_na_mao_volta_a_ser_escrita` guarda o unico modo de falha
  que o incremental introduz: vault silenciosamente incompleto.
"""

from __future__ import annotations

import json

from delegation_core import arquivamento


def _fm(data: str) -> str:
    """O frontmatter que `graphbridge._frontmatter` monta, com a data do dia."""
    return f"---\ntitle: Community 3\ndate: {data}\nsource: graph_build\n---\n\n"


def test_sem_manifesto_anterior_tudo_e_escrita():
    """O padrao seguro: primeira filagem se comporta como hoje."""
    plano = arquivamento.planejar({"a.md": "h1", "b.md": "h2"}, {})
    assert plano.escrever == ["a.md", "b.md"]
    assert plano.manter == []
    assert plano.apagar == []


def test_hash_igual_e_mantido_e_hash_diferente_e_reescrito():
    plano = arquivamento.planejar(
        {"igual.md": "h1", "mudou.md": "h2-novo"},
        {"igual.md": "h1", "mudou.md": "h2-velho"},
    )
    assert plano.manter == ["igual.md"]
    assert plano.escrever == ["mudou.md"]


def test_artigo_que_sumiu_do_grafo_e_apagado():
    """Comunidade renumerada deixa orfao, e orfao em vault poluil busca."""
    plano = arquivamento.planejar({"fica.md": "h"}, {"fica.md": "h", "sumiu.md": "x"})
    assert plano.apagar == ["sumiu.md"]
    assert plano.escrever == []


def test_a_data_do_frontmatter_nao_pode_invalidar_artigo_intocado():
    """A armadilha que teria matado a otimizacao em silencio.

    `_frontmatter` grava `date: <hoje>`. Hashear o ARQUIVO MONTADO daria 100%
    de acerto enquanto se testasse no mesmo dia e zero no dia seguinte: sem
    erro, sem aviso, o build so voltaria a demorar 4,5 minutos e ninguem
    ligaria uma coisa na outra.

    Aqui o mesmo corpo aparece com frontmatter de dois dias, e o plano tem que
    manter a nota.

    **Este teste sozinho nao pega a mutacao**, e dizer que pega seria mentira:
    ele chama `hash_do_corpo` ja com o corpo na mao, entao quem hashear o
    arquivo montado erra em outro lugar. O defeito mora na LIGACAO, e quem o
    pega e `test_a_virada_do_dia_nao_invalida_artigo_intocado`, em
    `test_graphbridge.py`, conferido por mutacao. O que fica guardado aqui e o
    contrato: corpo igual, hash igual, plano manda manter.
    """
    corpo = "## Community 3\n\nO mesmo texto que o grafo gerou ontem.\n"

    ontem = arquivamento.hash_do_corpo(corpo)
    hoje = arquivamento.hash_do_corpo(corpo)
    assert ontem == hoje, "o corpo nao mudou, o hash nao pode mudar"

    # e o arquivo montado, que e o que NAO deve ser hasheado, de fato difere
    assert (_fm("2026-09-24") + corpo) != (_fm("2026-09-25") + corpo)

    plano = arquivamento.planejar({"Community_3.md": hoje},
                                  {"Community_3.md": ontem})
    assert plano.manter == ["Community_3.md"]
    assert plano.escrever == []


def test_nota_apagada_na_mao_volta_a_ser_escrita(tmp_path):
    """O unico modo de falha que o incremental introduz, fechado.

    Sem `confirmar_no_disco`, apagar uma nota do vault na mao a perderia para
    sempre: o manifesto continuaria afirmando aquele hash e todo build
    seguinte pularia a escrita. O sintoma seria vault silenciosamente
    incompleto, nunca um erro.
    """
    (tmp_path / "existe.md").write_text("x", encoding="utf-8")
    anterior = {"existe.md": "h1", "apagada.md": "h2"}

    conferido = arquivamento.confirmar_no_disco(tmp_path, anterior)
    assert conferido == {"existe.md": "h1"}

    plano = arquivamento.planejar({"existe.md": "h1", "apagada.md": "h2"}, conferido)
    assert plano.escrever == ["apagada.md"], "a nota sumida tem que voltar"
    assert plano.manter == ["existe.md"]


def test_manifesto_ida_e_volta(tmp_path):
    arquivamento.gravar(tmp_path, {"a.md": "h1", "b.md": "h2"})
    assert arquivamento.ler(tmp_path) == {"a.md": "h1", "b.md": "h2"}


def test_sem_manifesto_le_vazio(tmp_path):
    assert arquivamento.ler(tmp_path) == {}


def test_manifesto_ilegivel_vale_como_ausente(tmp_path):
    """O pior caso e refazer tudo, que e o comportamento antigo. Levantar aqui
    derrubaria o build por causa de um arquivo de controle."""
    (tmp_path / arquivamento.NOME_MANIFESTO).write_text("{ nao e json",
                                                        encoding="utf-8")
    assert arquivamento.ler(tmp_path) == {}


def test_manifesto_com_forma_errada_nao_contamina(tmp_path):
    """JSON valido mas que nao e mapa de caminho para hash."""
    (tmp_path / arquivamento.NOME_MANIFESTO).write_text(json.dumps(["a", "b"]),
                                                        encoding="utf-8")
    assert arquivamento.ler(tmp_path) == {}


def test_a_gravacao_e_atomica_e_nao_deixa_temporario(tmp_path):
    """Pasta propria: o `conftest` deste repo planta arquivos em `tmp_path`."""
    saida = tmp_path / "saida"
    arquivamento.gravar(saida, {"a.md": "h"})
    sobrando = [p.name for p in saida.iterdir()
                if p.name != arquivamento.NOME_MANIFESTO
                and not p.name.endswith(".lock")]
    assert sobrando == [], f"sobrou {sobrando}"


def test_economia_e_a_fracao_poupada():
    plano = arquivamento.planejar(
        {f"a{i}.md": "h" for i in range(10)},
        {f"a{i}.md": "h" for i in range(7)},
    )
    assert len(plano.manter) == 7 and len(plano.escrever) == 3
    assert plano.economia == 0.7


def test_economia_de_plano_vazio_nao_divide_por_zero():
    assert arquivamento.planejar({}, {}).economia == 0.0
