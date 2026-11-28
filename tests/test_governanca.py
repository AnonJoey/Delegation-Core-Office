"""Governanca: classe destrutiva, precedencia de politica, aprovacao de uso unico e taxa."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from delegation_core import escopos
from delegation_core.governanca import Aprovacoes, LimiteDeTaxa, classe_de, politica_efetiva, validar_politicas
from delegation_core.governanca.politica import DESTRUTIVAS
from delegation_core.governanca.middleware import PoliticaMiddleware


def test_destrutivas_sao_ferramentas_de_escrita_que_existem():
    from tests.test_escopos import _ferramentas
    assert DESTRUTIVAS <= escopos.ESCRITA
    assert DESTRUTIVAS <= _ferramentas()


def test_classes():
    assert classe_de("search_vault") == "read"
    assert classe_de("write_note") == "write"
    assert classe_de("ingest_forget") == "destructive"
    assert classe_de("ferramenta_que_nao_existe") == "write"


def test_precedencia_do_mais_especifico_ao_geral():
    pol = {
        "*": {"destructive": "require_approval", "search_web": "rate_limit:5/60"},
        "codex": {"write": "block", "write_note": "allow"},
    }
    assert politica_efetiva(pol, "codex", "write_note")[0] == "allow"
    assert politica_efetiva(pol, "codex", "export_session")[0] == "block"
    assert politica_efetiva(pol, "codex", "ingest_forget")[0] == "require_approval"
    assert politica_efetiva(pol, "desktop", "search_web") == ("rate_limit:5/60", "tool_policies['*']['search_web']")
    assert politica_efetiva(pol, "desktop", "search_vault") == ("allow", "default")
    assert politica_efetiva({}, "x", "ingest_forget") == ("allow", "default")


def test_acao_invalida_e_ignorada_e_apontada():
    pol = {"*": {"write": "bloquear", "read": "rate_limit:0/60"}}
    assert politica_efetiva(pol, "x", "write_note")[0] == "allow"
    erros = validar_politicas(pol)
    assert len(erros) == 2 and "bloquear" in erros[0]
    assert validar_politicas({}) == [] and validar_politicas([1]) != []


def test_aprovacao_vale_uma_vez_e_so_para_os_mesmos_argumentos(tmp_path):
    ap = Aprovacoes(tmp_path / "a.json")
    ok, p = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/x"})
    assert not ok and p["status"] == "pending"
    ok, p2 = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/x"})
    assert not ok and p2["id"] == p["id"], "repetir a chamada nao duplica o pedido"
    assert ap.decidir(p["id"][:7], aprovar=True)["status"] == "approved"
    ok, _ = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/y"})
    assert not ok, "aprovar /x nao libera /y"
    ok, usado = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/x"})
    assert ok and usado["status"] == "used"
    ok, novo = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/x"})
    assert not ok and novo["id"] != p["id"], "a aprovacao gastou"


def test_negado_nao_libera_e_pedido_vence(tmp_path):
    agora = [datetime(2026, 10, 5, 12, 0)]
    ap = Aprovacoes(tmp_path / "a.json", validade_h=1, relogio=lambda: agora[0])
    _, p = ap.consumir_ou_pedir("c", "t", {})
    assert ap.decidir(p["id"], aprovar=False)["status"] == "denied"
    _, q = ap.consumir_ou_pedir("c", "t", {})
    assert q["id"] != p["id"]
    agora[0] += timedelta(hours=2)
    assert [x["status"] for x in ap.listar("all") if x["id"] == q["id"]] == ["expired"]
    assert ap.decidir(q["id"], aprovar=True)["status"] == "expired", "vencido nao se aprova"
    assert ap.decidir("apr_naoexiste", aprovar=True) is None


def test_previa_cobre_segredo_e_corta(tmp_path):
    ap = Aprovacoes(tmp_path / "a.json")
    _, p = ap.consumir_ou_pedir("c", "t", {"k": "sk-ant-api03-" + "A" * 90, "longo": "x" * 500})
    assert "AAAAAAAAAAAAAAAA" not in json.dumps(p)
    assert len(p["args_preview"]["longo"]) < 200


def test_taxa_em_janela_deslizante():
    t = [0.0]
    lim = LimiteDeTaxa(relogio=lambda: t[0])
    assert [lim.tentar("c", "f", 2, 10) for _ in range(2)] == [0, 0]
    assert lim.tentar("c", "f", 2, 10) == 10
    assert lim.tentar("outro", "f", 2, 10) == 0, "a janela e por cliente"
    t[0] = 10.0
    assert lim.tentar("c", "f", 2, 10) == 0


def _mw(tmp_path, politicas, cliente="codex"):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"tool_policies": politicas}))
    return PoliticaMiddleware(cfg, Aprovacoes(tmp_path / "a.json"), cliente=lambda: cliente)


def test_middleware_bloqueia_pede_e_libera(tmp_path):
    from fastmcp.exceptions import ToolError
    mw = _mw(tmp_path, {"*": {"destructive": "require_approval"}, "codex": {"write_note": "block"}})

    async def segue(_ctx):
        return "ok"

    def chama(nome, args=None):
        ctx = SimpleNamespace(message=SimpleNamespace(name=nome, arguments=args or {}))
        return asyncio.run(mw.on_call_tool(ctx, segue))

    assert chama("search_vault") == "ok"
    with pytest.raises(ToolError, match="policy_blocked"):
        chama("write_note")
    with pytest.raises(ToolError, match="approval_required") as e:
        chama("ingest_forget", {"source_path": "/a"})
    pid = str(e.value).split("Request ")[1].split(" ")[0]
    mw.aprovacoes.decidir(pid, aprovar=True)
    assert chama("ingest_forget", {"source_path": "/a"}) == "ok"
    with pytest.raises(ToolError, match="approval_required"):
        chama("ingest_forget", {"source_path": "/a"})


def test_politica_muda_sem_reiniciar(tmp_path):
    import os
    mw = _mw(tmp_path, {})
    assert mw.decidir("codex", "write_note", {}) is None
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"tool_policies": {"codex": {"write": "block"}}}))
    st = cfg.stat()
    os.utime(cfg, ns=(st.st_atime_ns, st.st_mtime_ns + 10_000_000))
    assert "policy_blocked" in mw.decidir("codex", "write_note", {})


def test_cli_policy_e_approvals(tmp_path, capsys):
    from delegation_core import config
    from delegation_core.governanca import cli
    config.Config().save()
    ns = SimpleNamespace
    assert cli.cmd_policy(ns(acao="set", client="*", key="destructive", action="require_approval")) == 0
    assert cli.cmd_policy(ns(acao="set", client="*", key="read", action="talvez")) == 1
    assert config.Config.load().tool_policies == {"*": {"destructive": "require_approval"}}
    capsys.readouterr()
    cli.cmd_policy(ns(acao="check", client="codex", tool="ingest_forget"))
    assert capsys.readouterr().out.startswith("codex -> ingest_forget: require_approval")
    cli.cmd_policy(ns(acao="check", client="codex", tool="search_vault"))
    assert "allow" in capsys.readouterr().out
    ap = cli._aprovacoes()
    _, p = ap.consumir_ou_pedir("codex", "ingest_forget", {"source_path": "/z"})
    assert cli.cmd_approvals(ns(acao="approve", id=p["id"], reason="ok")) == 0
    assert cli.cmd_approvals(ns(acao="list", status="approved")) == 0
    assert p["id"] in capsys.readouterr().out
    assert cli.cmd_policy(ns(acao="unset", client="*", key="destructive")) == 0
    assert config.Config.load().tool_policies == {}


def test_middleware_de_verdade_no_fastmcp(tmp_path):
    """Pelo Client em memoria do FastMCP, nao por chamada direta ao metodo."""
    from fastmcp import Client, FastMCP
    from fastmcp.exceptions import ToolError

    app = FastMCP("t")

    @app.tool()
    def ingest_forget(source_path: str) -> str:
        return "esquecido " + source_path

    @app.tool()
    def search_vault(query: str) -> str:
        return "achou " + query

    mw = _mw(tmp_path, {"*": {"destructive": "require_approval"}}, cliente="desktop")
    app.add_middleware(mw)

    async def roda():
        async with Client(app) as c:
            assert (await c.call_tool("search_vault", {"query": "q"})).data == "achou q"
            with pytest.raises(ToolError, match="approval_required"):
                await c.call_tool("ingest_forget", {"source_path": "/a"})
            pid = mw.aprovacoes.listar()[0]["id"]
            mw.aprovacoes.decidir(pid, aprovar=True)
            assert (await c.call_tool("ingest_forget", {"source_path": "/a"})).data == "esquecido /a"
    asyncio.run(roda())


def test_dag_run_e_destrutiva_e_anuncia_isso_ao_cliente():
    """`dag_run` executa comando de shell com a conta do daemon. Era classe `write`: a politica
    por classe nao a alcancava e a dica do protocolo dizia ao cliente que ela nao destroi nada."""
    from delegation_core.anotacoes import anotacoes_de
    assert "dag_run" in DESTRUTIVAS and classe_de("dag_run") == "destructive"
    dicas = anotacoes_de("dag_run")
    assert dicas == {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True}
    assert politica_efetiva({"*": {"destructive": "require_approval"}}, "qualquer", "dag_run")[0] == "require_approval"
    assert politica_efetiva({}, "qualquer", "dag_run")[0] == "allow"      # sem politica nada muda


def test_toda_ferramenta_que_executa_um_workflow_e_destrutiva():
    """A classe sai do que a ferramenta faz. Toda ferramenta do servidor que manda o
    `DAGRunner` executar (`execute_workflow` roda os passos com `shell=True`) tem de ser
    destrutiva. Hoje e uma so; o teste pega a proxima."""
    import ast
    import inspect
    from delegation_core import dag_runner, server
    assert "shell=True" in inspect.getsource(dag_runner.DAGRunner._run_single_step)
    arvore = ast.parse(inspect.getsource(server))
    executam = {no.name for no in ast.walk(arvore)
                if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
                and any(isinstance(x, ast.Attribute) and x.attr == "execute_workflow" for x in ast.walk(no))}
    assert executam == {"dag_run"}, executam
    assert executam <= DESTRUTIVAS
