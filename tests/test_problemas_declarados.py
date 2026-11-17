"""O `organizer` marcava defeito de conteudo e nada lia.

## O caso real, medido em 26/09/2026

Duas notas do vault tem como CORPO o template de prompt da sintese, sob titulos
que prometem conteudo: "Relatorio do job noturno - defeitos silenciosos" e
"Validacao tecnica dos Agentes PMO". O corpo comeca em
`OUTPUT: Markdown only. No preamble...`.

A causa foi corrigida em 04/09 e esta fechada: zero ocorrencias do aviso
`has no fallback_payload` em qualquer log ou no journal do daemon. **O estrago
nunca foi reparado.**

E as duas eram invisiveis ao passe de saude, porque declaram:

    quality_score: 0.7        <- acima do corte de 0,5
    quality_issues: ["prompt_leak"]
    needs_review: false

Ou seja, pelo criterio existente elas sao **saudaveis**. O `organizer.py:144`
gravou o `prompt_leak` e ninguem nunca leu.

## Balde proprio, e nao somado a `needs_repair`

Misturar esconderia de que tipo e cada problema, e este projeto ja tomou essa
decisao antes: `malformed_frontmatter` tambem tem balde proprio, com o
comentario de que a contagem deve dizer de que tipo e cada coisa em vez de
esconder a diferenca. Alem disso, somar mudaria uma metrica que outras coisas
ja leem.
"""

from __future__ import annotations

import pytest

from delegation_core.config import Config
from delegation_core.notes import problemas_declarados
from delegation_core.vault import VaultManager


def test_lista_json_no_frontmatter():
    """O formato real: o `_parse_frontmatter` deste projeto divide a linha no
    primeiro dois-pontos e nao interpreta tipo, entao o valor chega como a
    string `["prompt_leak"]`."""
    assert problemas_declarados({"quality_issues": '["prompt_leak"]'}) == ["prompt_leak"]


def test_varios_problemas():
    assert problemas_declarados({"quality_issues": '["prompt_leak", "truncado"]'}) == [
        "prompt_leak", "truncado"]


def test_lista_sem_aspas_ainda_nomeia_o_problema():
    """`[a, b]` nao e JSON valido, e mesmo assim da para dizer qual e o
    problema. Devolver vazio aqui esconderia uma nota defeituosa."""
    assert problemas_declarados({"quality_issues": "[prompt_leak, outro]"}) == [
        "prompt_leak", "outro"]


@pytest.mark.parametrize("fm", [{}, {"quality_issues": ""}, {"quality_issues": "[]"},
                                {"quality_issues": None}, None])
def test_ausente_ou_vazio_nao_inventa_problema(fm):
    assert problemas_declarados(fm) == []


def test_valor_impossivel_nao_levanta():
    """Frontmatter torto nao pode derrubar o passe de saude do vault inteiro."""
    assert isinstance(problemas_declarados({"quality_issues": "{{{"}), list)


def _vault_com(tmp_path, frontmatter: str) -> VaultManager:
    vault = tmp_path / "vault"
    (vault / "Reference").mkdir(parents=True)
    (vault / "Reference" / "2026-09-03-nota.md").write_text(
        frontmatter + "\nOUTPUT: Markdown only. No preamble\n", encoding="utf-8")
    cfg = Config(vault_path=str(vault), vault_folders=["Reference"])
    vm = VaultManager(cfg)
    vm._ensure_ready = lambda: None
    return vm


def test_a_nota_danificada_e_contada_no_balde_novo(tmp_path):
    """A forma EXATA das duas notas reais, que passavam por saudaveis.

    Conferido por mutacao: tirar a leitura do passe de saude derruba este teste.
    """
    vm = _vault_com(tmp_path, '---\nquality_score: 0.7\n'
                              'quality_issues: ["prompt_leak"]\n'
                              'needs_review: false\n---\n')
    s = vm.get_health_summary(force=True)
    assert s["com_problema_declarado"] == 1


def test_e_NAO_e_contada_como_needs_repair(tmp_path):
    """A regressao que importa: `needs_repair` tem outro significado e outros
    leitores, e somar aqui mudaria uma metrica que ja existe.

    Conferido por mutacao: somar em `needs_repair` em vez do balde proprio
    derruba este teste.
    """
    vm = _vault_com(tmp_path, '---\nquality_score: 0.7\n'
                              'quality_issues: ["prompt_leak"]\n'
                              'needs_review: false\n---\n')
    assert vm.get_health_summary(force=True)["needs_repair"] == 0


def test_nota_sa_nao_entra_no_balde(tmp_path):
    vm = _vault_com(tmp_path, '---\nquality_score: 0.9\nneeds_review: false\n---\n')
    assert vm.get_health_summary(force=True)["com_problema_declarado"] == 0


def test_o_detalhe_nomeia_a_nota_e_o_problema(tmp_path):
    """Contagem sozinha nao permite agir: quem le precisa saber QUAL nota."""
    vm = _vault_com(tmp_path, '---\nquality_score: 0.7\n'
                              'quality_issues: ["prompt_leak"]\n---\n')
    itens = vm.health_detail().get("com_problema_declarado_items") or []
    assert len(itens) == 1
    assert "prompt_leak" in itens[0]["issues"]
    assert itens[0]["folder"] == "Reference"
