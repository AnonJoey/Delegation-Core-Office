"""A fila da digestao nao pode ficar presa atras de notas que nao tem o que resumir.

Medido em 2026-11-04 rodando a digestao de verdade (com o modelo local autorizado):
`pendentes_antes: 357, feitos: 0, falhas: 5, restam: 352`, noite apos noite. As cinco
primeiras da fila eram notas-indice de reuniao: 1,3 a 1,7 KB, so com links para
`<nome>-parte-1` e `-parte-2`, que e onde esta a fala. O modelo respondia NOTHING a
cada uma, a falha nao era lembrada, e as mesmas cinco voltavam a frente da fila toda
noite, consumindo a cota de `maximo` e deixando as outras 352 sem andar.
"""

import json

import pytest

from delegation_core import digestao_vault
from delegation_core.config import Config
from delegation_core.digestao.resumo import REDUZIR

FALA = ("### You\n\nconsertar o crash do palworld no linux, a dll estava no lugar errado\n\n"
        "### Claude\n\nentao movi a dll e o jogo abriu.\n")
INDICE = ("---\ntitle: indice\n---\n\n## Resumo Executivo\nTranscricao dividida em duas partes.\n\n"
          "## Links Semanticos\n- [[{nome}-parte-1]]\n- [[{nome}-parte-2]]\n")


class _Vault:
    def __init__(self, cfg):
        self.cfg = cfg

    def index_note(self, t, m):
        return True

    def stamp_indexed(self, r):
        pass


@pytest.fixture
def vault(tmp_path, monkeypatch):
    from delegation_core import notewriter
    monkeypatch.setattr(notewriter, "post_write_links", lambda *a, **k: None)
    s = tmp_path / "Sessions"
    s.mkdir()
    for nome in ("2026-08-28-Daily-transcricao", "2026-08-28-Cronograma-transcricao"):
        (s / f"{nome}.md").write_text(INDICE.format(nome=nome))
        (s / f"{nome}-parte-1.md").write_text(FALA)
        (s / f"{nome}-parte-2.md").write_text(FALA)
    cfg = Config(vault_path=str(tmp_path), vault_folders=["Sessions"], engine_mode="local")
    return _Vault(cfg)


def modelo(chamadas=None, vazias_se=None):
    def perguntar(system, prompt):
        if chamadas is not None:
            chamadas.append(prompt[:40])
        if vazias_se and vazias_se in prompt:
            return "NOTHING"
        if system == REDUZIR:
            return "## Resumo\nCorrigiram o crash do palworld movendo a dll."
        return "- consertar o crash do palworld"
    return perguntar


def test_nota_indice_nao_e_transcricao_pendente(vault):
    nomes = sorted(p.name for p in digestao_vault.pendentes(vault.cfg))
    assert nomes == ["2026-08-28-Cronograma-transcricao-parte-1.md",
                     "2026-08-28-Cronograma-transcricao-parte-2.md",
                     "2026-08-28-Daily-transcricao-parte-1.md",
                     "2026-08-28-Daily-transcricao-parte-2.md"]


def test_vazia_nao_consome_a_cota_e_a_fila_anda(vault):
    """Antes: maximo=2 e duas notas vazias na frente davam feitos=0, para sempre."""
    s = vault.cfg.vault / "Sessions"
    for i in range(3):
        (s / f"2026-09-0{i + 1}-transcript-vazia{i}.md").write_text(FALA + f"\nVAZIA-{i}\n")
    r = digestao_vault.digerir(vault, maximo=2, perguntar=modelo(vazias_se="VAZIA-"))
    assert len(r["feitos"]) == 2, r
    assert len(r["vazias"]) == 3
    assert r["falhas"] == []


def test_vazia_e_lembrada_e_nao_volta_a_fila(vault):
    s = vault.cfg.vault / "Sessions"
    (s / "2026-09-01-transcript-vazia.md").write_text(FALA + "\nVAZIA-X\n")
    antes = [p.name for p in digestao_vault.pendentes(vault.cfg)]
    assert "2026-09-01-transcript-vazia.md" in antes
    digestao_vault.digerir(vault, maximo=1, perguntar=modelo(vazias_se="VAZIA-X"))
    depois = [p.name for p in digestao_vault.pendentes(vault.cfg)]
    assert "2026-09-01-transcript-vazia.md" not in depois
    estado = json.loads((vault.cfg.vault / ".digestao" / "vazias.json").read_text())
    assert "2026-09-01-transcript-vazia.md" in estado


def test_vazia_que_mudou_volta_a_ser_tentada(vault):
    s = vault.cfg.vault / "Sessions"
    p = s / "2026-09-01-transcript-vazia.md"
    p.write_text(FALA + "\nVAZIA-X\n")
    digestao_vault.digerir(vault, maximo=1, perguntar=modelo(vazias_se="VAZIA-X"))
    p.write_text(FALA + "\nagora tem conteudo novo e mais comprido\n")
    assert p.name in [q.name for q in digestao_vault.pendentes(vault.cfg)]


def test_vazia_conhecida_nao_chama_o_modelo_de_novo(vault):
    s = vault.cfg.vault / "Sessions"
    (s / "2026-09-01-transcript-vazia.md").write_text(FALA + "\nVAZIA-X\n")
    digestao_vault.digerir(vault, maximo=9, perguntar=modelo(vazias_se="VAZIA-X"))
    chamadas = []
    digestao_vault.digerir(vault, maximo=9, perguntar=modelo(chamadas, vazias_se="VAZIA-X"))
    assert not any("VAZIA-X" in c for c in chamadas)


def test_erro_real_continua_contando_na_cota(vault):
    def quebra(system, prompt):
        raise ConnectionError("llama fora")
    r = digestao_vault.digerir(vault, maximo=2, perguntar=quebra)
    assert len(r["falhas"]) == 2 and r["feitos"] == []


def test_fila_toda_de_vazias_nao_prende_a_execucao(vault):
    """O teto de tentativas (5 x maximo) impede que centenas de notas vazias virem uma noite inteira de chamadas."""
    s = vault.cfg.vault / "Sessions"
    for i in range(30):
        (s / f"2026-09-{i + 1:02d}-transcript-v{i:02d}.md").write_text(FALA + f"\nVAZIA-{i}\n")
    chamadas = []
    r = digestao_vault.digerir(vault, maximo=1, perguntar=modelo(chamadas, vazias_se="VAZIA-"))
    assert len(r["vazias"]) + len(r["feitos"]) <= 5


# ── travessao: o titulo vem da transcricao e ia direto para o nome e o frontmatter ──

#: gerados com chr(): um escape digitado vira o caractere de verdade no arquivo
EM = chr(0x2014)
EN = chr(0x2013)


def test_titulo_com_travessao_nao_chega_ao_nome_nem_ao_frontmatter(vault):
    """Em 2026-11-04 a digestao criou 15 notas; 14 tinham travessao no titulo e nos aliases e 3 no nome do
    arquivo, porque o titulo da transcricao (data e parte separadas por travessao) passava intacto. So o
    corpo era limpo."""
    s = vault.cfg.vault / "Sessions"
    titulo = f"Daily - Equipe Dev {EM} 2026-09-05 (transcricao) {EN} Parte 3/3"
    (s / "2026-09-05-transcript-com-travessao.md").write_text(
        f'---\ntitle: "{titulo}"\n---\n\n' + FALA, encoding="utf-8")
    r = digestao_vault.digerir(vault, maximo=9, perguntar=modelo())
    novo = next(f for f in r["feitos"] if f["transcricao"] == "2026-09-05-transcript-com-travessao.md")
    caminho = vault.cfg.vault / novo["resumo"]
    assert EM not in caminho.name and EN not in caminho.name
    texto = caminho.read_text(encoding="utf-8")
    assert EM not in texto and EN not in texto
    assert "Daily - Equipe Dev - 2026-09-05" in texto


# ── o resumo nao pode ser tomado por transcricao ────────────────────────────

def test_resumo_com_transcript_no_nome_nao_e_tratado_como_transcricao_bruta(vault):
    """Em 2026-11-04 a mesma transcricao foi resumida tres vezes e dois resumos foram resumidos de novo
    (resumo de resumo): o nome do resumo ('Resumo da sessao - Session Transcript ...') casa com o filtro de
    transcricao bruta, entao ele nao era reconhecido como resumo, a original seguia pendente e o proprio
    resumo entrava na fila."""
    s = vault.cfg.vault / "Sessions"
    (s / "2026-08-20-transcript-4024e1d7.md").write_text(FALA)
    (s / "2026-08-20-Resumo da sessao - Session Transcript - 4024e1d7.md").write_text(
        "---\ngerado_por: digestao\ntype: session\ndigere: 2026-08-20-transcript-4024e1d7\n---\n\n## Resumo\nx\n")
    nomes = [p.name for p in digestao_vault.pendentes(vault.cfg)]
    assert "2026-08-20-transcript-4024e1d7.md" not in nomes, "a original ja tem resumo"
    assert not any(n.startswith("2026-08-20-Resumo") for n in nomes), "o resumo entrou na fila"


def test_rodar_duas_vezes_nao_resume_a_mesma_transcricao_duas_vezes(vault):
    s = vault.cfg.vault / "Sessions"
    (s / "2026-08-20-transcript-4024e1d7.md").write_text(
        '---\ntitle: "Session Transcript 4024e1d7"\n---\n\n' + FALA)
    primeira = digestao_vault.digerir(vault, maximo=20, perguntar=modelo())
    segunda = digestao_vault.digerir(vault, maximo=20, perguntar=modelo())
    feitos = [f["transcricao"] for f in primeira["feitos"] + segunda["feitos"]]
    assert len(feitos) == len(set(feitos)), f"resumiu a mesma duas vezes: {feitos}"


def test_a_chave_digere_e_o_wikilink_nao_sofrem_a_troca_do_travessao(vault):
    """`corpo.replace(em, ',')` rodava no texto inteiro: um stem com travessao virava outro nome e a chave
    `digere:` deixava de casar com a transcricao, que voltava a ser resumida."""
    s = vault.cfg.vault / "Sessions"
    stem = f"2026-09-09-transcript-a{chr(0x2014)}b"
    (s / f"{stem}.md").write_text(FALA, encoding="utf-8")
    r = digestao_vault.digerir(vault, maximo=9, perguntar=modelo())
    novo = next(f for f in r["feitos"] if f["transcricao"] == f"{stem}.md")
    texto = (vault.cfg.vault / novo["resumo"]).read_text(encoding="utf-8")
    assert f"digere: {stem}" in texto and f"[[{stem}]]" in texto
