"""Reparo do frontmatter que nenhum leitor de YAML consegue abrir.

Medido em 04/11/2026: 352 notas do vault com frontmatter ilegivel. Causas
reais, com um exemplo de cada tirado do vault:

- 282 + 8 em Reference/graphs: `tags: [... @nous-research-ui ...]` e
  `buckets/[id]` dentro da lista de fluxo, sem aspas. Quem escreveu foi um
  script de refino do servidor que pega o bloco que o modelo devolve e grava
  sem validar.
- 19: valor simples com `: ` no meio (`subtitle: Oito mudancas: preview ...`).
- 41: linha solta `- "Decisao: ...` dentro do bloco, depois de chave com valor.
- 2: nota cujo "frontmatter" e o corpo do texto (chaves no fim do arquivo).
  Nao ha reparo seguro; tem que ser devolvido como esta.
"""
from __future__ import annotations

import yaml

from delegation_core.notes import _frontmatter_parses
from delegation_core.reparo_frontmatter import reparar_frontmatter

CORPO = "\n## Resumo\nTexto do corpo com `: ` e @arroba.\n"


def _nota(bloco: str) -> str:
    return f"---\n{bloco}\n---\n{CORPO}"


def _bloco(texto: str) -> dict:
    return yaml.safe_load(texto.split("---\n", 2)[1])


def test_tag_com_arroba_na_lista_de_fluxo():
    nota = _nota('title: "hermes-agent: x"\ntags: [hermes-agent, @nous-research-ui, package-json]\nstatus: active')
    assert not _frontmatter_parses(nota)

    r = reparar_frontmatter(nota)

    assert r.mudou and _frontmatter_parses(r.texto)
    assert _bloco(r.texto)["tags"] == ["hermes-agent", "@nous-research-ui", "package-json"]


def test_tag_com_colchete_dentro_do_item():
    nota = _nota("title: t\ntags: [supabase, buckets/[id], api-keys/temporary]\nstatus: active")
    r = reparar_frontmatter(nota)
    assert _frontmatter_parses(r.texto)
    assert _bloco(r.texto)["tags"] == ["supabase", "buckets/[id]", "api-keys/temporary"]


def test_valor_simples_com_dois_pontos():
    nota = _nota("title: t\nsubtitle: Oito mudancas: preview, escopo e doctor\nstatus: active")
    assert not _frontmatter_parses(nota)
    r = reparar_frontmatter(nota)
    assert _frontmatter_parses(r.texto)
    assert _bloco(r.texto)["subtitle"] == "Oito mudancas: preview, escopo e doctor"


def test_linhas_soltas_voltam_como_aliases_com_o_texto_inteiro():
    """O par `data-titulo` / `titulo` do compose_note, sem cabecalho nem fecho de aspas."""
    nota = _nota('title: "Decisao: x"\nai_generated: true\n- "2026-10-14-Decisao: x (2026)\n'
                 '- "Decisao: x (2026)\ntype: decision')
    assert not _frontmatter_parses(nota)
    r = reparar_frontmatter(nota)
    assert _frontmatter_parses(r.texto)
    d = _bloco(r.texto)
    assert d["type"] == "decision" and d["ai_generated"] is True
    assert d["aliases"] == ["2026-10-14-Decisao: x (2026)", "Decisao: x (2026)"]
    assert any("recuperada" in linha for linha in r.avisos)


def test_linha_solta_com_aliases_ja_existente_e_descartada_sem_duplicar_a_chave():
    nota = _nota('title: t\naliases:\n  - um\nai_generated: true\n- "perdida\ntype: x')
    r = reparar_frontmatter(nota)
    assert _frontmatter_parses(r.texto)
    assert r.texto.count("aliases:") == 1
    assert _bloco(r.texto)["aliases"] == ["um"]
    assert any("a nota ja tem aliases" in linha for linha in r.avisos)


def test_corpo_fica_identico_byte_a_byte():
    nota = _nota("title: t\ntags: [a, @b]\nstatus: active")
    r = reparar_frontmatter(nota)
    assert r.texto.endswith(CORPO)
    assert r.texto.split("\n---\n", 1)[1] == nota.split("\n---\n", 1)[1]


def test_nota_saudavel_nao_muda():
    nota = _nota('title: "ok"\ntags: [a, b]\nstatus: active')
    r = reparar_frontmatter(nota)
    assert not r.mudou and r.texto == nota


def test_nota_sem_frontmatter_nao_muda():
    r = reparar_frontmatter("# so corpo\n")
    assert not r.mudou and r.texto == "# so corpo\n"


def test_lista_em_bloco_e_valores_ja_citados_sobrevivem():
    nota = _nota('title: "a: b"\naliases:\n  - um\n  - "dois: tres"\ntags: ["x y", @z]\nstatus: active')
    r = reparar_frontmatter(nota)
    d = _bloco(r.texto)
    assert d["aliases"] == ["um", "dois: tres"]
    assert d["tags"] == ["x y", "@z"]


def test_o_que_nao_tem_reparo_seguro_volta_igual_e_diz_por_que():
    # Frontmatter que e na verdade o corpo da nota (chaves no fim do arquivo).
    nota = ("---\n\n**Voce** *(2026-10-24)*\n\nfaca tudo.\nquality_score: 0.7\n"
            "aliases:\n  - a*b\n  - *c\n---\n")
    r = reparar_frontmatter(nota)
    assert not r.mudou and r.texto == nota
    assert r.avisos and "sem reparo seguro" in r.avisos[-1]


def test_nunca_devolve_resultado_que_ainda_nao_abre():
    """Propriedade: mudou=True implica que o resultado abre num leitor de YAML."""
    casos = [
        _nota("title: t\ntags: [a, @b, c/[d]]\nx: y: z"),
        _nota("title: t\n- sozinha\nk: v"),
        _nota("title: [aberto\nk: v"),
    ]
    for nota in casos:
        r = reparar_frontmatter(nota)
        if r.mudou:
            assert _frontmatter_parses(r.texto), nota
        else:
            assert r.texto == nota


def test_mais_de_seis_linhas_soltas_nao_e_estrago_pontual():
    nota = _nota("title: t\nai: true\n" + "\n".join(f"- l{i}" for i in range(7)) + "\ntype: x")
    r = reparar_frontmatter(nota)
    assert not r.mudou and r.texto == nota
    assert "mais de 6 linhas soltas" in r.avisos[-1]


def test_texto_corrido_no_bloco_para_com_o_motivo():
    nota = "---\ntitle: t\nisto nao e chave nem lista\nstatus: x\n---\n" + CORPO
    r = reparar_frontmatter(nota)
    assert not r.mudou and r.texto == nota
    assert "linha que nao e chave nem lista" in r.avisos[-1]


def test_reparo_parcial_nao_vale_se_o_bloco_continua_ilegivel():
    # A primeira linha tem reparo; a recuada logo abaixo nao tem.
    nota = _nota("title: t\nsubtitle: a: b\nk: v\n   w: x")
    r = reparar_frontmatter(nota)
    assert not r.mudou and r.texto == nota
    assert "continua ilegivel" in r.avisos[-1]


def test_lista_em_bloco_no_nivel_zero_nao_e_linha_solta():
    nota = _nota("title: t\naliases:\n- um\n- dois\ntags: [a, @b]\nstatus: active")
    r = reparar_frontmatter(nota)
    d = _bloco(r.texto)
    assert d["aliases"] == ["um", "dois"]
    assert d["tags"] == ["a", "@b"]
    assert not any("removida" in a for a in r.avisos)


def test_aliases_recuperados_ficam_onde_estavam_as_linhas_soltas():
    nota = _nota('title: t\nai_generated: true\n- "a: b\ntype: decision')
    r = reparar_frontmatter(nota).texto
    assert r.index("ai_generated") < r.index("aliases:") < r.index("type:")


def test_sanitize_note_devolve_frontmatter_legivel_mesmo_com_tag_de_modelo_ruim():
    """A rede de seguranca do synthesizer: o modelo escreve `tags: [@x, a/[b]]`."""
    from delegation_core.synthesizer import sanitize_note

    bruto = '---\ntitle: "Nota"\ntags: [@nous-research-ui, buckets/[id], ok]\nstatus: active\n---\n\n## Resumo\ntexto\n'
    limpo = sanitize_note(bruto)

    assert _frontmatter_parses(limpo)
    assert _bloco(limpo)["tags"] == ["@nous-research-ui", "buckets/[id]", "ok"]
