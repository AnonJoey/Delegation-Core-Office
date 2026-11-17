"""Envelhecimento ligado ao vault: plano, aplicacao reversivel, expiracao, voto e leitura.

Vault falso em tmp_path e sqlite em tmp_path: nada toca o vault nem a config reais.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from delegation_core import envelhecimento_vault as ev
from delegation_core import historico_vault

DIA = 86_400_000_000
AGORA = int(datetime(2026, 10, 17, 12, 0).timestamp() * 1_000_000)

PROSA = "Conversamos longamente sobre o plano e ninguem anotou nada de duravel nesta parte. " * 30
VELHA = (
    "---\ntitle: Sessao velha\ndate: 2026-01-01\n---\n\n"
    "## Resumo\nDeploy falhou em src/app/main.py com E0433.\n\n" + PROSA + "\n\nVeja https://exemplo.org/issues/7.\n"
)


class VaultFalso:
    def __init__(self, raiz, **extra):
        self.cfg = SimpleNamespace(
            vault=raiz, vault_folders=["Sessions", "Decisions", "Reference"], historico_enabled=True, redigir_segredos=True,
            envelhecimento_enabled=True, envelhecimento_pastas=None, envelhecimento_meia_vida_dias=35.0,
            envelhecimento_limiar_frio=0.20, envelhecimento_compactar=True, envelhecimento_path=str(raiz.parent / "acessos.db"),
            **extra)
        self.indexadas, self.apagadas = [], []

    def index_note(self, texto, meta):
        self.indexadas.append(meta["path"])
        return True

    def stamp_indexed(self, rels):
        pass

    def delete_notes(self, rels):
        self.apagadas.extend(rels)
        return len(rels)

    def find_notes_by_stem(self, nome):
        return [f for pasta in self.cfg.vault_folders for f in sorted((self.cfg.vault / pasta).rglob("*.md")) if nome.lower() in f.stem.lower()]


def _escrever(raiz, rel, texto):
    p = raiz / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto, encoding="utf-8")


@pytest.fixture
def vault(tmp_path):
    raiz = tmp_path / "vault"
    _escrever(raiz, "Sessions/2026-01-01-velha.md", VELHA)
    _escrever(raiz, "Sessions/2026-10-10-nova.md", "---\ntitle: Nova\n---\n\n" + PROSA)
    _escrever(raiz, "Sessions/2026-01-02-fixada.md", "---\ntitle: Fixada\npinned: true\n---\n\n" + PROSA)
    _escrever(raiz, "Decisions/2026-01-01-decisao.md", "---\ntitle: Decisao\n---\n\n" + PROSA)
    _escrever(raiz, "Reference/2026-01-01-valida.md", "---\ntitle: Valida\nexpires_at: 2026-02-01\n---\n\ncorpo\n")
    _escrever(raiz, "Reference/2026-01-01-sem-validade.md", "---\ntitle: Sem\n---\n\n" + PROSA)
    historico_vault._INSTANCIAS.clear()
    ev._ACESSOS.clear()
    v = VaultFalso(raiz)
    yield v
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()
    for a in ev._ACESSOS.values():
        a.fechar()
    ev._ACESSOS.clear()


def _caminhos(lista):
    return sorted(x["path"] for x in lista)


def test_desligado_nao_faz_nada(vault):
    vault.cfg.envelhecimento_enabled = False
    assert "error" in ev.varrer(vault)
    assert ev.acessos(vault.cfg) is None
    ev.registrar_leituras(vault.cfg, ["Sessions/2026-01-01-velha.md"])  # nao levanta
    assert "error" in ev.votar(vault, "velha", "stale")


def test_plano_so_lista_o_que_esfriou_e_o_que_expirou(vault):
    r = ev.varrer(vault, agora_us=AGORA)
    assert r["dry_run"] is True
    assert _caminhos(r["to_compact"]) == ["Sessions/2026-01-01-velha.md"]
    assert [x["path"] for x in r["expired"]] == ["Reference/2026-01-01-valida.md"]
    assert r["to_forget"] == []
    # fixada, recente, semantica e sem validade ficam de fora
    assert r["evaluated"] == 4  # 3 episodicas + 1 com validade


def test_dry_run_nao_toca_em_nenhum_arquivo(vault):
    antes = {p: p.read_bytes() for p in vault.cfg.vault.rglob("*.md")}
    ev.varrer(vault, agora_us=AGORA)
    assert {p: p.read_bytes() for p in vault.cfg.vault.rglob("*.md")} == antes
    assert not (vault.cfg.vault / ".lixeira").exists() and vault.apagadas == []


def test_aplicar_compacta_e_o_texto_inteiro_volta_do_historico(vault):
    rel = "Sessions/2026-01-01-velha.md"
    r = ev.varrer(vault, aplicar=True, agora_us=AGORA)
    feito = next(x for x in r["applied"] if x["path"] == rel)
    assert feito["status"] == "compacted" and feito["bytes_after"] < feito["bytes_before"]
    novo = (vault.cfg.vault / rel).read_text(encoding="utf-8")
    assert novo.startswith("---\ntitle: Sessao velha\ndate: 2026-01-01\ncompacted: true\n---\n\n")
    assert "## Retained facts" in novo and "- `src/app/main.py`\n" in novo and "- `E0433`\n" in novo
    assert PROSA not in novo and len(novo.encode()) < len(VELHA.encode()) // 3  # sobra o resumo de ate 500 bytes
    assert "vault_note_restore" in novo
    # reversivel: a versao anterior esta no historico, e restaurar a traz de volta
    h = historico_vault.abrir(vault.cfg)
    assert h.texto(rel, 2) == VELHA
    out = historico_vault.restaurar(vault, rel, 2)
    assert "error" not in out and (vault.cfg.vault / rel).read_text(encoding="utf-8") == VELHA


def test_aplicar_leva_a_expirada_para_a_lixeira_sem_apagar(vault):
    rel = "Reference/2026-01-01-valida.md"
    r = ev.varrer(vault, aplicar=True, agora_us=AGORA)
    feito = next(x for x in r["applied"] if x["path"] == rel)
    assert feito["status"] == "forgotten" and feito["trash"].startswith(".lixeira/")
    assert not (vault.cfg.vault / rel).exists() and (vault.cfg.vault / feito["trash"]).is_file()
    assert rel in vault.apagadas
    assert historico_vault.abrir(vault.cfg).texto(rel, 1) is not None


def test_esquecer_leva_o_contador_junto(vault):
    rel = "Reference/2026-01-01-valida.md"
    ev.acessos(vault.cfg).registrar(rel, AGORA - 3 * DIA, vezes=2)
    ev.varrer(vault, aplicar=True, agora_us=AGORA)
    assert ev.acessos(vault.cfg).obter(rel) is None


def test_restaurar_conta_como_leitura_e_poupa_a_nota_da_proxima_varredura(vault):
    rel = "Sessions/2026-01-01-velha.md"
    ev.varrer(vault, aplicar=True, agora_us=AGORA)
    out = historico_vault.restaurar(vault, rel, 2)
    assert "error" not in out
    ev.depois_de_restaurar(vault.cfg, rel, out)  # o que a ferramenta e o painel fazem depois de restaurar
    # a nota voltou inteira e velha, mas alguem foi busca-la: nao e compactada de novo na hora
    assert (vault.cfg.vault / rel).read_text(encoding="utf-8") == VELHA
    assert rel not in _caminhos(ev.varrer(vault, agora_us=int(datetime.now().timestamp() * 1_000_000))["to_compact"])


def test_a_segunda_varredura_nao_refaz_nada(vault):
    ev.varrer(vault, aplicar=True, agora_us=AGORA)
    r2 = ev.varrer(vault, agora_us=AGORA)
    assert r2["to_compact"] == [] and r2["expired"] == [] and r2["to_forget"] == []


def test_nota_lida_o_bastante_nao_esfria(vault):
    rel = "Sessions/2026-01-01-velha.md"
    ev.acessos(vault.cfg).registrar(rel, AGORA - DIA, vezes=8)
    assert ev.varrer(vault, agora_us=AGORA)["to_compact"] == []


def test_registrar_leituras_conta_cada_nota_uma_vez_por_chamada(vault):
    rel = "Sessions/2026-01-01-velha.md"
    ev.registrar_leituras(vault.cfg, [rel, rel, "", rel])
    assert ev.acessos(vault.cfg).obter(rel)["total"] == 1


def test_voto_stale_derruba_a_saliencia_e_esfria_antes(vault):
    # 55 dias sem uso: ainda acima do limiar com a saliencia padrao
    _escrever(vault.cfg.vault, "Sessions/2026-08-23-recente.md", "---\ntitle: R\n---\n\n" + PROSA)
    assert "Sessions/2026-08-23-recente.md" not in _caminhos(ev.varrer(vault, agora_us=AGORA)["to_compact"])
    out = ev.votar(vault, "2026-08-23-recente", "stale")
    assert out == {"status": "ok", "path": "Sessions/2026-08-23-recente.md", "vote": "stale", "salience": 0.25}
    assert "Sessions/2026-08-23-recente.md" in _caminhos(ev.varrer(vault, agora_us=AGORA)["to_compact"])


def test_voto_invalido_e_nota_ambigua_ou_ausente(vault):
    assert ev.votar(vault, "velha", "talvez")["kind"] == "invalid"
    assert "error" in ev.votar(vault, "nao-existe-mesmo", "stale")


def test_limite_corta_a_aplicacao_e_conta_o_resto(vault):
    for i in range(1, 5):
        _escrever(vault.cfg.vault, f"Sessions/2026-01-0{i}-extra{i}.md", "---\ntitle: E\n---\n\n" + PROSA)
    r = ev.varrer(vault, aplicar=True, limite=2, agora_us=AGORA)
    compactadas = [x for x in r["applied"] if x.get("status") == "compacted"]
    assert len(compactadas) == 2 and r["remaining"] >= 2


def test_compactar_desligado_esquece_a_fria_pela_lixeira(vault):
    vault.cfg.envelhecimento_compactar = False
    rel = "Sessions/2026-01-01-velha.md"
    r = ev.varrer(vault, aplicar=True, agora_us=AGORA)
    assert rel in _caminhos(r["to_forget"]) and r["to_compact"] == []
    assert not (vault.cfg.vault / rel).exists()


def test_nota_pequena_demais_para_compactar_e_pulada_e_fica_como_esta(vault):
    rel = "Sessions/2026-01-03-curta.md"
    _escrever(vault.cfg.vault, rel, "---\ntitle: C\n---\n\ncurta\n")
    r = ev.varrer(vault, aplicar=True, agora_us=AGORA)
    feito = next(x for x in r["applied"] if x["path"] == rel)
    assert "skipped" in feito
    assert (vault.cfg.vault / rel).read_text(encoding="utf-8") == "---\ntitle: C\n---\n\ncurta\n"


def test_pasta_episodica_configuravel(vault):
    vault.cfg.envelhecimento_pastas = ["Decisions"]
    r = ev.varrer(vault, agora_us=AGORA)
    assert _caminhos(r["to_compact"]) == ["Decisions/2026-01-01-decisao.md"]


def test_idade_vem_da_data_da_nota_e_nao_do_mtime(vault):
    # reescrever a nota agora (como um relink) nao a rejuvenesce
    rel = "Sessions/2026-01-01-velha.md"
    (vault.cfg.vault / rel).write_text(VELHA + "\n## Related\n- [[x]]\n", encoding="utf-8")
    assert rel in _caminhos(ev.varrer(vault, agora_us=AGORA)["to_compact"])


def test_texto_compactado_preserva_o_frontmatter_e_trata_notas_sem_ele():
    com = ev.texto_compactado("---\ntitle: T\ntags:\n  - a\n---\n\n" + PROSA + "\n`ARQ_CONST_X`\n")
    assert com.startswith("---\ntitle: T\ntags:\n  - a\ncompacted: true\n---\n\n")
    sem = ev.texto_compactado("so prosa " * 200)
    assert sem.startswith("---\ncompacted: true\n---\n\n")
    falso = ev.texto_compactado("---\ntitle: T\ncompacted: false\n---\n\n" + PROSA)
    assert "compacted: true" in falso and "compacted: false" not in falso


def test_expires_at_aceita_data_data_e_hora_e_texto(vault):
    for nome, valor in (("a", "2026-02-01"), ("b", "2026-02-01T10:00:00"), ("c", '"2026-02-01T10:00:00Z"'), ("d", "2099-01-01")):
        _escrever(vault.cfg.vault, f"Reference/2026-01-05-{nome}.md", f"---\nexpires_at: {valor}\n---\n\ncorpo\n")
    _escrever(vault.cfg.vault, "Reference/2026-01-05-e.md", "---\nexpires_at: nao e data\n---\n\ncorpo\n")
    vencidas = _caminhos([{"path": e["path"]} for e in ev.varrer(vault, agora_us=AGORA)["expired"]])
    for nome in "abc":
        assert f"Reference/2026-01-05-{nome}.md" in vencidas
    assert "Reference/2026-01-05-d.md" not in vencidas and "Reference/2026-01-05-e.md" not in vencidas


def test_meia_vida_invalida_cai_no_padrao(vault):
    vault.cfg.envelhecimento_meia_vida_dias = -3
    assert ev.parametros(vault.cfg).lamb == pytest.approx(0.6931471805599453 / 35.0)
