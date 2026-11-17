"""Pacote passagem: escolha da passagem certa e aceitacao uma vez so, contra um sqlite temporario."""

from __future__ import annotations

import ast
import sqlite3
import threading
from pathlib import Path

import pytest

from delegation_core.passagem import normalizar_cwd
from delegation_core.passagem.armazem import (
    CAMPO_MAX_BYTES,
    LISTA_MAX_ITENS,
    EstadoInvalido,
    Passagens,
)

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "passagem"
P = "projeto"


@pytest.fixture
def pg(tmp_path):
    x = Passagens(tmp_path / "passagens.db")
    yield x
    x.fechar()


def _auto(pg, cwd="/repo", t=1_000, sessao="s1", resumo="r", **kw):
    pg.abrir_sessao(sessao, P, "claude", cwd, agora_us=t)
    pg.encerrar_sessao(sessao, agora_us=t)
    return pg.criar(projeto=P, de_agente="claude", resumo=resumo, cwd=cwd, de_sessao=sessao, agora_us=t, **kw)


def _manual(pg, t=1_000, cwd=None, resumo="m", **kw):
    return pg.criar(projeto=P, de_agente="pessoa", resumo=resumo, cwd=cwd, agora_us=t, **kw)


def _receptor(pg, sessao="r1", cwd="/repo", agente="claude"):
    pg.abrir_sessao(sessao, P, agente, cwd)
    return sessao


# ── escolha ────────────────────────────────────────────────────────────────


def test_sem_passagem_nao_ha_o_que_entregar(pg):
    assert pg.escolher(P, "/repo") is None


def test_automatica_so_serve_ao_mesmo_diretorio_ou_abaixo(pg):
    pid = _auto(pg, cwd="/repo")
    assert pg.escolher(P, "/repo")["id"] == pid
    assert pg.escolher(P, "/repo/api")["id"] == pid
    assert pg.escolher(P, "/repo-outro") is None
    assert pg.escolher(P, "/repositorio") is None
    assert pg.escolher(P, "/") is None


def test_manual_vale_para_o_projeto_todo_e_vence_a_automatica(pg):
    auto = _auto(pg, cwd="/repo", t=9_000)
    manual = _manual(pg, t=1_000)
    assert pg.escolher(P, "/repo")["id"] == manual
    assert pg.escolher(P, "/qualquer/lugar")["id"] == manual
    assert pg.obter(manual)["manual"] is True and pg.obter(auto)["manual"] is False


def test_entre_automaticas_vence_a_mais_nova(pg):
    _auto(pg, cwd="/repo", t=1_000, sessao="a")
    velho = _auto(pg, cwd="/repo/api", t=2_000, sessao="b")
    novo = _auto(pg, cwd="/repo/api/v1", t=3_000, sessao="c")
    # a de /repo/api/v1 e a mais nova e tambem serve a quem comeca la
    assert pg.escolher(P, "/repo/api/v1")["id"] == novo
    # quem comeca em /repo/api nao e servido pela de /repo/api/v1 (ela e mais profunda)
    assert pg.escolher(P, "/repo/api")["id"] == velho


def test_cwd_de_windows_ignora_caixa_da_unidade(pg):
    pid = _auto(pg, cwd="C:\\Users\\Ana\\proj")
    assert pg.escolher(P, "c:/users/ana/proj/src")["id"] == pid or pg.escolher(P, "C:/Users/Ana/proj/src")["id"] == pid
    assert normalizar_cwd("C:\\Users\\Ana\\proj\\") == "c:/users/ana/proj"


def test_projetos_nao_se_misturam(pg):
    _auto(pg)
    assert pg.escolher("outro", "/repo") is None


# ── aceitar ────────────────────────────────────────────────────────────────


def test_aceitar_marca_aceita_e_some_da_escolha(pg):
    pid = _auto(pg)
    r = _receptor(pg)
    assert pg.aceitar(pid, projeto=P, agente="claude", sessao=r, cwd_do_receptor="/repo") is True
    d = pg.obter(pid)
    assert d["estado"] == "aceita" and d["aceita_sessao"] == r and d["aceita_por"] == "claude"
    assert pg.escolher(P, "/repo") is None


def test_so_um_aceita_a_mesma_passagem(pg):
    pid = _manual(pg)
    a, b = _receptor(pg, "ra"), _receptor(pg, "rb")
    assert pg.aceitar(pid, projeto=P, agente="claude", sessao=a) is True
    assert pg.aceitar(pid, projeto=P, agente="claude", sessao=b) is False
    assert pg.obter(pid)["aceita_sessao"] == a


def test_corrida_de_threads_tem_um_vencedor_so(tmp_path):
    arq = tmp_path / "corrida.db"
    base = Passagens(arq)
    pid = _manual(base)
    sessoes = [f"r{i}" for i in range(12)]
    for s in sessoes:
        base.abrir_sessao(s, P, "claude", "/repo")
    base.fechar()

    resultados, barreira = [], threading.Barrier(len(sessoes))

    def corre(s):
        p = Passagens(arq)  # uma conexao por thread, como processos distintos
        try:
            barreira.wait()
            resultados.append(p.aceitar(pid, projeto=P, agente="claude", sessao=s))
        finally:
            p.fechar()

    ts = [threading.Thread(target=corre, args=(s,)) for s in sessoes]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(resultados) == [False] * (len(sessoes) - 1) + [True]


def test_uma_sessao_aceita_uma_passagem_so(pg):
    a = _manual(pg, t=1_000)
    b = _manual(pg, t=2_000)
    r = _receptor(pg)
    assert pg.aceitar(b, projeto=P, agente="claude", sessao=r) is True
    assert pg.aceitar(a, projeto=P, agente="claude", sessao=r) is False
    assert pg.obter(a)["estado"] == "aberta"


def test_aceitar_com_sessao_inexistente_ou_de_outro_agente_falha(pg):
    pid = _manual(pg)
    with pytest.raises(EstadoInvalido):
        pg.aceitar(pid, projeto=P, agente="claude", sessao="fantasma")
    _receptor(pg, "rx", agente="codex")
    with pytest.raises(EstadoInvalido):
        pg.aceitar(pid, projeto=P, agente="claude", sessao="rx")
    assert pg.obter(pid)["estado"] == "aberta"


def test_sessao_encerrada_nao_aceita_a_menos_que_reabra(pg):
    pid = _manual(pg)
    pg.abrir_sessao("rz", P, "claude", "/repo", agora_us=5)
    pg.encerrar_sessao("rz", agora_us=6)
    with pytest.raises(EstadoInvalido):
        pg.aceitar(pid, projeto=P, agente="claude", sessao="rz")
    assert pg.aceitar(pid, projeto=P, agente="claude", sessao="rz", reabre_sessao_apos_o_fim=True) is True


def test_aceitar_passagem_de_outro_projeto_devolve_false(pg):
    pid = _manual(pg)
    pg.abrir_sessao("ro", "outro", "claude", "/repo")
    assert pg.aceitar(pid, projeto="outro", agente="claude", sessao="ro") is False
    assert pg.obter(pid)["estado"] == "aberta"


def test_aceitar_automatica_expira_as_automaticas_superadas_e_nunca_a_manual(pg):
    velha = _auto(pg, cwd="/repo", t=1_000, sessao="a")
    meia = _auto(pg, cwd="/repo/api", t=2_000, sessao="b")
    nova = _auto(pg, cwd="/repo/api", t=3_000, sessao="c")
    manual = _manual(pg, t=500)
    # `criar` ja expirou a de mesmo cwd exato (meia); a velha de /repo ainda esta aberta
    assert pg.obter(meia)["estado"] == "expirada"
    assert pg.obter(velha)["estado"] == "aberta"
    r = _receptor(pg, "r1", cwd="/repo/api")
    assert pg.aceitar(nova, projeto=P, agente="claude", sessao=r, cwd_do_receptor="/repo/api") is True
    assert pg.obter(velha)["estado"] == "expirada"
    assert pg.obter(manual)["estado"] == "aberta"


def test_aceitar_uma_automatica_antiga_nao_expira_a_mais_nova(pg):
    antiga = _auto(pg, cwd="/repo", t=1_000, sessao="a")
    nova = _auto(pg, cwd="/repo/api", t=3_000, sessao="b")
    r = _receptor(pg, "r1", cwd="/repo/api")
    assert pg.aceitar(antiga, projeto=P, agente="claude", sessao=r, cwd_do_receptor="/repo/api") is True
    assert pg.obter(nova)["estado"] == "aberta"


def test_aceitar_nao_expira_automatica_de_sessao_ainda_aberta(pg):
    pg.abrir_sessao("viva", P, "claude", "/repo", agora_us=100)
    viva = pg.criar(projeto=P, de_agente="claude", resumo="x", cwd="/repo", de_sessao="viva", agora_us=100)
    nova = _auto(pg, cwd="/repo", t=9_000, sessao="fim")
    # criar() da nova no mesmo cwd poupa o baton da sessao aberta
    assert pg.obter(viva)["estado"] == "aberta"
    r = _receptor(pg, "r1")
    assert pg.aceitar(nova, projeto=P, agente="claude", sessao=r, cwd_do_receptor="/repo") is True
    assert pg.obter(viva)["estado"] == "aberta"


def test_criar_automatica_expira_as_do_mesmo_cwd_exato_e_poupa_o_resto(pg):
    mesma = _auto(pg, cwd="/repo", t=1_000, sessao="a")
    outra = _auto(pg, cwd="/repo/api", t=1_500, sessao="b")
    manual = _manual(pg, t=1_700)
    nova = _auto(pg, cwd="/repo", t=2_000, sessao="c")
    assert pg.obter(mesma)["estado"] == "expirada"
    assert pg.obter(outra)["estado"] == "aberta"
    assert pg.obter(manual)["estado"] == "aberta"
    assert pg.obter(nova)["estado"] == "aberta"


# ── dono ───────────────────────────────────────────────────────────────────


def test_filtro_de_dono_na_escolha_e_na_aceitacao(pg):
    meu = _manual(pg, t=1_000, dono="ana")
    alheio = _manual(pg, t=2_000, dono="bia")
    livre = _manual(pg, t=500)
    assert pg.escolher(P, "/repo", ("usuario", "ana"))["id"] == meu
    assert pg.escolher(P, "/repo", ("sem_dono",))["id"] == livre
    r = _receptor(pg)
    assert pg.aceitar(alheio, projeto=P, agente="claude", sessao=r, filtro_dono=("usuario", "ana"), usuario="ana") is False
    assert pg.obter(alheio)["estado"] == "aberta"
    with pytest.raises(EstadoInvalido):
        pg.aceitar(meu, projeto=P, agente="claude", sessao=r, filtro_dono=("usuario", "ana"), usuario="bia")
    with pytest.raises(EstadoInvalido):
        pg.aceitar(meu, projeto=P, agente="claude", sessao=r, filtro_dono=("usuario", "ana"))


def test_filtro_sem_dono_nao_aceita_passagem_de_alguem(pg):
    de_ana = _manual(pg, t=1_000, dono="ana")
    livre = _manual(pg, t=2_000)
    r = _receptor(pg)
    assert pg.aceitar(de_ana, projeto=P, agente="claude", sessao=r, filtro_dono=("sem_dono",)) is False
    assert pg.obter(de_ana)["estado"] == "aberta"
    with pytest.raises(EstadoInvalido):
        pg.aceitar(livre, projeto=P, agente="claude", sessao=r, filtro_dono=("sem_dono",), usuario="ana")
    assert pg.aceitar(livre, projeto=P, agente="claude", sessao=r, filtro_dono=("sem_dono",)) is True


def test_expirar_superadas_respeita_o_dono(pg):
    de_ana = _auto(pg, cwd="/repo", t=1_000, sessao="a", dono="ana")
    de_bia = _auto(pg, cwd="/repo", t=2_000, sessao="b", dono="bia")
    # criar() de bia no mesmo cwd nao toca no baton de ana
    assert pg.obter(de_ana)["estado"] == "aberta"
    r = _receptor(pg, "r1")
    assert pg.aceitar(de_bia, projeto=P, agente="claude", sessao=r, filtro_dono=("usuario", "bia"), usuario="bia", cwd_do_receptor="/repo")
    assert pg.obter(de_ana)["estado"] == "aberta"


# ── limites ────────────────────────────────────────────────────────────────


def test_campos_grandes_sao_cortados_em_bytes_e_listas_em_itens(pg):
    grande = "é" * CAMPO_MAX_BYTES  # 2 bytes por caractere
    pid = _manual(pg, resumo=grande, perguntas=[grande] * (LISTA_MAX_ITENS + 40))
    d = pg.obter(pid)
    assert len(d["resumo"].encode()) <= CAMPO_MAX_BYTES
    assert len(d["perguntas"]) == LISTA_MAX_ITENS
    assert all(len(x.encode()) <= CAMPO_MAX_BYTES for x in d["perguntas"])
    d["resumo"].encode("utf-8")  # nao corta no meio de um caractere


def test_cwd_guardado_sem_separador_no_fim(pg):
    pid = _auto(pg, cwd="/repo/api/")
    assert pg.obter(pid)["cwd"] == "/repo/api"
    assert pg.obter(_manual(pg, cwd="/"))["cwd"] == "/"


# ── encerrar sem aceitar ───────────────────────────────────────────────────


def test_expirar_abertas_limpa_inclusive_as_manuais(pg):
    a = _manual(pg, t=1_000)
    b = _auto(pg, cwd="/x", t=2_000, sessao="b")
    c = _manual(pg, t=9_000)
    n = pg.expirar_abertas(P, mais_antigas_que_us=2_000)
    assert n == 2
    assert [pg.obter(i)["estado"] for i in (a, b, c)] == ["expirada", "expirada", "aberta"]
    assert pg.expirar_abertas(P) == 1


def test_expirar_nao_apaga_o_resumo(pg):
    pid = _manual(pg, resumo="onde paramos")
    pg.expirar_abertas(P)
    d = pg.obter(pid)
    assert d["estado"] == "expirada" and d["resumo"] == "onde paramos"


def test_cancelar(pg):
    pid = _manual(pg, dono="ana")
    assert pg.cancelar(pid, projeto="outro") is False
    assert pg.cancelar(pid, projeto=P, filtro_dono=("usuario", "bia")) is False
    assert pg.cancelar(pid, projeto=P, filtro_dono=("usuario", "ana")) is True
    assert pg.cancelar(pid, projeto=P) is False


def test_listar_filtra_por_estado_e_ordena_pela_mais_nova(pg):
    a = _manual(pg, t=1_000)
    b = _manual(pg, t=2_000)
    pg.cancelar(a, projeto=P)
    assert [x["id"] for x in pg.listar(P)] == [b, a]
    assert [x["id"] for x in pg.listar(P, "aberta")] == [b]


# ── persistencia e auditoria ───────────────────────────────────────────────


def test_sobrevive_a_reabertura_e_audita(tmp_path):
    arq = tmp_path / "p.db"
    p = Passagens(arq)
    pid = _manual(p, resumo="fica")
    p.fechar()
    q = Passagens(arq)
    assert q.obter(pid)["resumo"] == "fica"
    con = sqlite3.connect(arq)
    ops = [r[0] for r in con.execute("SELECT operacao FROM auditoria ORDER BY id")]
    con.close()
    q.fechar()
    assert ops == ["criar"]


def test_erro_dentro_da_transacao_desfaz(pg):
    pid = _manual(pg)
    with pytest.raises(EstadoInvalido):
        pg.aceitar(pid, projeto=P, agente="claude", sessao="fantasma")
    assert pg.obter(pid)["estado"] == "aberta"
    # a conexao continua utilizavel depois do rollback
    assert _manual(pg, t=2) is not None


def test_pacote_so_importa_a_biblioteca_padrao_e_duas_folhas():
    fora = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom):
                if (no.level >= 2 and no.module not in ("texto_bytes", "cerca_nao_confiavel")) or (no.module or "").startswith("delegation_core"):
                    fora.append(f"{arq.name}: {'.' * no.level}{no.module}")
    assert fora == []
