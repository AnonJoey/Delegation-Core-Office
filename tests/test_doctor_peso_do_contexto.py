"""doctor: quanto o CLAUDE.md global carrega em toda sessao.

Relato do Mac de um colega em 2026-11-04: o guia importado pelo CLAUDE.md global
tinha uns 40 KB (cerca de 10 mil tokens) e entrava antes de a pessoa escrever
qualquer coisa. Nesta maquina o `AGENT_GUIDE.md` tem 47 KB. Nada media isso.
"""

from delegation_core import doctor


def _claude_md(tmp_path, corpo):
    p = tmp_path / "CLAUDE.md"
    p.write_text(corpo, encoding="utf-8")
    return p


def test_sem_claude_md_nao_ha_o_que_medir(tmp_path):
    r = doctor.check_context_weight(claude_md=tmp_path / "nao-existe.md")
    assert r["status"] == "ok"


def test_arquivo_pequeno_fica_ok(tmp_path):
    p = _claude_md(tmp_path, "# regras\nSeja breve.\n")
    assert doctor.check_context_weight(claude_md=p)["status"] == "ok"


def test_o_import_conta_junto_com_o_arquivo(tmp_path):
    guia = tmp_path / "guia.md"
    guia.write_text("x" * 40_000, encoding="utf-8")
    p = _claude_md(tmp_path, f"# delegation-core\n@{guia}\n")
    r = doctor.check_context_weight(claude_md=p, limite_bytes=16_000)
    assert r["status"] == "warn"
    assert "guia.md" in r["detail"]
    assert "40" in r["detail"]


def test_import_dentro_de_import_tambem_conta(tmp_path):
    fundo = tmp_path / "fundo.md"
    fundo.write_text("y" * 20_000, encoding="utf-8")
    meio = tmp_path / "meio.md"
    meio.write_text(f"@{fundo}\n", encoding="utf-8")
    p = _claude_md(tmp_path, f"@{meio}\n")
    assert doctor.check_context_weight(claude_md=p, limite_bytes=16_000)["status"] == "warn"


def test_import_que_cita_a_si_mesmo_nao_trava(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text(f"@{p}\ntexto\n", encoding="utf-8")
    assert doctor.check_context_weight(claude_md=p)["status"] == "ok"


def test_import_que_nao_existe_nao_derruba_o_check(tmp_path):
    p = _claude_md(tmp_path, "@/nao/existe/guia.md\n")
    assert doctor.check_context_weight(claude_md=p)["status"] == "ok"


def test_arroba_no_meio_da_linha_nao_e_import(tmp_path):
    """`user@example.com` e menções a @tipos nao sao arquivos."""
    grande = tmp_path / "grande.md"
    grande.write_text("z" * 50_000, encoding="utf-8")
    # sem espaco, para que so a regra do "@ no inicio da linha" o deixe de fora
    p = _claude_md(tmp_path, f"contato:user@{grande}\n@ {grande}\n")
    assert doctor.check_context_weight(claude_md=p, limite_bytes=16_000)["status"] == "ok"


def test_o_aviso_aponta_o_guia_curto_quando_o_peso_vem_do_guia_do_produto(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "CONFIG_DIR", tmp_path)
    guia = tmp_path / "AGENT_GUIDE.md"
    guia.write_text("g" * 40_000, encoding="utf-8")
    p = _claude_md(tmp_path, f"@{guia}\n")
    r = doctor.check_context_weight(claude_md=p, limite_bytes=16_000)
    assert "AGENT_GUIDE_CURTO.md" in r["fix"]
