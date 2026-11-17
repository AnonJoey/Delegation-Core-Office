"""`src/cmds/git/gh_cmd.rs` do RTK: `gh pr` compacto.

Portado `gh pr` (list, view, checks, status, create, merge, diff, comment, edit),
o subcomando mais usado do `gh`. `issue`, `run`, `repo` e `api` seguem sem porte:
o `shell` deixa esses comandos passarem como estao.

`list`, `view` e `status` pedem JSON ao `gh` (`--json campos`) e montam o resumo
a partir dele, por isso so `rodar` os faz; `checks`, `diff`, `create`, `comment` e
`edit` filtram o texto que o `gh` ja imprime, e o `filtrar` (para o
`filter_output`) cobre esses.
"""

from __future__ import annotations

import json
import re

from ..ambiente import Ambiente
from ..base import _ESPACOS, force_tee_tail_hint, linhas, trim, truncate
from ..runner import run_filtered
from .compact_diff import compact_diff

COMANDOS = ("gh",)
CAP_LIST = 20
SUBCOMANDOS_PR = ("list", "view", "checks", "status", "create", "merge", "diff", "comment", "edit")

# `\s` do crate regex e Unicode (White_Space); o `\s` do Python inclui mais quatro caracteres.
_S = "[" + re.escape(_ESPACOS) + "]"
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BADGE_LINE = re.compile(rf"^{_S}*\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\){_S}*$", re.M)
_IMAGE_ONLY_LINE = re.compile(rf"^{_S}*!\[[^\]]*\]\([^)]*\){_S}*$", re.M)
_HORIZONTAL_RULE = re.compile(rf"^{_S}*(?:---+|\*\*\*+|___+){_S}*$", re.M)
_MULTI_BLANK = re.compile(r"\n{3,}")


# ── valores JSON como o serde_json os le (campo ausente = nulo) ──────────────

def _get(valor, *caminho):
    for chave in caminho:
        valor = valor.get(chave) if isinstance(valor, dict) else None
    return valor


def _str(valor, padrao: str) -> str:
    return valor if isinstance(valor, str) else padrao


def _i64(valor, padrao: int = 0) -> int:
    ok = isinstance(valor, int) and not isinstance(valor, bool) and -(2**63) <= valor < 2**63
    return valor if ok else padrao


# ── corpo em markdown ────────────────────────────────────────────────────────

def filter_markdown_segment(texto: str) -> str:
    s = _HTML_COMMENT.sub("", texto)
    s = _BADGE_LINE.sub("", s)
    s = _IMAGE_ONLY_LINE.sub("", s)
    s = _HORIZONTAL_RULE.sub("", s)
    return _MULTI_BLANK.sub("\n\n", s)


def filter_markdown_body(corpo: str) -> str:
    """Tira comentario HTML, selo, imagem solta, regua e linhas em branco demais; blocos de codigo ficam."""
    if not corpo:
        return ""
    resultado: list[str] = []
    resto = corpo
    while True:
        pos = resto.find("```")
        if pos < 0:
            pos = resto.find("~~~")
        if pos < 0:
            resultado.append(filter_markdown_segment(resto))
            break
        cerca = "```" if resto[pos:].startswith("```") else "~~~"
        resultado.append(filter_markdown_segment(resto[:pos]))
        depois_de_abrir = pos + len(cerca)
        nl = resto.find("\n", depois_de_abrir)
        inicio_codigo = nl + 1 if nl >= 0 else len(resto)
        fecha = resto.find(cerca, inicio_codigo)
        if fecha < 0:
            resultado.append(resto[pos:])
            resto = ""
            continue
        fim = fecha + len(cerca)
        resultado.append(resto[pos:fim])
        nl = resto.find("\n", fim)
        depois_de_fechar = nl + 1 if nl >= 0 else len(resto)
        resultado.append(resto[fim:depois_de_fechar])
        resto = resto[depois_de_fechar:]
    return trim("".join(resultado))


# ── argumentos ───────────────────────────────────────────────────────────────

_FLAGS_COM_VALOR = ("-R", "--repo", "-q", "--jq", "-t", "--template", "--job", "--attempt")


def has_json_flag(args: list[str]) -> bool:
    return "--json" in args


def extract_identifier_and_extra_args(args: list[str]) -> tuple[str, list[str]] | None:
    """O identificador (numero ou URL) e o resto, em `view 123 -R dono/repo` ou `view -R dono/repo 123`."""
    if not args:
        return None
    identificador = None
    extra: list[str] = []
    pular = False
    for arg in args:
        if pular:
            extra.append(arg)
            pular = False
        elif arg in _FLAGS_COM_VALOR:
            extra.append(arg)
            pular = True
        elif arg.startswith("-"):
            extra.append(arg)
        elif identificador is None:
            identificador = arg
        else:
            extra.append(arg)
    return None if identificador is None else (identificador, extra)


def parse_optional_identifier(args: list[str]) -> tuple[str | None, list[str]]:
    achado = extract_identifier_and_extra_args(args)
    return (achado[0], achado[1]) if achado else (None, list(args))


# ── formatos ─────────────────────────────────────────────────────────────────

def state_icon(estado: str, ultra_compacto: bool) -> str:
    if ultra_compacto:
        return {"OPEN": "O", "MERGED": "M", "CLOSED": "C"}.get(estado, "?")
    return {"OPEN": "[open]", "MERGED": "[merged]", "CLOSED": "[closed]"}.get(estado, "[unknown]")


def format_pr_list(dados, ultra_compacto: bool = False) -> str:
    if not isinstance(dados, list):
        return ""
    if not dados:
        return "No PRs\n" if ultra_compacto else "No Pull Requests\n"
    saida = ["PRs\n" if ultra_compacto else "Pull Requests\n"]
    todas = []
    for pr in dados:
        numero = _i64(_get(pr, "number"))
        titulo = _str(_get(pr, "title"), "???")
        estado = _str(_get(pr, "state"), "???")
        autor = _str(_get(pr, "author", "login"), "???")
        todas.append(f"  {state_icon(estado, ultra_compacto)} #{numero} {truncate(titulo, 60)} ({autor})")
    for linha in todas[:CAP_LIST]:
        saida.append(f"{linha}\n")
    if len(todas) > CAP_LIST:
        saida.append(f"  … +{len(todas) - CAP_LIST} more\n")
        dica = force_tee_tail_hint("\n".join(todas), "gh-prs", CAP_LIST + 1)
        if dica:
            saida.append(f"  {dica}\n")
    return "".join(saida)


def _contagem(checks: list, valor: str) -> int:
    return sum(1 for c in checks if _get(c, "conclusion") == valor or _get(c, "state") == valor)


def format_pr_view(dados, ultra_compacto: bool = False) -> str:
    saida: list[str] = []
    numero = _i64(_get(dados, "number"))
    titulo = _str(_get(dados, "title"), "???")
    estado = _str(_get(dados, "state"), "???")
    autor = _str(_get(dados, "author", "login"), "???")
    url = _str(_get(dados, "url"), "")
    mesclavel = _str(_get(dados, "mergeable"), "UNKNOWN")

    saida.append(f"{state_icon(estado, ultra_compacto)} PR #{numero}: {titulo}\n")
    saida.append(f"  {autor}\n")
    marca = {"MERGEABLE": "[ok]", "CONFLICTING": "[x]"}.get(mesclavel, "?")
    saida.append(f"  {estado} | {marca}\n")

    reviews = _get(dados, "reviews", "nodes")
    if isinstance(reviews, list):
        aprovadas = sum(1 for r in reviews if _get(r, "state") == "APPROVED")
        mudancas = sum(1 for r in reviews if _get(r, "state") == "CHANGES_REQUESTED")
        if aprovadas > 0 or mudancas > 0:
            saida.append(f"  Reviews: {aprovadas} approved, {mudancas} changes requested\n")

    checks = _get(dados, "statusCheckRollup")
    if isinstance(checks, list):
        total = len(checks)
        passaram = _contagem(checks, "SUCCESS")
        falharam = _contagem(checks, "FAILURE")
        if ultra_compacto:
            if falharam > 0:
                saida.append(f"  [x]{passaram}/{total}  {falharam} fail\n")
            else:
                saida.append(f"  {passaram}/{total}\n")
        else:
            saida.append(f"  Checks: {passaram}/{total} passed\n")
            if falharam > 0:
                saida.append(f"  [warn] {falharam} checks failed\n")

    saida.append(f"  {url}\n")

    corpo = _get(dados, "body")
    if isinstance(corpo, str) and corpo:
        filtrado = filter_markdown_body(corpo)
        if filtrado:
            saida.append("\n")
            for linha in linhas(filtrado):
                saida.append(f"  {linha}\n")
        else:
            saida.append("\n  (body contained only badges/images/comments)\n")
    return "".join(saida)


PASSED, FAILED, PENDING, OTHER = "passed", "failed", "pending", "other"


def parse_pr_check_line(linha: str):
    campos = linha.split("\t")
    if len(campos) < 2:
        return None
    nome = trim(campos[0])
    status = trim(campos[1])
    if status == "pass":
        estado = PASSED
    elif status == "fail":
        estado = FAILED
    elif status in ("pending", "*"):
        estado = PENDING
    else:
        estado = OTHER
    link = trim(campos[3]) if len(campos) > 3 else ""
    return (nome, link, estado) if nome else None


def format_pr_checks(stdout: str) -> str:
    """Uma linha por check; no `--watch` cada rodada acrescenta a tabela, e vale a ultima de cada um."""
    checks: list[list] = []
    for linha in linhas(stdout):
        achado = parse_pr_check_line(linha)
        if achado is None:
            continue
        nome, link, estado = achado
        for c in checks:
            if c[0] == nome and c[1] == link:
                c[2], c[3] = estado, trim(linha)
                break
        else:
            checks.append([nome, link, estado, trim(linha)])
    passaram = sum(1 for c in checks if c[2] == PASSED)
    falharam = sum(1 for c in checks if c[2] == FAILED)
    pendentes = sum(1 for c in checks if c[2] == PENDING)
    outros = sum(1 for c in checks if c[2] == OTHER)
    saida = ["CI Checks Summary:\n", f"  [ok] Passed: {passaram}\n", f"  [FAIL] Failed: {falharam}\n"]
    if pendentes > 0:
        saida.append(f"  [pending] Pending: {pendentes}\n")
    if outros > 0:
        saida.append(f"  [skip] Skipped/cancelled: {outros}\n")
    if falharam > 0:
        saida.append("\n  Failed checks:\n")
        for c in checks:
            if c[2] == FAILED:
                saida.append(f"    {c[3]}\n")
    return "".join(saida)


def format_pr_status_entry(pr) -> str:
    if pr is None:
        return ""
    numero = _i64(_get(pr, "number"))
    titulo = _str(_get(pr, "title"), "???")
    reviews = _str(_get(pr, "reviewDecision"), "PENDING")
    saida = f"  #{numero} {truncate(titulo, 50)} [{reviews}]"
    checks = _get(pr, "statusCheckRollup")
    if isinstance(checks, list) and checks:
        saida += f" checks {_contagem(checks, 'SUCCESS')}/{len(checks)}"
        falharam = _contagem(checks, "FAILURE")
        if falharam > 0:
            saida += f" fail {falharam}"
    return saida + "\n"


def format_pr_status(dados) -> str:
    saida = ""
    atual = _get(dados, "currentBranch")
    if atual is not None:
        entrada = format_pr_status_entry(atual)
        if entrada:
            saida += "Current Branch\n" + entrada + "\n"
    criadas = _get(dados, "createdBy")
    if isinstance(criadas, list):
        saida += f"Your PRs ({len(criadas)}):\n"
        for pr in criadas[:5]:
            saida += format_pr_status_entry(pr)
    return saida


def ok_confirmation(acao: str, detalhe: str) -> str:
    return f"ok {acao}" if not detalhe else f"ok {acao} {detalhe}"


def _confirmacao_de_criacao(stdout: str) -> str:
    url = trim(stdout)
    numero = url.rsplit("/", 1)[-1]
    detalhe = f"#{numero} {url}" if numero and numero.isascii() and numero.isdigit() else url
    return ok_confirmation("created", detalhe)


def _numero_do_pr(args: list[str]) -> str:
    for a in args[1:]:
        if not a.startswith("-"):
            return f"#{a}"
    return ""


def has_non_diff_format_flag(args: list[str]) -> bool:
    return any(a in ("--name-only", "--name-status", "--stat", "--numstat", "--shortstat", "--patch")
               for a in args)


def _filtro_de_diff(bruto: str) -> str:
    return "No diff" if not trim(bruto) else compact_diff(bruto, 500)


# ── execucao ─────────────────────────────────────────────────────────────────

def _json_ou_texto(formatar):
    def filtro(stdout: str) -> str:
        try:
            dados = json.loads(stdout)
        except ValueError:
            return stdout
        return formatar(dados)
    return filtro


def _passthrough(amb: Ambiente, *args: str) -> int:
    return amb.repassar(["gh", *args])


def run_pr(args: list[str], amb: Ambiente) -> int:
    if not args:
        return _passthrough(amb, "pr")
    sub, resto = args[0], args[1:]
    if sub == "list":
        return run_filtered(amb, ["gh", "pr", "list", "--json", "number,title,state,author,updatedAt", *resto],
                            "gh", _json_ou_texto(format_pr_list), stdout_only=True,
                            early_exit_on_failure=True, no_trailing_newline=True)
    if sub == "view":
        pr, extra = parse_optional_identifier(resto)
        if any(a in ("--json", "--jq", "--web", "--comments") for a in extra):
            return _passthrough(amb, "pr", "view", *([pr] if pr else []), *extra)
        cmd = ["gh", "pr", "view", *([pr] if pr else []), "--json",
               "number,title,state,author,body,url,mergeable,reviews,statusCheckRollup", *extra]
        return run_filtered(amb, cmd, "gh", _json_ou_texto(format_pr_view), stdout_only=True,
                            early_exit_on_failure=True, no_trailing_newline=True)
    if sub == "checks":
        pr, extra = parse_optional_identifier(resto)
        return run_filtered(amb, ["gh", "pr", "checks", *([pr] if pr else []), *extra], "gh",
                            format_pr_checks, stdout_only=True, no_trailing_newline=True)
    if sub == "status":
        if any(a in ("--help", "-h", "--web", "--jq", "--template") for a in resto):
            return _passthrough(amb, "pr", "status", *resto)
        return run_filtered(amb, ["gh", "pr", "status", "--json", "number,title,reviewDecision,statusCheckRollup", *resto],
                            "gh", _json_ou_texto(format_pr_status), stdout_only=True,
                            early_exit_on_failure=True, no_trailing_newline=True)
    if sub == "create":
        return run_filtered(amb, ["gh", "pr", "create", *resto], "gh", _confirmacao_de_criacao,
                            stdout_only=True, early_exit_on_failure=True)
    if sub == "merge":
        # Acao destrutiva: a saida real, sem filtro.
        return _passthrough(amb, "pr", "merge", *resto)
    if sub == "diff":
        sem_compactar = "--no-compact" in resto
        do_gh = [a for a in resto if a != "--no-compact"]
        if sem_compactar or has_non_diff_format_flag(do_gh):
            return _passthrough(amb, "pr", "diff", *do_gh)
        return run_filtered(amb, ["gh", "pr", "diff", *do_gh], "gh", _filtro_de_diff,
                            stdout_only=True, early_exit_on_failure=True)
    if sub in ("comment", "edit"):
        acao = "commented" if sub == "comment" else "edited"
        numero = _numero_do_pr(args)
        return run_filtered(amb, ["gh", "pr", *args], "gh", lambda _s: ok_confirmation(acao, numero),
                            stdout_only=True, early_exit_on_failure=True)
    return _passthrough(amb, "pr", *args)


def executa(args: list[str]) -> bool:
    return len(args) >= 2 and args[0] == "pr" and args[1] in SUBCOMANDOS_PR and not has_json_flag(args)


def rodar(args: list[str], amb: Ambiente) -> int:
    """`rtk gh pr ...`: `--json` do usuario e tudo que nao e `pr` passam sem filtro."""
    if has_json_flag(args) or not args or args[0] != "pr":
        return _passthrough(amb, *args)
    try:
        return run_pr(args[1:], amb)
    except OSError as e:
        amb.err(f"Error: Failed to run gh: {e}\n")
        return 1


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """Para o `filter_output`: o texto que o `gh` ja imprimiu (checks, diff, create, comment, edit)."""
    args = list(args)
    sub = args[1] if len(args) > 1 else ""
    if sub == "checks":
        return format_pr_checks(bruto)
    if codigo != 0:
        return bruto
    if sub == "diff":
        return _filtro_de_diff(bruto)
    if sub == "create":
        return _confirmacao_de_criacao(bruto)
    if sub in ("comment", "edit"):
        return ok_confirmation("commented" if sub == "comment" else "edited", _numero_do_pr(args[1:]))
    return bruto


def trata(args: list[str]) -> bool:
    return executa(list(args)) and args[1] in ("checks", "diff", "create", "comment", "edit")
