"""Pacote envelhecimento: retencao, fatos duraveis, compactacao, planejador da varredura e contadores de uso.

A paridade com o ai-memory compilado e conferida por `scripts/paridade_ai_memory.py`; estes testes
fixam o comportamento com exemplos escritos a mao, para o que roda sem o binario Rust.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from delegation_core.envelhecimento import (
    Parametros,
    RODAPE,
    compactar,
    lambda_da_meia_vida,
    minerar_fatos,
    pontuacao,
    residuo,
    saliencia_depois_do_voto,
)
from delegation_core.envelhecimento.acessos import Acessos
from delegation_core.envelhecimento.varredura import Nota, dias_decorridos, e_decaivel, entrada_fria, planejar

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "envelhecimento"
DIA = 86_400_000_000
AGORA = 1_760_000_000_000_000
P = Parametros()


# ── retencao ───────────────────────────────────────────────────────────────


def test_nota_nova_e_nunca_usada_vale_a_saliencia_padrao():
    assert pontuacao(P, "episodic", 0.0, 0, None) == pytest.approx(1.0)


def test_sem_uso_cai_abaixo_do_limiar_em_cerca_de_80_dias():
    assert pontuacao(P, "episodic", 79.0, 0, None) > P.limiar_frio
    assert pontuacao(P, "episodic", 81.0, 0, None) < P.limiar_frio


def test_cada_leitura_reforca_e_o_reforco_esquece():
    sem = pontuacao(P, "episodic", 100.0, 0, None)
    lida_hoje = pontuacao(P, "episodic", 100.0, 5, 0.0)
    lida_faz_tempo = pontuacao(P, "episodic", 100.0, 5, 200.0)
    assert lida_hoje > lida_faz_tempo > sem
    assert lida_hoje > P.limiar_frio  # uma nota relida volta a valer


def test_o_reforco_cresce_devagar_com_a_contagem():
    a = pontuacao(P, "episodic", 100.0, 1, 0.0) - pontuacao(P, "episodic", 100.0, 0, 0.0)
    b = pontuacao(P, "episodic", 100.0, 100, 0.0) - pontuacao(P, "episodic", 100.0, 1, 0.0)
    assert 0 < a < b < 100 * a


def test_lambda_por_camada_deixa_o_trabalho_esquecer_mais_depressa():
    p = Parametros(lambda_por_camada={"working": 0.2})
    assert pontuacao(p, "working", 10.0, 0, None) < pontuacao(p, "episodic", 10.0, 0, None)
    assert pontuacao(p, "episodic", 10.0, 0, None) == pontuacao(P, "episodic", 10.0, 0, None)


def test_lambda_da_meia_vida():
    assert lambda_da_meia_vida(35.0) == pytest.approx(math.log(2) / 35.0)
    assert lambda_da_meia_vida(0) == math.inf


def test_amplitude_so_conta_com_peso_positivo_e_mais_de_um_leitor():
    base = pontuacao(P, "episodic", 50.0, 4, 1.0)
    assert pontuacao(P, "episodic", 50.0, 4, 1.0, None, 9, 0.0) == base
    assert pontuacao(P, "episodic", 50.0, 4, 1.0, None, 1, 1.0) == base
    assert pontuacao(P, "episodic", 50.0, 4, 1.0, None, 9, 1.0) > base
    # peso invalido desliga o bonus em vez de estragar a nota
    for ruim in (-1.0, math.nan, math.inf):
        assert pontuacao(P, "episodic", 50.0, 4, 1.0, None, 9, ruim) == base


@pytest.mark.parametrize("voto,atual,esperado", [
    ("helpful", None, 1.25), ("helpful", 2.0, 2.0), ("not_helpful", None, 0.75), ("not_helpful", 0.25, 0.25),
    ("stale", 2.0, 0.25), ("wrong", None, 0.25),
])
def test_voto_move_a_saliencia_um_degrau_dentro_da_faixa(voto, atual, esperado):
    assert saliencia_depois_do_voto(P, atual, voto) == esperado


def test_voto_desconhecido_e_recusado():
    with pytest.raises(ValueError):
        saliencia_depois_do_voto(P, 1.0, "talvez")


# ── fatos duraveis ─────────────────────────────────────────────────────────


def test_prosa_pura_nao_tem_fato_duravel():
    assert minerar_fatos("We talked about the plan. Everyone agreed it was subtle.") == []


def test_fatos_saem_na_ordem_das_classes_e_sem_repeticao():
    corpo = "Veja https://github.com/x/y/issues/7. Erro E0433 e HTTP 500 em crates/a/src/lib.rs, de novo crates/a/src/lib.rs. Constante AI_MEMORY_TOKEN."
    f = minerar_fatos(corpo)
    assert f[0] == "https://github.com/x/y/issues/7"
    assert "crates/a/src/lib.rs" in f and f.count("crates/a/src/lib.rs") == 1
    assert {"E0433", "HTTP 500", "AI_MEMORY_TOKEN"} <= set(f)
    assert f.index("https://github.com/x/y/issues/7") < f.index("E0433") < f.index("AI_MEMORY_TOKEN")


def test_url_perde_a_pontuacao_do_fim_da_frase():
    assert minerar_fatos("Abra (https://exemplo.org/a/b).") == ["https://exemplo.org/a/b"]


def test_limite_de_quantidade_e_de_tamanho():
    muitos = " ".join(f"arquivo_{i}.py" for i in range(200))
    assert len(minerar_fatos(muitos)) == 48
    assert minerar_fatos("`" + "z" * 130 + "`") == []  # mais de 128 bytes
    assert minerar_fatos("`a`") == []  # menos de 2 bytes


def test_espaco_unicode_que_o_rust_nao_chama_de_espaco_nao_encerra_a_url():
    # \x1c e espaco para o `\s` do Python e nao para o do Rust
    assert minerar_fatos("https://a.b/c\x1cdepois") == ["https://a.b/c\x1cdepois"]


def test_residuo_pega_diagnostico_versao_e_ip_e_respeita_o_maximo():
    corpo = "error[E0433]: failed to resolve\nrodando em 192.0.2.11 com v2.6.3-rc1\n"
    r = residuo(corpo, 8)
    assert r[0].startswith("error[E0433]: failed to resolve")
    assert "192.0.2.11" in r and "v2.6.3-rc1" in r
    assert residuo(corpo, 1) == r[:1]
    assert residuo(corpo, 0) == []


# ── compactacao ────────────────────────────────────────────────────────────


def test_compactar_guarda_resumo_fatos_e_rodape_e_marca_o_frontmatter():
    fm, corpo = compactar({"summary": "Falha no deploy.", "tags": ["x"]}, "Longa prosa.\n\nVeja src/app/main.py e E0433.\n")
    assert fm["compacted"] is True and fm["summary"] == "Falha no deploy." and fm["tags"] == ["x"]
    assert corpo.startswith("Falha no deploy.\n\n## Retained facts\n\n")
    assert "- `src/app/main.py`\n" in corpo and "- `E0433`\n" in corpo
    assert corpo.endswith(RODAPE + "\n")
    assert "Longa prosa" not in corpo


def test_compactar_sem_summary_usa_o_primeiro_paragrafo_e_pula_titulo():
    _, corpo = compactar({}, "# Titulo\n\n  Primeira   linha\n com quebra.\n\nSegundo.\n")
    assert corpo.startswith("Primeira linha com quebra.\n\n")


def test_compactar_nao_muda_o_frontmatter_de_quem_chamou():
    original = {"summary": "x"}
    compactar(original, "corpo")
    assert original == {"summary": "x"}


def test_compactar_aceita_frontmatter_que_nao_e_dicionario():
    fm, corpo = compactar(None, "so prosa aqui")
    assert fm == {"compacted": True} and corpo.startswith("so prosa aqui\n\n")


def test_resumo_longo_e_cortado_em_500_bytes_com_reticencias():
    _, corpo = compactar({"summary": "é" * 400}, "x")
    resumo = corpo.split("\n\n")[0]
    assert resumo.endswith("…") and len(resumo[:-1].encode()) <= 500


def test_rodape_reconhecido_pelo_resumo_inicial():
    from delegation_core.resumo_inicial.trecho import COMPACTION_FOOTER_PREFIX

    assert RODAPE.startswith(COMPACTION_FOOTER_PREFIX)


# ── varredura ──────────────────────────────────────────────────────────────


def _nota(dias=0, **kw):
    kw.setdefault("camada", "episodic")
    return Nota(caminho=kw.pop("caminho", "Sessions/a.md"), atualizada_em_us=AGORA - int(dias * DIA), **kw)


def test_so_a_camada_episodica_esfria():
    for camada in ("semantic", "procedural", "working"):
        assert not e_decaivel(_nota(camada=camada))
    assert e_decaivel(_nota())


def test_nota_fixada_pelo_campo_ou_pelo_frontmatter_nao_esfria():
    assert not e_decaivel(_nota(fixada=True))
    assert not e_decaivel(_nota(frontmatter={"pinned": True}))
    for nao_e_pin in ({"pinned": False}, {"pinned": "true"}, {"pinned": 1}, {}, None):
        assert e_decaivel(_nota(frontmatter=nao_e_pin))


def test_fria_so_abaixo_do_limiar():
    assert entrada_fria(_nota(dias=79), P, AGORA) is None
    f = entrada_fria(_nota(dias=120), P, AGORA)
    assert f is not None and f.retencao < P.limiar_frio and f.idade_dias == pytest.approx(120.0)


def test_retencao_igual_ao_limiar_ainda_nao_e_fria():
    # nota de hoje, nunca lida: retencao exatamente 1.0 (a saliencia padrao)
    assert entrada_fria(_nota(dias=0), Parametros(limiar_frio=1.0), AGORA) is None
    assert entrada_fria(_nota(dias=0), Parametros(limiar_frio=1.0000001), AGORA) is not None


def test_leitura_recente_salva_a_nota_velha():
    n = _nota(dias=120, acessos=6, ultimo_acesso_us=AGORA - DIA)
    assert entrada_fria(n, P, AGORA) is None


def test_nota_do_futuro_tem_idade_zero():
    assert dias_decorridos(AGORA, AGORA + 10 * DIA) == 0.0
    assert entrada_fria(_nota(dias=-10), P, AGORA) is None


def test_plano_compacta_a_fria_e_nao_recompacta_a_ja_compactada():
    notas = [_nota(dias=200, caminho="a.md"), _nota(dias=200, caminho="b.md", compactada_em_us=AGORA - DIA), _nota(dias=5, caminho="c.md")]
    plano = planejar(notas, P, AGORA)
    assert plano.avaliadas == 3
    assert [f.caminho for f in plano.compactar] == ["a.md"] and plano.esquecer == []


def test_sem_compactacao_a_fria_e_esquecida_mesmo_ja_compactada():
    notas = [_nota(dias=200, caminho="a.md"), _nota(dias=200, caminho="b.md", compactada_em_us=AGORA - DIA)]
    plano = planejar(notas, P, AGORA, compactar_frias=False)
    assert [f.caminho for f in plano.esquecer] == ["a.md", "b.md"] and plano.compactar == []


def test_ttl_vence_o_pin_a_camada_e_a_retencao():
    fixada_e_semantica = _nota(dias=1, camada="semantic", fixada=True, expira_em_us=AGORA - 1, caminho="ttl.md")
    ainda_valida = _nota(dias=1, expira_em_us=AGORA + DIA, caminho="ok.md")
    plano = planejar([fixada_e_semantica, ainda_valida], P, AGORA)
    assert [e.caminho for e in plano.expiradas] == ["ttl.md"]
    assert plano.vazio is False
    # o instante exato da expiracao ja conta como vencido
    assert planejar([_nota(expira_em_us=AGORA)], P, AGORA).expiradas


def test_nota_expirada_nao_entra_tambem_na_lista_de_frias():
    plano = planejar([_nota(dias=400, expira_em_us=AGORA - DIA)], P, AGORA)
    assert len(plano.expiradas) == 1 and plano.compactar == [] and plano.esquecer == []


def test_plano_vazio_quando_nada_esfriou():
    assert planejar([_nota(dias=3)], P, AGORA).vazio


def test_peso_de_amplitude_invalido_e_recusado():
    for ruim in (-0.1, math.nan, math.inf):
        with pytest.raises(ValueError):
            planejar([], P, AGORA, peso_amplitude=ruim)


def test_planejar_nao_altera_as_notas():
    n = _nota(dias=200, frontmatter={"a": 1})
    planejar([n], P, AGORA)
    assert n.frontmatter == {"a": 1}


# ── contadores de uso ──────────────────────────────────────────────────────


@pytest.fixture
def ac(tmp_path):
    x = Acessos(tmp_path / "acessos.db")
    yield x
    x.fechar()


def test_registrar_soma_e_guarda_o_acesso_mais_recente(ac):
    ac.registrar("a.md", agora_us=100)
    ac.registrar("a.md", agora_us=300, vezes=2)
    ac.registrar("a.md", agora_us=200)  # leitura atrasada nao rebaixa o ultimo acesso
    r = ac.obter("a.md")
    assert r["total"] == 4 and r["ultimo_us"] == 300


def test_registrar_zero_vezes_nao_faz_nada(ac):
    ac.registrar("a.md", vezes=0)
    assert ac.obter("a.md") is None


def test_voto_persiste_a_saliencia_e_encadeia(ac):
    assert ac.votar("a.md", "helpful", P) == 1.25
    assert ac.votar("a.md", "helpful", P) == 1.5
    assert ac.votar("a.md", "wrong", P) == 0.25
    assert ac.obter("a.md")["saliencia"] == 0.25
    with pytest.raises(ValueError):
        ac.votar("a.md", "talvez", P)


def test_voto_nao_apaga_o_contador_de_acessos(ac):
    ac.registrar("a.md", agora_us=5, vezes=3)
    ac.votar("a.md", "helpful", P)
    assert ac.obter("a.md")["total"] == 3


def test_renomear_leva_o_contador(ac):
    ac.registrar("a.md", agora_us=10, vezes=2)
    assert ac.renomear("a.md", "b.md") is True
    assert ac.obter("a.md") is None and ac.obter("b.md")["total"] == 2
    assert ac.renomear("nada.md", "c.md") is False


def test_renomear_para_caminho_que_ja_tem_contador_soma(ac):
    ac.registrar("a.md", agora_us=10, vezes=2)
    ac.registrar("b.md", agora_us=50, vezes=3)
    ac.votar("a.md", "not_helpful", P)
    ac.renomear("a.md", "b.md")
    r = ac.obter("b.md")
    assert r["total"] == 5 and r["ultimo_us"] == 50 and r["saliencia"] == 0.75
    assert ac.obter("a.md") is None


def test_esquecer(ac):
    ac.registrar("a.md", agora_us=7)
    assert ac.esquecer("a.md") is True and ac.esquecer("a.md") is False
    assert ac.obter("a.md") is None


def test_contadores_sobrevivem_a_reabertura(tmp_path):
    a = Acessos(tmp_path / "x.db")
    a.registrar("a.md", agora_us=1, vezes=4)
    a.fechar()
    b = Acessos(tmp_path / "x.db")
    assert b.todas()["a.md"]["total"] == 4
    b.fechar()


def test_pacote_so_importa_a_biblioteca_padrao_e_texto_bytes():
    fora = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom):
                if (no.level >= 2 and no.module != "texto_bytes") or (no.module or "").startswith("delegation_core"):
                    fora.append(f"{arq.name}: {'.' * no.level}{no.module}")
    assert fora == []
