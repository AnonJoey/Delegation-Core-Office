"""Digestao: pedacos por turno, map-reduce com modelo falso, conferencia de lastro, e a escolha das pendentes."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from delegation_core import digestao_vault
from delegation_core.digestao import citacoes_sem_lastro, pedacos, resumir
from delegation_core.digestao.resumo import MAPA, REDUZIR

TRANS = """---
title: Raw transcript — consertar o crash do palworld
date: 2026-06-18
type: session-transcript
---

# Session transcript

### You *(2026-06-18 10:00)*

o jogo crasha com UE4SS

### Claude *(2026-06-18 10:01)*

Vou ver o `UE4SS-settings.ini` e o `dwmapi.dll`.

### You *(2026-06-18 10:05)*

deu certo
"""


def test_pedacos_cortam_em_turno_e_tiram_frontmatter():
    ps = pedacos(TRANS, alvo=80)
    assert len(ps) >= 2 and all("type: session-transcript" not in p for p in ps)
    assert all(p.lstrip().startswith(("### You", "### Claude", "# Session")) for p in ps)
    assert "".join(ps).count("### ") == 3


def test_linha_maior_que_o_alvo_nao_e_cortada_e_nada_se_perde():
    """O contexto do modelo manda mais que a integridade do turno: turno acima de
    1,5x o alvo e recortado. Mas por LINHA: uma linha nunca e partida."""
    linha = "x" * 500
    t = "### You\n" + linha + "\n### Claude\nok\n"
    ps = pedacos(t, alvo=100)
    assert any(linha in p for p in ps) and "".join(ps) == t


def test_citacao_sem_lastro():
    assert citacoes_sem_lastro("usei `dwmapi.dll` e `inventado.exe`", TRANS) == ["inventado.exe"]


def _modelo(mapa="- DONE: trocado `dwmapi.dll`", reduzir="## Resumo\nConsertado com `dwmapi.dll`."):
    chamadas = []

    def p(system, prompt):
        chamadas.append(system)
        return reduzir if system == REDUZIR else mapa
    p.chamadas = chamadas
    return p


def test_resumir_faz_map_e_reduce():
    m = _modelo()
    r = resumir(TRANS, m, alvo=80)
    assert r["resumo"].startswith("## Resumo") and r["sem_lastro"] == [] and not r["vazio"]
    assert m.chamadas.count(MAPA) == r["partes"] and m.chamadas.count(REDUZIR) == 1


def test_nada_a_resumir_nao_chama_o_reduce():
    m = _modelo(mapa="NOTHING")
    r = resumir(TRANS, m, alvo=80)
    assert r["vazio"] and REDUZIR not in m.chamadas


# ── escolha das pendentes e escrita ────────────────────────────────────────

class VaultFalso:
    def __init__(self, cfg):
        self.cfg = cfg

    def index_note(self, t, m):
        return True

    def stamp_indexed(self, r):
        pass


@pytest.fixture
def vault(tmp_path, monkeypatch):
    from delegation_core import notewriter
    from delegation_core.config import Config
    monkeypatch.setattr(notewriter, "post_write_links", lambda *a, **k: None)
    s = tmp_path / "Sessions"
    s.mkdir()
    (s / "2026-06-18-transcript-aaaa.md").write_text(TRANS)
    (s / "2026-06-19-transcript-bbbb.md").write_text(TRANS)
    (s / "2026-06-19-Sessao curada do dia.md").write_text("---\ntitle: curada\n---\nx")
    (s / "transcript-semdata.md").write_text(TRANS)
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Sessions"])
    return VaultFalso(cfg)


def test_pendentes_pula_dia_com_sessao_curada(vault):
    nomes = [p.name for p in digestao_vault.pendentes(vault.cfg)]
    assert nomes == ["2026-06-18-transcript-aaaa.md", "transcript-semdata.md"]


def test_digerir_escreve_resumo_ligado_a_fonte_e_nao_repete(vault):
    r = digestao_vault.digerir(vault, maximo=1, perguntar=_modelo())
    assert r["pendentes_antes"] == 2 and len(r["feitos"]) == 1 and r["restam"] == 1
    nota = vault.cfg.vault / r["feitos"][0]["resumo"]
    texto = nota.read_text()
    assert "gerado_por: digestao" in texto and "digere: 2026-06-18-transcript-aaaa" in texto
    assert "[[2026-06-18-transcript-aaaa]]" in texto and "consertar o crash do palworld" in texto
    # a data do nome e a da SESSAO, nao a de hoje (facetas e boletim leem pelo nome)
    assert nota.name.startswith("2026-06-18-Resumo da sessao")
    assert "—" not in texto
    # o resumo nao conta como sessao curada do dia, e a transcricao ja feita sai da fila
    assert [p.name for p in digestao_vault.pendentes(vault.cfg)] == ["transcript-semdata.md"]


def test_citacao_sem_lastro_vai_para_o_rodape(vault):
    m = _modelo(reduzir="## Resumo\nUsou `inventado.exe`.")
    r = digestao_vault.digerir(vault, maximo=1, perguntar=m)
    texto = (vault.cfg.vault / r["feitos"][0]["resumo"]).read_text()
    assert "a conferir: `inventado.exe`" in texto


def test_falha_de_uma_nao_para_a_fila(vault):
    def quebra(system, prompt):
        raise ConnectionError("llama fora")
    r = digestao_vault.digerir(vault, maximo=5, perguntar=quebra)
    assert len(r["falhas"]) == 2 and "llama fora" in r["falhas"][0]["erro"] and r["feitos"] == []


def test_desligado(vault):
    vault.cfg.digestao_enabled = False
    assert digestao_vault.digerir(vault) == {"desligado": True}


def test_resumo_de_uma_nao_esconde_a_outra_do_mesmo_dia(vault):
    """Se o resumo contasse como sessao curada, o dia 18/06 ficaria 'curado' e a
    segunda transcricao desse dia nunca seria resumida."""
    (vault.cfg.vault / "Sessions" / "2026-06-18-transcript-cccc.md").write_text(TRANS)
    digestao_vault.digerir(vault, maximo=1, perguntar=_modelo())
    restantes = [p.name for p in digestao_vault.pendentes(vault.cfg)]
    # uma das duas de 18/06 foi resumida; a outra TEM que continuar na fila
    assert sum(1 for n in restantes if n.startswith("2026-06-18-transcript")) == 1


def test_reuniao_sem_marca_de_turno_e_recortada_por_linha():
    """Transcricao do Teams nao tem '### You'; sem o recorte, 181 KB iam num pedaco so."""
    t = "---\ntitle: reuniao\n---\n" + "".join(f"[{i // 60}:{i % 60:02d}] Fulano: fala numero {i}\n" for i in range(3000))
    ps = pedacos(t, alvo=10_000)
    assert len(ps) > 5 and all(len(p) <= 10_000 + 60 for p in ps)
    assert "".join(ps).count("Fulano:") == 3000


def test_assunto_pula_marcacao_do_claude_code():
    from delegation_core.digestao_vault import _assunto
    bruto = ('---\ntitle: "Raw transcript - <local-command-caveat>Caveat: The messages below"\n---\n\n'
             "### You *(2026-08-27 19:36)*\n\n<local-command-caveat>Caveat: nao responda</local-command-caveat>\n\n---\n\n"
             "### You *(2026-08-27 19:37)*\n\n<command-name>/model</command-name>\n\n---\n\n"
             "### Claude *(2026-08-27 19:37)*\n\nok\n\n### You *(2026-08-27 19:38)*\n\n"
             "palworld crashed after our <b>previous</b> modifications\nmais texto\n")
    assert _assunto(bruto, "2026-08-28-transcript-x") == "palworld crashed after our previous modifications"
    normal = '---\ntitle: "Raw transcript - Instalar o soteria-pmo"\n---\n### You\n\nqualquer'
    assert _assunto(normal, "stem") == "Instalar o soteria-pmo"
    assert _assunto("---\ntitle: \"<x>\"\n---\n### You\n\n<y>\n", "stem") == "stem"
