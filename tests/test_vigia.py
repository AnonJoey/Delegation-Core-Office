"""O vigia: regras sobre estado real (em vault temporario), acoes, ciclo, aviso e ferramentas."""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import delegation_core.server as server
from delegation_core import historico_vault, vigia
from delegation_core.alertas import Disparo


class VaultFalso:
    def __init__(self, cfg, saude=None):
        self.cfg = cfg
        self.saude = saude or {}
        self.reindex = 0

    def get_health_summary(self):
        return self.saude

    def reindex_vault(self, force=False):
        self.reindex += 1
        return 7


class TrackerFalso:
    def __init__(self, processos):
        self.p = processos

    def list_processes(self, status="active"):
        return self.p


@pytest.fixture
def base(tmp_path):
    raiz = tmp_path / "vault"
    (raiz / "Fixes").mkdir(parents=True)
    for i in range(3):
        (raiz / "Fixes" / f"n{i}.md").write_text(f"nota {i}")
    cfg = SimpleNamespace(vault=raiz, vault_folders=["Fixes"], historico_enabled=True,
                          alerta_indice_atrasado=1, alerta_processo_parado_dias=14,
                          alertas_desktop=False, agenda_tarefas=None)
    conf = tmp_path / "conf"
    conf.mkdir()
    historico_vault._INSTANCIAS.clear()
    yield SimpleNamespace(cfg=cfg, raiz=raiz, conf=conf)
    for h in historico_vault._INSTANCIAS.values():
        h.fechar()
    historico_vault._INSTANCIAS.clear()


def _ctx(b, vault=None, tracker=None, agenda=None):
    return SimpleNamespace(cfg=b.cfg, vault=vault or VaultFalso(b.cfg), tracker=tracker,
                           agenda=agenda, config_dir=b.conf)


def _carimbar(b, rels):
    estado = {r: (b.raiz / r).stat().st_mtime for r in rels}
    (b.raiz / ".chroma_index.json").write_text(json.dumps(estado))


# ── regras, cada uma no caso que a motivou ──────────────────────────────────

def test_indice_atrasado_dispara_acima_do_limite(base):
    """O caso de 26/09: notas mudaram, o carimbo ficou para tras, nada avisava."""
    _carimbar(base, ["Fixes/n0.md", "Fixes/n1.md", "Fixes/n2.md"])
    assert vigia.regra_indice_atrasado(_ctx(base)) == []
    for i in (0, 1):
        f = base.raiz / "Fixes" / f"n{i}.md"
        f.write_text("mudou")
        os.utime(f, (time.time() + 10, time.time() + 10))
    d = vigia.regra_indice_atrasado(_ctx(base))
    assert len(d) == 1 and d[0].detalhe["notas"] == 2


def test_indice_atrasado_conta_nota_nunca_carimbada(base):
    _carimbar(base, ["Fixes/n0.md"])
    assert vigia.regra_indice_atrasado(_ctx(base))[0].detalhe["notas"] == 2


def test_saude_do_vault(base):
    v = VaultFalso(base.cfg, {"needs_repair": 6, "broken_links": 2, "malformed_frontmatter": 0})
    assert sorted(d.sujeito for d in vigia.regra_saude_do_vault(_ctx(base, vault=v))) == ["broken_links", "needs_repair"]
    v.saude = {"needs_repair": 5, "broken_links": 0}
    assert vigia.regra_saude_do_vault(_ctx(base, vault=v)) == []


def test_sentinela_esquecida(base):
    assert vigia.regra_sentinela_esquecida(_ctx(base)) == []
    s = base.conf / "no_auto_reindex"
    s.write_text("")
    velho = time.time() - 26 * 86400
    os.utime(s, (velho, velho))
    d = vigia.regra_sentinela_esquecida(_ctx(base))
    assert d[0].sujeito == "no_auto_reindex" and d[0].detalhe["dias"] == pytest.approx(26, abs=0.1)


def test_inbox_parado_so_depois_de_24h(base):
    inbox = base.raiz / "_inbox"
    inbox.mkdir()
    (inbox / "novo.pdf").write_text("x")
    velho = inbox / "foto.png"
    velho.write_text("x")
    t = time.time() - 30 * 3600
    os.utime(velho, (t, t))
    d = vigia.regra_inbox_parado(_ctx(base))
    assert d[0].detalhe["arquivos"] == [("foto.png", 30)]


def test_processo_parado(base):
    antigo = datetime.fromtimestamp(time.time() - 20 * 86400).isoformat()
    recente = datetime.now().isoformat()
    t = TrackerFalso([{"id": "p1", "name": "velho", "updated": antigo},
                      {"id": "p2", "name": "novo", "updated": recente},
                      {"id": "p3", "name": "sem data", "updated": "lixo"}])
    assert [d.sujeito for d in vigia.regra_processo_parado(_ctx(base, tracker=t))] == ["p1"]


def test_disco(base, monkeypatch):
    monkeypatch.setattr(vigia.shutil, "disk_usage", lambda p: SimpleNamespace(total=100e9, free=3e9, used=97e9))
    assert "3.0 GB" in vigia.regra_disco(_ctx(base))[0].mensagem
    monkeypatch.setattr(vigia.shutil, "disk_usage", lambda p: SimpleNamespace(total=100e9, free=50e9, used=50e9))
    assert vigia.regra_disco(_ctx(base)) == []


def test_agenda_falhando(base):
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    t = v.agenda.tarefas["historico-horario"]
    for _ in range(2):
        v.agenda.executar(t, lambda a: (_ for _ in ()).throw(RuntimeError("quebrou")))
    d = vigia.regra_agenda_falhando(v.contexto())
    assert [x.sujeito for x in d] == ["historico-horario"] and "quebrou" in d[0].detalhe["ultimo_erro"]


# ── vigia: acoes, ciclo, aviso ──────────────────────────────────────────────

def test_tarefas_padrao_carregam_sem_erro(base):
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    assert v.erros_de_config == [] and set(v.agenda.tarefas) == {
        "historico-horario", "alertas", "reindex-noturno", "podar-historico", "sonho-noturno", "boletim-diario",
        "digestao-noturna", "fatos-noturno"}
    assert {t.acao for t in v.agenda.tarefas.values()} <= set(v.acoes())


def test_lista_vazia_na_config_desliga_todas(base):
    base.cfg.agenda_tarefas = []
    assert vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf).agenda.tarefas == {}


def test_rodar_historico_fotografa(base):
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    r = v.rodar("historico-horario")
    assert r["ultimo_status"] == "ok" and r["ultimo_resultado"]["novas"] == 3


def test_reindex_vai_pela_fila_de_jobs_quando_ha(base):
    pedidos = []
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf,
                    submeter=lambda nome, fn, **kw: pedidos.append((nome, kw)) or "job1")
    assert v.rodar("reindex-noturno")["ultimo_resultado"] == {"job_id": "job1"}
    assert pedidos == [("vault_reindex:incremental", {"force": False})]


def test_rodar_tarefa_inexistente(base):
    assert "not found" in vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf).rodar("x")["error"]


def test_ciclo_roda_o_devido(base):
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    assert v.ciclo(datetime(2026, 9, 27, 0, 30)) == []  # primeira vez: ancora
    # 01:17 (historico) e 00:40 (alertas) ja passaram; 04:07 e 03:43 de domingo ainda nao
    assert v.ciclo(datetime(2026, 9, 27, 1, 20)) == ["historico-horario", "alertas"]
    assert v.ciclo(datetime(2026, 9, 27, 1, 25)) == []


def test_alertas_avisam_no_log(base, monkeypatch):
    base.cfg.alertas_desktop = True
    chamadas = []
    monkeypatch.setattr(vigia.shutil, "which", lambda n: "/usr/bin/notify-send")
    monkeypatch.setattr(vigia.subprocess, "run", lambda cmd, **kw: chamadas.append(cmd))
    vigia.avisar(base.cfg, base.conf, [{"tipo": "aberto", "regra": "disco", "sujeito": "/",
                                        "severidade": "critico", "mensagem": "3 GB livres"}])
    linha = json.loads((base.conf / "alertas.log").read_text().splitlines()[0])
    assert linha["regra"] == "disco"
    assert chamadas and "critical" in chamadas[0] and "3 GB livres" in chamadas[0]


def test_sem_notify_send_so_loga(base, monkeypatch):
    base.cfg.alertas_desktop = True
    monkeypatch.setattr(vigia.shutil, "which", lambda n: None)
    monkeypatch.setattr(vigia.subprocess, "run", lambda *a, **k: pytest.fail("nao devia chamar"))
    vigia.avisar(base.cfg, base.conf, [{"tipo": "resolvido", "regra": "r", "sujeito": "s",
                                        "severidade": "info", "mensagem": "m"}])
    assert (base.conf / "alertas.log").exists()


def test_acao_alertas_avalia_e_avisa(base):
    base.cfg.alerta_indice_atrasado = 0
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    v.alertas.regras = {"x": vigia.Regra("x", lambda c: [Disparo("s", "algo")], "aviso", 0.0)}
    r = v.acoes()["alertas"]({})
    assert r["abertos"] == 1 and r["eventos"] == ["aberto: x s"]
    assert "algo" in (base.conf / "alertas.log").read_text()


# ── ferramentas MCP ─────────────────────────────────────────────────────────

def _chamar(f, **kw):
    r = f(**kw)
    return json.loads(asyncio.run(r) if asyncio.iscoroutine(r) else r)


def test_ferramentas_desligadas_sem_vigia(monkeypatch):
    monkeypatch.setattr(server, "_vigia", None)
    for f in (server.alerts, server.schedule_list, server.alerts_check):
        assert _chamar(f)["error_type"] == "disabled"
    assert _chamar(server.schedule_run, name="x")["error_type"] == "disabled"


def test_ferramentas_com_vigia(base, monkeypatch):
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    monkeypatch.setattr(server, "_vigia", v)
    lista = _chamar(server.schedule_list)
    assert {t["nome"] for t in lista["tasks"]} >= {"alertas", "historico-horario"}
    assert _chamar(server.schedule_run, name="historico-horario")["ultimo_status"] == "ok"
    assert _chamar(server.schedule_run, name="nao-ha")["error_type"] == "not_found"
    assert set(_chamar(server.alerts)) == {"open", "events"}


def test_digestao_guarda_o_motivo_das_falhas(base, monkeypatch):
    """A agenda reduzia toda lista a uma contagem: 'falhas: 5' sem dizer por que, noite apos noite
    (digestao-noturna, 5 de 5 em 2026-11-04). Os motivos agora acompanham o resultado."""
    from delegation_core import digestao_vault
    monkeypatch.setattr(digestao_vault, "digerir", lambda vault, maximo=5: {
        "pendentes_antes": 5, "feitos": [], "restam": 0,
        "falhas": [{"transcricao": f"t{i}.md", "erro": f"erro {i}"} for i in range(5)]})
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    r = v.acoes()["digestao"]({})
    assert r["falhas"] == 5
    assert r["motivos"] == ["t0.md: erro 0", "t1.md: erro 1", "t2.md: erro 2"]


def test_digestao_adiada_em_modo_agent_passa_a_oferta_adiante(base, monkeypatch):
    from delegation_core import digestao_vault
    monkeypatch.setattr(digestao_vault, "digerir", lambda vault, maximo=5: {
        "skipped": "agent_mode", "pending": 4, "offer": "autorize"})
    v = vigia.Vigia(base.cfg, VaultFalso(base.cfg), config_dir=base.conf)
    assert v.acoes()["digestao"]({}) == {"skipped": "agent_mode", "pending": 4, "offer": "autorize"}
