"""Resumo de inicio de sessao: o trecho L0 e L1 de uma nota e a conta dos niveis.

A paridade com o ai-memory compilado e conferida por `scripts/paridade_ai_memory.py`.
"""

from __future__ import annotations

from delegation_core.envelhecimento import compactar
from delegation_core.resumo_inicial.niveis import CustoDaNota, Nivel, Orcamento, atribuir_niveis
from delegation_core.resumo_inicial.trecho import eh_campo_de_metadado, prosa_de_abertura, trecho_da_nota


def test_abstract_manda_no_l0_e_summary_no_l1():
    t = trecho_da_nota({"abstract": "Resumo A", "summary": "Resumo S"}, "corpo")
    assert (t.l0, t.l1) == ("Resumo A", "Resumo S")


def test_so_um_dos_dois_serve_aos_dois_niveis():
    assert trecho_da_nota({"summary": "S"}, "corpo") == trecho_da_nota({"abstract": "S"}, "corpo")


def test_sem_resumo_vem_a_prosa_de_abertura_sem_titulo_nem_metadado():
    corpo = "# Titulo\n\n**Status:** Accepted\n**Date:** 2026\n\nPrimeira frase real.\nSegunda linha.\n"
    assert trecho_da_nota({}, corpo).l0 == "Primeira frase real. Segunda linha."


def test_nota_sem_texto_nao_tem_trecho():
    t = trecho_da_nota(None, "# So titulo\n\n---\n")
    assert t.l0 is None and t.l1 is None
    assert trecho_da_nota({"abstract": "   ", "summary": 7}, "").l0 is None


def test_l0_e_l1_cortam_em_bytes_sem_partir_caractere():
    t = trecho_da_nota({}, "é" * 300)
    assert len(t.l0.encode()) <= 256 and len(t.l1.encode()) <= 500
    t.l0.encode("utf-8")
    t.l1.encode("utf-8")


def test_nota_compactada_nao_mostra_o_rodape_como_trecho():
    fm, corpo = compactar({}, "")
    assert trecho_da_nota(fm, corpo).l0 is None
    fm, corpo = compactar({}, "Falha no deploy.\n\nVeja src/app/main.py.\n")
    assert trecho_da_nota(fm, corpo).l0.startswith("Falha no deploy.")
    assert "Extractively compacted" not in (trecho_da_nota(fm, corpo).l1 or "")


def test_campo_de_metadado():
    assert eh_campo_de_metadado("**Status:** Accepted")
    assert eh_campo_de_metadado("**Date**: 2026-10-17")
    assert eh_campo_de_metadado("- __Owner:__ time de infra")
    assert not eh_campo_de_metadado("Date: 2026-10-17")  # sem destaque no rotulo e afirmacao, nao metadado
    assert not eh_campo_de_metadado("**Gerenciador de pacotes:** pnpm")  # o rotulo nao e de ADR
    assert not eh_campo_de_metadado("Status: this is a long sentence with many many words")
    assert not eh_campo_de_metadado("random line")


def test_prosa_de_abertura_pula_cerca_e_titulo():
    assert prosa_de_abertura("---\n---\n# T\n\nTexto aqui.") == "Texto aqui."
    assert prosa_de_abertura("# So titulo") is None


# ── niveis ─────────────────────────────────────────────────────────────────

ORC = Orcamento(prefixo=100, teto_do_conteudo=1000, recentes_inteiro=200, recentes_primeiro=40)


def _nota(l0=50, l1=120, l2=400, privilegiada=False, titulo=20):
    return CustoDaNota(privilegiada, titulo, (l0, l1, l2))


def _plano(notas, orc=ORC):
    return atribuir_niveis(notas, orc, lambda de: 30 + 10 * (len(notas) - de), lambda n: 12)


def test_cobertura_primeiro_toda_nota_que_cabe_ganha_ao_menos_o_l0():
    p = _plano([_nota() for _ in range(5)])
    assert all(n >= Nivel.L0 for n in p.niveis) and p.omitidas_a_partir == 5


def test_o_que_nao_cabe_e_omitido_a_partir_de_um_indice():
    p = _plano([_nota(l0=300, l1=400, l2=900) for _ in range(6)])
    assert p.omitidas_a_partir < 6
    assert all(n == Nivel.OMITIDA for n in p.niveis[p.omitidas_a_partir:])
    assert all(n >= Nivel.L0 for n in p.niveis[:p.omitidas_a_partir])


def test_privilegiada_e_aprofundada_antes_da_comum():
    # sobra pouca: so uma das duas notas sobe para L1, e e a privilegiada, mesmo vindo depois
    notas = [_nota(l0=100, l1=300, l2=900), _nota(l0=100, l1=300, l2=900, privilegiada=True)]
    p = _plano(notas, Orcamento(prefixo=100, teto_do_conteudo=600, recentes_inteiro=0, recentes_primeiro=0))
    assert p.niveis[1] > p.niveis[0]


def test_nota_sem_trecho_fica_so_com_o_titulo():
    p = _plano([CustoDaNota(False, 30, None), _nota()])
    assert p.niveis[0] == Nivel.SO_TITULO and p.niveis[1] >= Nivel.L0


def test_corpo_curto_completa_com_a_folga():
    # L2 passa do L1 por exatamente a folga: sobe mesmo com outras notas ainda esperando o L1
    comum = _nota(l0=50, l1=120, l2=120 + 128)
    p = _plano([comum])
    assert p.niveis[0] == Nivel.L2
    longo = _nota(l0=50, l1=120, l2=120 + 128 + 1)
    assert _plano([longo, _nota(l0=50, l1=900, l2=900)]).niveis[0] < Nivel.L2


def test_sem_notas_o_plano_e_vazio():
    p = _plano([])
    assert p.niveis == [] and p.omitidas_a_partir == 0


def test_orcamento_menor_que_o_prefixo_nao_estoura():
    p = _plano([_nota()], Orcamento(prefixo=500, teto_do_conteudo=100, recentes_inteiro=10, recentes_primeiro=5))
    assert p.niveis == [Nivel.OMITIDA]


def test_nota_que_cabe_exatamente_no_teto_da_cobertura_entra():
    # teto 500, menos a contagem das omitidas (12): a cobertura vai ate 488; 100 de prefixo + 388 de L0 = 488
    orc = Orcamento(prefixo=100, teto_do_conteudo=500, recentes_inteiro=0, recentes_primeiro=0)
    assert _plano([_nota(l0=388, l1=388, l2=388)], orc).niveis == [Nivel.L0]
    assert _plano([_nota(l0=389, l1=389, l2=389)], orc).niveis == [Nivel.OMITIDA]


def test_a_contagem_das_omitidas_e_reservada_antes_da_cobertura():
    orc = Orcamento(prefixo=100, teto_do_conteudo=500, recentes_inteiro=0, recentes_primeiro=0)
    # sem a reserva de 12 bytes a segunda nota (100 + 200 + 200 = 500) caberia; com ela, nao
    p = _plano([_nota(l0=200, l1=200, l2=200), _nota(l0=200, l1=200, l2=200)], orc)
    assert p.omitidas_a_partir == 1 and p.niveis == [Nivel.L0, Nivel.OMITIDA]


def test_orcamento_menor_que_o_prefixo_nao_reserva_nada_para_recentes():
    p = _plano([_nota()], Orcamento(prefixo=500, teto_do_conteudo=100, recentes_inteiro=10, recentes_primeiro=5))
    assert p.reserva_de_recentes == 0
