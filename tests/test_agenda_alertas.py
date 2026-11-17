"""Pacotes agenda (cron + tarefas recorrentes) e alertas (regras com espera)."""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

import pytest

from delegation_core.agenda import Agenda, Cron, CronInvalido, Tarefa, tarefas_de_config
from delegation_core.alertas import Disparo, MotorDeAlertas, Regra

RAIZ = Path(__file__).resolve().parents[1] / "src" / "delegation_core"
D = datetime


# ── cron ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr,depois,esperado", [
    ("*/10 * * * *", D(2026, 9, 27, 0, 21), D(2026, 9, 27, 0, 30)),
    ("0 * * * *", D(2026, 9, 27, 0, 0), D(2026, 9, 27, 1, 0)),          # estritamente depois
    ("30 4 * * *", D(2026, 9, 27, 5, 0), D(2026, 9, 28, 4, 30)),
    ("0 9 * * 1-5", D(2026, 9, 26, 10, 0), D(2026, 9, 28, 9, 0)),       # sabado -> segunda
    ("0 0 1 * *", D(2026, 12, 15, 0, 0), D(2027, 1, 1, 0, 0)),          # vira o ano
    ("0 0 29 2 *", D(2026, 3, 1, 0, 0), D(2028, 2, 29, 0, 0)),          # bissexto
    ("5/15 * * * *", D(2026, 9, 27, 0, 21), D(2026, 9, 27, 0, 35)),
    ("0 12 * * 0", D(2026, 9, 27, 13, 0), D(2026, 10, 4, 12, 0)),       # 27/09/2026 e domingo
    ("0 12 * * 7", D(2026, 9, 27, 13, 0), D(2026, 10, 4, 12, 0)),       # 7 tambem e domingo
    ("@daily", D(2026, 9, 27, 0, 21), D(2026, 9, 28, 0, 0)),
    ("0 8-18/2 * * *", D(2026, 9, 27, 9, 0), D(2026, 9, 27, 10, 0)),
])
def test_proxima(expr, depois, esperado):
    assert Cron.ler(expr).proxima(depois) == esperado


def test_dia_do_mes_e_da_semana_restritos_valem_por_ou():
    """`0 9 1 * 1`: todo dia 1 E toda segunda. 28/09/2026 e segunda, antes do dia 1."""
    assert Cron.ler("0 9 1 * 1").proxima(D(2026, 9, 27, 0, 0)) == D(2026, 9, 28, 9, 0)
    assert Cron.ler("0 9 1 * 1").casa(D(2026, 10, 1, 9, 0))


def test_so_semana_restrita_exige_a_semana():
    assert not Cron.ler("0 9 * * 1").casa(D(2026, 10, 1, 9, 0))  # quinta
    # segunda: Python diz weekday()=0 e o cron diz 1; sem a conversao nao casaria
    assert Cron.ler("0 9 * * 1").casa(D(2026, 9, 28, 9, 0))


@pytest.mark.parametrize("ruim", ["", "* * * *", "60 * * * *", "* 24 * * *", "* * 0 * *",
                                  "*/0 * * * *", "a * * * *", "5-1 * * * *", "1,,2 * * * *"])
def test_cron_invalido_na_leitura(ruim):
    """Erro de escrita tem que aparecer ao ler a config, e nao na primeira execucao."""
    with pytest.raises(CronInvalido):
        Cron.ler(ruim)


def test_cron_que_nunca_casa_e_recusado_ao_calcular():
    with pytest.raises(CronInvalido):
        Cron.ler("0 0 31 2 *").proxima(D(2026, 1, 1))


# ── agenda ──────────────────────────────────────────────────────────────────

@pytest.fixture
def agenda(tmp_path):
    return Agenda(tmp_path / "agenda.json", [Tarefa("hist", "0 * * * *", "historico"),
                                             Tarefa("off", "* * * * *", "x", ligada=False)])


def test_primeira_vez_nao_dispara(agenda):
    assert agenda.devidas(D(2026, 9, 27, 0, 30)) == []
    assert agenda.devidas(D(2026, 9, 27, 0, 59)) == []
    assert [t.nome for t in agenda.devidas(D(2026, 9, 27, 1, 0))] == ["hist"]


def test_atraso_vira_uma_execucao_so(agenda):
    agenda.devidas(D(2026, 9, 27, 0, 30))
    devidas = agenda.devidas(D(2026, 9, 27, 12, 5))  # perdeu 12 horarios
    assert [t.nome for t in devidas] == ["hist"]
    agenda.executar(devidas[0], lambda a: "ok", agora=D(2026, 9, 27, 12, 5))
    assert agenda.devidas(D(2026, 9, 27, 12, 30)) == []
    assert [t.nome for t in agenda.devidas(D(2026, 9, 27, 13, 0))] == ["hist"]


def test_executar_registra_sucesso_e_falha(agenda):
    t = agenda.tarefas["hist"]
    agenda.executar(t, lambda a: (_ for _ in ()).throw(OSError("disco cheio")))
    agenda.executar(t, lambda a: (_ for _ in ()).throw(OSError("disco cheio")))
    e = agenda.estado("hist")
    assert e["ultimo_status"] == "erro" and e["falhas_seguidas"] == 2 and "disco cheio" in e["ultimo_erro"]
    agenda.executar(t, lambda a: {"lidas": 3})
    e = agenda.estado("hist")
    assert e["falhas_seguidas"] == 0 and e["ultimo_resultado"] == {"lidas": 3} and e["execucoes"] == 3
    assert "ultimo_erro" not in e


def test_executor_recebe_copia_dos_argumentos(tmp_path):
    t = Tarefa("x", "* * * * *", "a", argumentos={"k": 1})
    ag = Agenda(tmp_path / "a.json", [t])
    ag.executar(t, lambda a: a.update(k=2))
    assert t.argumentos == {"k": 1}


def test_estado_sobrevive_ao_processo(agenda, tmp_path):
    agenda.devidas(D(2026, 9, 27, 0, 30))
    agenda.executar(agenda.tarefas["hist"], lambda a: 1, agora=D(2026, 9, 27, 1, 0))
    outra = Agenda(tmp_path / "agenda.json", [Tarefa("hist", "0 * * * *", "historico")])
    assert outra.estado("hist")["execucoes"] == 1
    assert outra.devidas(D(2026, 9, 27, 1, 30)) == []


def test_tarefa_rodando_nao_dispara_de_novo_e_orfa_e_solta(agenda, tmp_path):
    agenda.devidas(D(2026, 9, 27, 0, 30))
    agenda._estado["hist"]["rodando"] = True
    assert agenda.devidas(D(2026, 9, 27, 2, 0)) == []
    assert agenda.destravar_orfas() == ["hist"]
    assert agenda.estado("hist")["ultimo_status"] == "interrompida"
    assert [t.nome for t in agenda.devidas(D(2026, 9, 27, 2, 0))] == ["hist"]


def test_resultado_grande_vira_resumo(agenda):
    agenda.executar(agenda.tarefas["hist"], lambda a: "x" * 5000)
    assert agenda.estado("hist")["ultimo_resultado"]["tamanho"] > 5000


def test_proximas(agenda):
    agenda.devidas(D(2026, 9, 27, 0, 30))
    p = {d["nome"]: d for d in agenda.proximas(D(2026, 9, 27, 0, 30))}
    assert p["hist"]["proxima"] == "2026-09-27T01:00" and p["off"]["proxima"] is None


def test_tarefas_de_config_recusa_invalida_e_repetida():
    ok, erros = tarefas_de_config([
        {"nome": "a", "cron": "0 * * * *", "acao": "x"},
        {"nome": "b", "cron": "99 * * * *", "acao": "x"},
        {"nome": "a", "cron": "0 * * * *", "acao": "y"},
        {"cron": "0 * * * *", "acao": "x"},
    ])
    assert [t.nome for t in ok] == ["a"] and len(erros) == 3
    assert "repetido" in erros[1] and "minuto" in erros[0]


# ── alertas ─────────────────────────────────────────────────────────────────

def _motor(tmp_path, errados, para_s=60.0):
    regra = Regra("disco", lambda ctx: [Disparo(s, f"{s} cheio") for s in errados], "critico", para_s)
    return MotorDeAlertas(tmp_path / "alertas.json", [regra])


def test_pendente_antes_do_periodo_e_disparando_depois(tmp_path):
    errados = ["/home"]
    m = _motor(tmp_path, errados)
    r = m.avaliar(None, agora=1000)
    assert r["eventos"] == [] and [a["sujeito"] for a in r["pendentes"]] == ["/home"]
    r = m.avaliar(None, agora=1059)
    assert r["eventos"] == []
    r = m.avaliar(None, agora=1060)
    assert [e["tipo"] for e in r["eventos"]] == ["aberto"] and r["abertos"][0]["severidade"] == "critico"
    assert m.avaliar(None, agora=1100)["eventos"] == []  # aviso so na transicao


def test_tropeco_curto_some_calado(tmp_path):
    errados = ["/home"]
    m = _motor(tmp_path, errados)
    m.avaliar(None, agora=1000)
    errados.clear()
    r = m.avaliar(None, agora=1030)
    assert r["eventos"] == [] and r["pendentes"] == []


def test_resolvido_gera_evento_com_duracao(tmp_path):
    errados = ["/home"]
    m = _motor(tmp_path, errados, para_s=0)
    m.avaliar(None, agora=1000)
    errados.clear()
    r = m.avaliar(None, agora=1300)
    assert r["eventos"][0]["tipo"] == "resolvido" and r["eventos"][0]["durou_s"] == 300


def test_sujeitos_independentes(tmp_path):
    errados = ["/a", "/b"]
    m = _motor(tmp_path, errados, para_s=0)
    m.avaliar(None, agora=1)
    errados.remove("/a")
    r = m.avaliar(None, agora=2)
    assert [(e["tipo"], e["sujeito"]) for e in r["eventos"]] == [("resolvido", "/a")]
    assert [a["sujeito"] for a in r["abertos"]] == ["/b"]


def test_regra_quebrada_vira_alerta_e_nao_derruba_as_outras(tmp_path):
    def quebra(ctx):
        raise KeyError("campo")
    m = MotorDeAlertas(tmp_path / "a.json", [Regra("ruim", quebra), Regra("boa", lambda c: [Disparo("x", "ok")])])
    r = m.avaliar(None, agora=1)
    assert {a["regra"] for a in r["abertos"]} == {"regra_quebrada", "boa"}
    assert "KeyError" in next(a for a in r["abertos"] if a["regra"] == "regra_quebrada")["mensagem"]


def test_estado_persiste_e_eventos_tem_teto(tmp_path):
    errados = ["/a"]
    m = _motor(tmp_path, errados, para_s=0)
    for i in range(10):
        errados[:] = ["/a"] if i % 2 == 0 else []
        m.avaliar(None, agora=i, manter_eventos=4)
    assert len(json.loads((tmp_path / "alertas.json").read_text())["eventos"]) == 4
    m2 = _motor(tmp_path, ["/a"], para_s=0)
    assert m2.eventos(limite=1)[0]["tipo"] == "resolvido"


def test_abertos_ordenados_por_severidade(tmp_path):
    m = MotorDeAlertas(tmp_path / "a.json", [
        Regra("i", lambda c: [Disparo("x", "")], "info"),
        Regra("c", lambda c: [Disparo("x", "")], "critico"),
        Regra("a", lambda c: [Disparo("x", "")], "aviso"),
    ])
    assert [a["severidade"] for a in m.avaliar(None, agora=1)["abertos"]] == ["critico", "aviso", "info"]


@pytest.mark.parametrize("pacote", ["agenda", "alertas"])
def test_pacote_nao_importa_o_nucleo(pacote):
    proibidos = []
    for arq in (RAIZ / pacote).glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom) and (no.level >= 2 or (no.module or "").startswith("delegation_core")):
                proibidos.append(f"{arq.name}: {no.module}")
    assert proibidos == []
