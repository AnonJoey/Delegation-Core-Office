"""Testes do porte de `gh_cmd.rs` do RTK (`gh pr`), com um `gh` falso no PATH.

A paridade byte a byte com o binario do RTK esta em `scripts/paridade_rtk_gh.py`.
"""

import json
import stat
import sys

import pytest

from delegation_core.filtros_saida import modulos
from delegation_core.filtros_saida.modulos.ambiente import Ambiente, por_linhas
from delegation_core.filtros_saida.modulos.git import gh


def test_extract_identifier_and_extra_args():
    f = gh.extract_identifier_and_extra_args
    assert f(["123"]) == ("123", [])
    assert f(["123", "-R", "dono/repo"]) == ("123", ["-R", "dono/repo"])
    assert f(["-R", "dono/repo", "123"]) == ("123", ["-R", "dono/repo"])
    assert f(["--jq", ".x", "7", "extra"]) == ("7", ["--jq", ".x", "extra"])
    assert f(["--web"]) is None and f([]) is None
    assert gh.parse_optional_identifier(["--web"]) == (None, ["--web"])


def test_state_icon():
    assert gh.state_icon("OPEN", False) == "[open]" and gh.state_icon("MERGED", True) == "M"
    assert gh.state_icon("X", False) == "[unknown]" and gh.state_icon("X", True) == "?"


def test_format_pr_list():
    dados = [{"number": 7, "title": "x" * 80, "state": "OPEN", "author": {"login": "ana"}},
             {"number": 8, "title": "t", "state": "MERGED", "author": None},
             {"title": "sem numero"}]
    r = gh.format_pr_list(dados)
    ls = r.split("\n")
    assert ls[0] == "Pull Requests"
    assert ls[1] == f"  [open] #7 {'x' * 57}... (ana)"
    assert ls[2] == "  [merged] #8 t (???)"
    assert ls[3] == "  [unknown] #0 sem numero (???)"
    assert gh.format_pr_list([]) == "No Pull Requests\n" and gh.format_pr_list([], True) == "No PRs\n"
    assert gh.format_pr_list({"nao": "lista"}) == ""


def test_format_pr_list_corta_em_vinte(monkeypatch):
    dicas = []
    monkeypatch.setattr(gh, "force_tee_tail_hint", lambda c, slug, off: dicas.append((c.count("\n") + 1, slug, off)) or "[+5 hidden: x]")
    dados = [{"number": i, "title": f"t{i}", "state": "OPEN", "author": {"login": "a"}} for i in range(25)]
    r = gh.format_pr_list(dados)
    assert r.count("\n  [open] #") == 20 - 1 + 1 or r.count("#") == 20
    assert "  … +5 more\n  [+5 hidden: x]\n" in r
    assert dicas == [(25, "gh-prs", 21)]


def test_format_pr_view():
    dados = {"number": 12, "title": "Titulo", "state": "OPEN", "author": {"login": "ana"}, "url": "https://g/p/12",
             "mergeable": "CONFLICTING",
             "reviews": {"nodes": [{"state": "APPROVED"}, {"state": "CHANGES_REQUESTED"}, {"state": "COMMENTED"}]},
             "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"state": "FAILURE"}, {"conclusion": None}],
             "body": "<!-- nota -->\n[![b](http://a)](http://b)\n\nTexto\n\n\n\nfim\n```\n<!-- fica -->\n```\n"}
    assert gh.format_pr_view(dados) == (
        "[open] PR #12: Titulo\n  ana\n  OPEN | [x]\n  Reviews: 1 approved, 1 changes requested\n"
        "  Checks: 1/3 passed\n  [warn] 1 checks failed\n  https://g/p/12\n\n  Texto\n  \n  fim\n  ```\n  <!-- fica -->\n  ```\n")
    assert gh.format_pr_view(dados, True).split("\n")[0] == "O PR #12: Titulo"
    assert "  [x]1/3  1 fail\n" in gh.format_pr_view(dados, True)
    so_badge = dict(dados, body="[![b](http://a)](http://b)\n")
    assert gh.format_pr_view(so_badge).endswith("\n  (body contained only badges/images/comments)\n")
    vazio = gh.format_pr_view({})
    assert vazio.startswith("[unknown] PR #0: ???\n  ???\n  ??? | ?\n") and vazio.endswith("  \n")


def test_filter_markdown_body():
    f = gh.filter_markdown_body
    assert f("") == ""
    assert f("<!-- a -->\ntexto <!-- b --> fim") == "texto  fim"
    assert f("![i](x.png)\nA\n---\nB\n***\n___\nC") == "A\n\n\n\nB\n\n\n\nC".replace("\n\n\n\n", "\n\n")
    assert f("a\n\n\n\nb") == "a\n\nb"
    assert f("```\n<!-- fica -->\n![i](x)\n```") == "```\n<!-- fica -->\n![i](x)\n```"
    assert f("~~~\n---\n~~~\nresto") == "~~~\n---\n~~~\nresto"
    assert f("<!-- some -->\n```\nsem fechar\n<!-- fica -->") == "```\nsem fechar\n<!-- fica -->"


def test_format_pr_checks_conta_e_lista_as_falhas():
    saida = "\n".join(["build\tpass\t1m\thttps://x/1\t", "lint\tfail\t3s\thttps://x/2\t", "deploy\tpending\t0\thttps://x/3\t",
                       "docs\tskipping\t0\thttps://x/4\t", "", "sem tabulacao"]) + "\n"
    assert gh.format_pr_checks(saida) == (
        "CI Checks Summary:\n  [ok] Passed: 1\n  [FAIL] Failed: 1\n  [pending] Pending: 1\n  [skip] Skipped/cancelled: 1\n"
        "\n  Failed checks:\n    lint\tfail\t3s\thttps://x/2\n")   # a linha sai com trim


def test_format_pr_checks_watch_vale_a_ultima_linha_de_cada_check():
    rodada1 = "build\tpending\t0\thttps://x/1\t\nlint\tpass\t1s\thttps://x/2\t\n"
    rodada2 = "build\tfail\t5s\thttps://x/1\t\nlint\tpass\t1s\thttps://x/2\t\n"
    r = gh.format_pr_checks(rodada1 + rodada2)
    assert "[ok] Passed: 1" in r and "[FAIL] Failed: 1" in r and "Pending" not in r
    assert "    build\tfail\t5s\thttps://x/1\n" in r
    assert gh.parse_pr_check_line("so um campo") is None and gh.parse_pr_check_line("\tpass") is None
    assert gh.parse_pr_check_line("a\t*\t0") == ("a", "", gh.PENDING)


def test_format_pr_status():
    pr = {"number": 3, "title": "t" * 60, "reviewDecision": "APPROVED",
          "statusCheckRollup": [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]}
    dados = {"currentBranch": pr, "createdBy": [pr, {"number": 4, "title": "u"}] + [pr] * 6}
    r = gh.format_pr_status(dados)
    assert r.startswith(f"Current Branch\n  #3 {'t' * 47}... [APPROVED] checks 1/2 fail 1\n\nYour PRs (8):\n")
    assert r.count("\n  #") == 1 + 5                                   # a lista mostra cinco
    assert "  #4 u [PENDING]\n" in r
    assert gh.format_pr_status({"currentBranch": None, "createdBy": []}) == "Your PRs (0):\n"


def test_confirmacoes():
    assert gh._confirmacao_de_criacao("https://github.com/x/y/pull/42\n") == "ok created #42 https://github.com/x/y/pull/42"
    assert gh._confirmacao_de_criacao("https://github.com/x/y/pull/abc") == "ok created https://github.com/x/y/pull/abc"
    assert gh._confirmacao_de_criacao("") == "ok created"
    assert gh._numero_do_pr(["comment", "12", "--body", "x"]) == "#12"
    assert gh._numero_do_pr(["comment", "--body", "x"]) == "#x"       # igual ao RTK: o primeiro token sem `-`
    assert gh._numero_do_pr(["edit"]) == ""


def test_executa_so_assume_gh_pr():
    for ok in (["pr", "list"], ["pr", "diff", "--stat"], ["pr", "merge", "1"]):
        assert gh.executa(ok)
    for no in (["issue", "list"], ["pr"], ["pr", "ready"], ["pr", "list", "--json", "number"], ["api", "x"], []):
        assert not gh.executa(no)
    assert gh.trata(["pr", "checks"]) and gh.trata(["pr", "diff"]) and not gh.trata(["pr", "list"])


def test_filtrar_do_filter_output():
    assert gh.filtrar("b\tpass\t1\tu\t\n", 0, ["pr", "checks"]).startswith("CI Checks Summary:")
    assert gh.filtrar("", 0, ["pr", "diff"]) == "No diff"
    assert "+1 -1" in gh.filtrar("diff --git a/f b/f\n@@ -1 +1 @@\n-a\n+b\n", 0, ["pr", "diff"])
    assert gh.filtrar("erro", 1, ["pr", "diff"]) == "erro"
    assert gh.filtrar("https://g/x/pull/9\n", 0, ["pr", "create"]) == "ok created #9 https://g/x/pull/9"
    assert gh.filtrar("u\n", 0, ["pr", "comment", "9"]) == "ok commented #9"
    assert gh.filtrar("u\n", 0, ["pr", "edit", "9"]) == "ok edited #9"


def test_por_linhas_normaliza_como_o_run_streaming():
    assert por_linhas(b"") == "" and por_linhas(b"[]") == "[]\n" and por_linhas(b"a\r\nb\r\n") == "a\nb\n"
    assert por_linhas(b"a\n\nb") == "a\n\nb\n" and por_linhas(b"\n") == "\n"
    assert por_linhas(b"x\xe3y\n") == "x�y\n"


# ── com um gh falso ──────────────────────────────────────────────────────────

@pytest.fixture
def falso(tmp_path):
    if sys.platform == "win32":
        pytest.skip("o gh falso e um script sh; o Windows nao o executa")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    env = {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(tmp_path)}

    def instalar(stdout="", stderr="", codigo=0):
        (bindir / "out").write_bytes(stdout.encode())
        (bindir / "err").write_bytes(stderr.encode())
        exe = bindir / "gh"
        exe.write_text(f'#!/bin/sh\necho "$@" > "{bindir}/args"\ncat "{bindir}/out"\ncat "{bindir}/err" >&2\nexit {codigo}\n')
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

    def rodar(*args):
        amb = Ambiente.em_memoria(str(tmp_path), env=env)
        codigo = gh.rodar(list(args), amb)
        o, e = amb.saida_gravada()
        argv = (bindir / "args").read_text().strip() if (bindir / "args").exists() else None
        return o.decode(), e.decode(), codigo, argv

    rodar.instalar = instalar
    return rodar


def test_pr_list_pede_json_e_resume(falso):
    falso.instalar(json.dumps([{"number": 1, "title": "t", "state": "OPEN", "author": {"login": "a"}}]))
    o, e, c, argv = falso("pr", "list", "--state", "all")
    assert argv == "pr list --json number,title,state,author,updatedAt --state all"
    assert (o, e, c) == ("Pull Requests\n  [open] #1 t (a)\n", "", 0)


def test_pr_view_sem_identificador_e_com_flags_de_passagem(falso):
    falso.instalar(json.dumps({"number": 5, "title": "T", "state": "OPEN", "author": {"login": "a"}, "url": "u"}))
    o, _, c, argv = falso("pr", "view")
    assert argv.startswith("pr view --json number,title,state,author,body,url,mergeable,reviews,statusCheckRollup")
    assert o.startswith("[open] PR #5: T\n")
    _, _, _, argv = falso("pr", "view", "5", "--web")
    assert argv == "pr view 5 --web"                                # passagem: sem --json injetado


def test_json_do_usuario_passa_sem_filtro(falso):
    falso.instalar('{"title":"x"}\n')
    o, e, c, argv = falso("pr", "view", "5", "--json", "title")
    assert o == '{"title":"x"}\n' and argv == "pr view 5 --json title"


def test_falha_mostra_a_saida_original_e_o_codigo(falso):
    falso.instalar("parcial\n", "erro: x\n", 4)
    assert falso("pr", "list")[:3] == ("parcial\n", "erro: x\n", 4)


def test_json_invalido_passa_como_veio(falso):
    falso.instalar("isto nao e json\n")
    assert falso("pr", "list")[0] == "isto nao e json\n"


def test_pr_diff_compacta_ou_passa(falso):
    diff = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ -1 +1 @@\n-a\n+b\n"
    falso.instalar(diff)
    assert falso("pr", "diff", "7")[0] == "\nf\n@@ -1 +1 @@\n-a\n+b\n  +1 -1\n"
    assert falso("pr", "diff", "7", "--no-compact") [0] == diff and falso("pr", "diff", "--no-compact")[3] == "pr diff"
    assert falso("pr", "diff", "--stat")[0] == diff
    falso.instalar("")
    # "No diff" e mais longo que a saida vazia, e a guarda "nunca pior" devolve a vazia.
    assert falso("pr", "diff")[0] == "\n"


def test_pr_comment_e_create_confirmam(falso):
    falso.instalar("https://github.com/x/y/pull/9#issuecomment-1\n")
    assert falso("pr", "comment", "9", "--body", "oi")[0] == "ok commented #9\n"
    falso.instalar("https://github.com/x/y/pull/9\n")
    # A confirmacao e mais longa que a URL crua: vale a guarda "nunca pior" (e o println ganha o seu \\n).
    assert falso("pr", "create", "--title", "t")[0] == "https://github.com/x/y/pull/9\n\n"


def test_pr_merge_passa_a_saida_real(falso):
    falso.instalar("Merged!\n", "aviso\n", 0)
    assert falso("pr", "merge", "9", "--squash")[:3] == ("Merged!\n", "aviso\n", 0)


def test_stderr_longo_e_cortado_com_a_dica(falso, monkeypatch):
    monkeypatch.setattr("delegation_core.filtros_saida.modulos.runner.force_tee_hint", lambda s, r: f"[full: {r}]")
    falso.instalar("a\tpass\t1\tu\t\n", "".join(f"aviso numero {i} com algum texto para passar do minimo\n" for i in range(30)))
    o, e, c, _ = falso("pr", "checks", "9")
    assert e.startswith("... (+20 earlier stderr lines not shown)\naviso numero 20") and e.endswith("[full: gh-stderr]\n")


def test_shell_entrega_gh_pr_ao_modulo():
    assert modulos.rodavel("gh pr list")[2] == ["pr", "list"]
    assert modulos.rodavel("gh issue list") is None and modulos.rodavel("gh pr list --json number") is None
    tabela = "".join(f"job-{i}\tpass\t1m\thttps://github.com/x/y/runs/{i}\t\n" for i in range(20))
    assert modulos.aplicar("gh pr checks", tabela, 0)["output"].startswith("CI Checks Summary:")
    assert modulos.aplicar("gh pr list", "tabela", 0) is None
