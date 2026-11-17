"""Modo agent: o delegation-core nao sobe o modelo local por conta propria.

Medido em 2026-11-04 nesta maquina, com `engine_mode: agent`: cada write_note e
vault_update_note agendava a extracao de fatos (fatos_vault.apos_escrita), que
chamava `perguntar_local` com force_local=True e subia o gemma de 12B. Foram
10 GB de VRAM ocupados, a GPU em 0%, por mais de 10 minutos depois do ultimo
pedido, porque o engine descartavel de cada chamada nao e o dono que a
descarga por ociosidade conhece. Os jobs noturnos (fatos, digestao, sonho)
faziam o mesmo.

Decisao do usuario: em modo agent o servidor local fica desligado; se a tarefa
for grande, o job diz quanto e pergunta, em vez de ligar. `local_em_modo_agent`
e a autorizacao explicita.
"""

import pytest

from delegation_core import digestao_vault, engine, fatos_vault, sonho_vault
from delegation_core.config import Config
from tests.test_fatos import _vault


def _agent(v, **extra):
    v.cfg.engine_mode = "agent"
    for k, val in extra.items():
        setattr(v.cfg, k, val)
    return v


@pytest.fixture
def sem_modelo(monkeypatch):
    """Qualquer tentativa de falar com o modelo local reprova o teste."""
    def proibido(*a, **k):
        pytest.fail("subiu o modelo local em modo agent")
    monkeypatch.setattr(engine, "DelegationEngine", proibido)
    monkeypatch.setattr(engine, "perguntar_local", proibido)
    monkeypatch.setattr(fatos_vault, "SUBMETER_PADRAO", None, raising=False)


# ── a regra ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("modo,permite,esperado", [
    ("local", False, True), ("hybrid", False, True),
    ("agent", False, False), ("agent", True, True),
])
def test_quem_pode_usar_o_modelo_local(modo, permite, esperado):
    cfg = Config(engine_mode=modo, local_em_modo_agent=permite)
    assert engine.modelo_local_liberado(cfg) is esperado


def test_perguntar_local_recusa_em_modo_agent_sem_criar_motor(monkeypatch):
    monkeypatch.setattr(engine, "DelegationEngine",
                        lambda *a, **k: pytest.fail("criou o motor em modo agent"))
    perguntar = engine.perguntar_local(Config(engine_mode="agent"))
    with pytest.raises(engine.ModeloLocalDesligado):
        perguntar("sistema", "pergunta")


# ── os jobs ─────────────────────────────────────────────────────────────────

def test_fatos_em_modo_agent_adia_e_diz_quanto_falta(tmp_path, sem_modelo):
    v = _agent(_vault(tmp_path))
    r = fatos_vault.extrair_pendentes(v)
    assert r["skipped"] == "agent_mode"
    assert r["pending"] == 2
    assert "local_em_modo_agent" in r["offer"] and "2" in r["offer"]
    fatos_vault._ARMAZEM.clear()


def test_escrita_em_modo_agent_nao_agenda_extracao(tmp_path, sem_modelo):
    v = _agent(_vault(tmp_path))
    chamadas = []
    r = fatos_vault.apos_escrita(v, "Fixes/2026-09-26-porta.md",
                                 submeter=lambda *a: chamadas.append(a) or "job1")
    assert r is None and chamadas == []
    fatos_vault._ARMAZEM.clear()


def test_escrita_com_autorizacao_agenda_como_antes(tmp_path):
    v = _agent(_vault(tmp_path), local_em_modo_agent=True)
    chamadas = []
    r = fatos_vault.apos_escrita(v, "Fixes/2026-09-26-porta.md",
                                 submeter=lambda *a: chamadas.append(a) or "job1")
    assert r == "job1" and len(chamadas) == 1
    fatos_vault._ARMAZEM.clear()


def test_digestao_em_modo_agent_adia(tmp_path, sem_modelo, monkeypatch):
    v = _agent(_vault(tmp_path))
    monkeypatch.setattr(digestao_vault, "pendentes", lambda cfg: ["a", "b", "c"])
    r = digestao_vault.digerir(v)
    assert r["skipped"] == "agent_mode" and r["pending"] == 3
    assert "local_em_modo_agent" in r["offer"]


def test_sonho_em_modo_agent_adia(tmp_path, sem_modelo):
    v = _agent(_vault(tmp_path))
    r = sonho_vault.sonhar_e_registrar(v)
    assert r["skipped"] == "agent_mode"
    assert "local_em_modo_agent" in r["offer"]


def test_com_perguntar_explicito_o_job_roda_mesmo_em_modo_agent(tmp_path):
    """Quem passa a propria funcao de pergunta nao usa o modelo local: nao ha o que barrar."""
    from tests.test_fatos import perguntar_porta
    v = _agent(_vault(tmp_path))
    r = fatos_vault.extrair_pendentes(v, perguntar=perguntar_porta)
    assert r["extracted_notes"] == 2
    fatos_vault._ARMAZEM.clear()


# ── quando autorizado, o modelo sai depois de ocioso ────────────────────────

class _Processo:
    def __init__(self):
        self.terminado = False
    def poll(self):
        return 0 if self.terminado else None
    def terminate(self):
        self.terminado = True
    def wait(self, timeout=None):
        return 0
    def kill(self):
        self.terminado = True


def _motor_com_processo():
    eng = engine.DelegationEngine(Config(engine_mode="agent", local_em_modo_agent=True))
    eng._proc = _Processo()
    eng._we_started_it = True
    return eng


def test_ocioso_autorizado_libera_o_modelo(monkeypatch):
    eng = _motor_com_processo()
    monkeypatch.setattr(engine, "queue_stats", lambda: {"running": 0, "waiting": 0})
    engine._liberar_se_ocioso(eng)
    assert eng._proc.terminado


def test_com_fila_nao_libera(monkeypatch):
    eng = _motor_com_processo()
    monkeypatch.setattr(engine, "queue_stats", lambda: {"running": 1, "waiting": 0})
    engine._liberar_se_ocioso(eng)
    assert not eng._proc.terminado


def test_modo_local_nunca_libera(monkeypatch):
    """Em local/hybrid o modelo e o motor de todo mundo: soltar custa um reload na proxima chamada."""
    eng = engine.DelegationEngine(Config(engine_mode="local"))
    eng._proc, eng._we_started_it = _Processo(), True
    monkeypatch.setattr(engine, "queue_stats", lambda: {"running": 0, "waiting": 0})
    engine._liberar_se_ocioso(eng)
    assert not eng._proc.terminado


# ── a ligacao: a pergunta autorizada agenda a liberacao ─────────────────────

def test_pergunta_autorizada_usa_um_motor_so_e_agenda_a_liberacao(monkeypatch):
    cfg = Config(engine_mode="agent", local_em_modo_agent=True, llama_port=18999)
    criados, agendados = [], []

    class _Motor:
        def __init__(self, c):
            criados.append(self)
            self.cfg = c
        async def invoke(self, prompt, **kw):
            return "resposta"
        async def aclose(self):
            pass

    monkeypatch.setattr(engine, "DelegationEngine", _Motor)
    monkeypatch.setattr(engine, "_motores", {})
    monkeypatch.setattr(engine, "_agendar_liberacao", lambda eng: agendados.append(eng))
    perguntar = engine.perguntar_local(cfg)
    assert perguntar("s", "p1") == "resposta" and perguntar("s", "p2") == "resposta"
    assert len(criados) == 1, "um motor novo por pergunta e o que deixava o processo orfao"
    assert agendados == [criados[0], criados[0]]


def test_o_temporizador_libera_depois_da_ociosidade(monkeypatch):
    import time
    cfg = Config(engine_mode="agent", local_em_modo_agent=True, local_idle_shutdown_sec=1, llama_port=18998)
    eng = engine.DelegationEngine(cfg)
    eng._proc, eng._we_started_it = _Processo(), True
    monkeypatch.setattr(engine, "queue_stats", lambda: {"running": 0, "waiting": 0})
    monkeypatch.setattr(cfg, "local_idle_shutdown_sec", 0.05, raising=False)
    engine._agendar_liberacao(eng)
    for _ in range(40):
        if eng._proc.terminado:
            break
        time.sleep(0.05)
    assert eng._proc.terminado


def test_sem_ociosidade_configurada_ou_fora_do_modo_agent_nao_agenda(monkeypatch):
    for cfg in (Config(engine_mode="agent", local_idle_shutdown_sec=0, llama_port=18997),
                Config(engine_mode="local", local_idle_shutdown_sec=5, llama_port=18996)):
        eng = engine.DelegationEngine(cfg)
        engine._agendar_liberacao(eng)
        assert cfg.llama_port not in engine._liberacoes
