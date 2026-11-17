"""Autoridade ligada a busca: fator por pasta e etiqueta, reordenacao, e o que nunca muda."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from delegation_core import ranqueamento_vault as rv


def _escrever(raiz, rel, texto):
    p = raiz / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")


@pytest.fixture
def cfg(tmp_path):
    raiz = tmp_path / "vault"
    _escrever(raiz, "Decisions/d.md", "---\ntitle: D\n---\n\ncorpo\n")
    _escrever(raiz, "Sessions/s.md", "---\ntitle: S\n---\n\ncorpo\n")
    _escrever(raiz, "Reference/canon.md", "---\ntags:\n  - canonical\n---\n\ncorpo\n")
    _escrever(raiz, "Reference/velha.md", "---\ntags: [historical]\n---\n\ncorpo\n")
    _escrever(raiz, "Fixes/fixada.md", "---\npinned: true\n---\n\ncorpo\n")
    _escrever(raiz, "Misc/x.md", "corpo\n")
    return SimpleNamespace(vault=raiz, autoridade_enabled=True)


def _hit(path, sim, kind="note"):
    return {"path": path, "similarity": sim, "kind": kind, "title": path}


def test_desligado_so_corta_na_ordem_recebida(cfg):
    cfg.autoridade_enabled = False
    hits = [_hit("Sessions/s.md", 0.90), _hit("Decisions/d.md", 0.89)]
    assert rv.reordenar(cfg, "q", hits, 1) == hits[:1]
    assert "authority" not in hits[0] and rv.candidatos(cfg, 10) == 10


def test_ligado_busca_mais_candidatos(cfg):
    assert rv.candidatos(cfg, 10) == 40


def test_decisao_passa_uma_sessao_quase_igual(cfg):
    hits = [_hit("Sessions/s.md", 0.90), _hit("Decisions/d.md", 0.88)]
    r = rv.reordenar(cfg, "qual a porta do llama", hits, 5)
    assert [h["path"] for h in r] == ["Decisions/d.md", "Sessions/s.md"]
    assert r[0]["authority"] == 1.25 and r[1]["authority"] == 0.77


def test_a_autoridade_age_sobre_o_posto_e_nao_sobre_a_magnitude_da_similaridade(cfg):
    # a ordem de chegada e o que conta: a decisao na posicao 2 passa a sessao na 1, qualquer que seja a similaridade
    a = rv.reordenar(cfg, "q", [_hit("Sessions/s.md", 0.95), _hit("Decisions/d.md", 0.60)], 5)
    b = rv.reordenar(cfg, "q", [_hit("Sessions/s.md", 0.61), _hit("Decisions/d.md", 0.60)], 5)
    assert [h["path"] for h in a] == [h["path"] for h in b] == ["Decisions/d.md", "Sessions/s.md"]


def test_o_alcance_da_autoridade_e_o_do_posto(cfg):
    # decisao 1,25 contra sessao 0,77 (razao 1,62): alcanca uma sessao em primeiro ate perto da posicao 38, nao alem
    def ordem(posicao_da_decisao):
        hits = [_hit("Sessions/s.md", 0.9)] + [_hit(f"Misc/{i}.md", 0.8) for i in range(posicao_da_decisao - 2)] + [_hit("Decisions/d.md", 0.7)]
        return [h["path"] for h in rv.reordenar(cfg, "q", hits, 100)]

    perto, longe = ordem(30), ordem(50)
    assert perto.index("Decisions/d.md") < perto.index("Sessions/s.md")
    assert longe.index("Decisions/d.md") > longe.index("Sessions/s.md")


def test_forca_escala_o_desvio_do_fator(cfg):
    cfg.autoridade_forca = 0.5
    assert rv.fator_da_nota(cfg, "Decisions/d.md") == pytest.approx(1.125)
    assert rv.fator_da_nota(cfg, "Sessions/s.md") == pytest.approx(0.885)
    cfg.autoridade_forca = 0.0
    assert rv.fator_da_nota(cfg, "Decisions/d.md") == 1.0
    hits = [_hit("Sessions/s.md", 0.9), _hit("Decisions/d.md", 0.8)]
    assert [h["path"] for h in rv.reordenar(cfg, "q", hits, 5)] == ["Sessions/s.md", "Decisions/d.md"]


def test_a_similaridade_do_acerto_nao_muda(cfg):
    hits = [_hit("Sessions/s.md", 0.90), _hit("Decisions/d.md", 0.88)]
    r = rv.reordenar(cfg, "q", hits, 5)
    assert {h["path"]: h["similarity"] for h in r} == {"Sessions/s.md": 0.90, "Decisions/d.md": 0.88}


def test_pergunta_sobre_sessao_devolve_a_penalidade_e_um_bonus(cfg):
    hits = [_hit("Sessions/s.md", 0.88), _hit("Decisions/d.md", 0.89)]
    r = rv.reordenar(cfg, "o que fizemos na última sessão", hits, 5)
    assert r[0]["path"] == "Sessions/s.md" and r[0]["authority"] == 1.25 and r[1]["authority"] == 1.25


def test_etiquetas_e_fixacao_vem_do_frontmatter(cfg):
    assert rv.fator_da_nota(cfg, "Reference/canon.md") == pytest.approx(1.37)
    assert rv.fator_da_nota(cfg, "Reference/velha.md") == 0.80
    assert rv.fator_da_nota(cfg, "Fixes/fixada.md") == pytest.approx(1 + 0.12 + 0.10 + 0.08)


def test_o_que_nao_e_nota_do_vault_fica_neutro(cfg):
    assert rv.fator_da_nota(cfg, "Misc/x.md") == 1.0
    assert rv.fator_da_nota(cfg, "") == 1.0
    hits = [_hit("Decisions/graphs/g/a.md", 0.9, kind="generated"), _hit("Decisions/d.md", 0.9)]
    r = rv.reordenar(cfg, "q", hits, 5)
    assert next(h for h in r if h["kind"] == "generated")["authority"] == 1.0


def test_nota_que_sumiu_do_disco_nao_derruba_a_busca(cfg):
    hits = [_hit("Decisions/sumiu.md", 0.9), _hit("Decisions/d.md", 0.89)]
    r = rv.reordenar(cfg, "q", hits, 5)
    assert len(r) == 2 and all("authority" in h for h in r)


def test_erro_inesperado_devolve_a_ordem_original(cfg, monkeypatch):
    monkeypatch.setattr(rv, "fator_da_nota", lambda *a, **k: 1 / 0)
    hits = [_hit("Sessions/s.md", 0.90), _hit("Decisions/d.md", 0.88)]
    assert rv.reordenar(cfg, "q", hits, 1) == hits[:1]


def test_lista_vazia_e_limite(cfg):
    assert rv.reordenar(cfg, "q", [], 5) == []
    hits = [_hit("Decisions/d.md", 0.9)] * 3
    assert len(rv.reordenar(cfg, "q", hits, 2)) == 2
