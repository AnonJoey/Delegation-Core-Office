"""`src/cmds/git/git_cmd.rs` do RTK: `git status`, `add`, `fetch`, `diff`, `log` e `show` compactos.

Portados os seis subcomandos mais usados (5,8% dos comandos do agente). `commit`,
`checkout`, `push`, `pull`, `branch`, `stash` e `worktree` seguem sem porte: o
`shell` deixa esses comandos passarem como estao.

Diferente de mypy, pytest e ruff, o git do RTK nao filtra a saida de um comando:
ele roda varios (`status` roda o simples e o porcelain, `diff` roda o diff e o
`--stat`, `show` roda tres vezes) e monta o resultado. Por isso o modulo exporta
`rodar(args, amb)`, o `run_*` do RTK, e nao so `filtrar`. O `filtrar` e para o
`filter_output`, quando o agente ja rodou o comando e so resta a saida.

Diferencas deliberadas:
- `restore_double_dash` nao e portado: o RTK precisa dele porque o clap engole o
  `--`; aqui os argumentos vem do proprio comando e o `--` ja esta la.
- As dicas que citam o proprio RTK (`rtk git diff --no-compact`, `rtk proxy git
  show ...`) citam o delegation-core (`base.pelo_filtro`, `base.sem_filtro`).
- A linha de status limpo do RTK leva um travessao (U+2014) entre `clean` e
  `nothing to commit`; aqui ele e escrito como escape, para o arquivo nao carregar
  o caractere, e a saida e a mesma.
- O Windows nao e tratado (o RTK decodifica a pagina de codigo do console).
"""

from __future__ import annotations

from .. import arg_tokenizer as at
from ..arg_tokenizer import DASH_DASH, LONG, POSITIONAL, SHORT, Token, ValueSpec
from ..ambiente import Ambiente
from .. import base
from ..base import never_worse, strip_ansi, trim, linhas, sem_filtro
from .compact_diff import compact_diff

COMANDOS = ("git",)
SUBCOMANDOS = ("status", "add", "fetch", "diff", "log", "show")
DEFAULT_LOG_LIMIT = 10
DEFAULT_LOG_LIMIT_ARG = "-10"
MAX_BLOB_BYTES = 8192
DIFF_MAX_LINES = 500


# ── opcoes globais do git, na ordem em que o RTK as monta ────────────────────

_GLOBAIS_SIMPLES = ("--no-pager", "--no-optional-locks", "--bare", "--literal-pathspecs")


def analisar(args: list[str]) -> tuple[list[str], str, list[str]] | None:
    """(opcoes globais na ordem do RTK, subcomando, argumentos) ou None se nao for com este modulo.

    O clap do RTK aceita as opcoes globais em qualquer ordem antes do subcomando e as
    remonta sempre como -C..., -c..., --git-dir, --work-tree, --no-pager, --no-optional-locks,
    --bare, --literal-pathspecs. Opcao global que ele nao conhece (`--paginate`) faz o `rtk git`
    falhar; aqui o comando fica com o git, sem filtro.
    """
    diretorios: list[str] = []
    configs: list[str] = []
    git_dir = work_tree = None
    marcas = {k: False for k in _GLOBAIS_SIMPLES}
    i = 0
    while i < len(args):
        a = args[i]
        if not a.startswith("-"):
            break
        if a in marcas:
            marcas[a] = True
        elif a in ("-C", "-c"):
            if i + 1 >= len(args):
                return None
            (diretorios if a == "-C" else configs).append(args[i + 1])
            i += 1
        elif a[:2] in ("-C", "-c") and not a.startswith("--"):
            (diretorios if a[1] == "C" else configs).append(a[2:])
        elif a.startswith(("--git-dir", "--work-tree")):
            nome, sep, valor = a.partition("=")
            if nome not in ("--git-dir", "--work-tree"):
                return None
            if not sep:
                if i + 1 >= len(args):
                    return None
                valor = args[i + 1]
                i += 1
            if nome == "--git-dir":
                if git_dir is not None:
                    return None
                git_dir = valor
            else:
                if work_tree is not None:
                    return None
                work_tree = valor
        else:
            return None
        i += 1
    if i >= len(args) or args[i] not in SUBCOMANDOS:
        return None
    globais: list[str] = []
    for d in diretorios:
        globais += ["-C", d]
    for c in configs:
        globais += ["-c", c]
    if git_dir is not None:
        globais += ["--git-dir", git_dir]
    if work_tree is not None:
        globais += ["--work-tree", work_tree]
    globais += [k for k in _GLOBAIS_SIMPLES if marcas[k]]
    return globais, args[i], args[i + 1:]


def executa(args: list[str]) -> bool:
    """O `shell` deixa este modulo rodar o comando (`git [opcoes] status|add|...`)."""
    return analisar(args) is not None


def _git(g: list[str], *resto: str) -> list[str]:
    return ["git", *g, *resto]


# ── gramatica de flags de git log, diff e show ───────────────────────────────

_LONGAS_COM_VALOR = frozenset("""
after anchored author before color-moved-ws committer date decorate-refs decorate-refs-exclude
diff-algorithm diff-filter diff-merges dst-prefix encoding exclude find-object glob grep
grep-reflog ignore-matching-lines inter-hunk-context line-prefix max-age max-count max-depth
min-age output output-indicator-context output-indicator-new output-indicator-old rotate-to
since since-as-filter skip skip-to src-prefix stat-count stat-graph-width stat-name-width
stat-width until word-diff-regex ws-error-highlight
""".split())


def log_takes_value(tipo: str, nome: str) -> ValueSpec | None:
    """`git log`: `-M -U -C -B` levem um numero preso e nunca um token; `-n` e `-l` so solitarios."""
    if tipo == LONG:
        return ValueSpec.value() if nome in _LONGAS_COM_VALOR else None
    if tipo == SHORT:
        if nome in ("B", "C", "M", "U"):
            return ValueSpec.attached()
        if nome in ("G", "I", "L", "O", "S"):
            return ValueSpec.value()
        if nome in ("l", "n"):
            return ValueSpec.solo()
    return None


def diff_takes_value(tipo: str, nome: str) -> ValueSpec | None:
    """`git diff` e `show`: igual, mas `-l` (limite de renomeacao) tambem se agrupa (`-wl 100`)."""
    if tipo == LONG:
        return ValueSpec.value() if nome in _LONGAS_COM_VALOR else None
    if tipo == SHORT:
        if nome in ("B", "C", "M", "U"):
            return ValueSpec.attached()
        if nome in ("G", "I", "L", "O", "S", "l"):
            return ValueSpec.value()
        if nome == "n":
            return ValueSpec.solo()
    return None


def tokenize_git_diff_args(args: list[str]) -> list[Token]:
    return at.tokenize_grammar(args, diff_takes_value)


def tokenize_git_log_args(args: list[str]) -> list[Token]:
    return at.tokenize_grammar(args, log_takes_value)


def _long(t: Token, *nomes: str) -> bool:
    return t.kind == LONG and t.text in nomes


def _short(t: Token, *nomes: str) -> bool:
    return t.kind == SHORT and t.text in nomes


# ── formato de saida que o RTK nao sabe compactar ────────────────────────────

def log_wants_raw_shape(token: Token, tokens: list[Token]) -> bool:
    """Flag que muda a *forma* da saida do git log (patch, diffstat, lista de nomes)."""
    if _long(token, "diff-merges"):
        return token.value(tokens) not in (None, "none", "off")
    if token.kind == LONG:
        return token.text in {
            "binary", "cc", "remerge-diff", "compact-summary", "dirstat", "line-prefix", "name-only",
            "name-status", "numstat", "patch", "patch-with-raw", "patch-with-stat", "raw", "shortstat",
            "stat", "summary", "unified"}
    if token.kind == SHORT:
        return token.text in ("U", "c", "p", "u")
    return False


def show_wants_raw_shape(token: Token, tokens: list[Token]) -> bool:
    if _long(token, "check", "exit-code"):
        return True
    if _long(token, "diff-merges"):
        return token.value(tokens) in ("c", "cc", "combined", "dense-combined")
    # `-c` e a forma combinada de `--cc`, nao um pedido de patch; as outras curtas e
    # `--patch`/`--unified` so repetem o que `diff` e `show` ja imprimem.
    if (token.kind == SHORT and token.text != "c") or _long(token, "patch", "unified"):
        return False
    return log_wants_raw_shape(token, tokens)


def diff_wants_raw_shape(token: Token, tokens: list[Token]) -> bool:
    return _long(token, "quiet") or show_wants_raw_shape(token, tokens)


def suppresses_diff_body(token: Token) -> bool:
    return _long(token, "no-patch", "quiet") or _short(token, "s")


def hard_suppresses_diff_body(token: Token) -> bool:
    return _long(token, "no-patch") or _short(token, "s")


def requests_patch_output(token: Token) -> bool:
    if token.kind == LONG:
        return token.text in ("patch", "patch-with-stat", "patch-with-raw", "unified", "function-context")
    if token.kind == SHORT:
        return token.text in ("p", "u", "U", "W")
    return False


def body_is_suppressed(tokens: list[Token]) -> bool:
    """`-s` e `--no-patch` perdem para um `-p`/`-U<n>` posterior e ganham de um anterior;
    `--quiet` so suprime se nada mais pediu saida."""
    suprimido = False
    for t in tokens:
        if hard_suppresses_diff_body(t):
            suprimido = True
        elif requests_patch_output(t):
            suprimido = False
    return suprimido or (any(_long(t, "quiet") for t in tokens)
                         and not any(requests_patch_output(t) for t in tokens))


def emits_word_diff(tokens: list[Token]) -> bool:
    """Um word diff nao tem coluna de marcador, e o `compact_diff` nao sabe le-lo."""
    palavras = False
    for t in tokens:
        if t.kind != LONG:
            continue
        if t.text == "word-diff":
            palavras = t.attached != "none"
        elif t.text in ("color-words", "word-diff-regex"):
            palavras = True
    return palavras


def show_wants_format(tokens: list[Token]) -> bool:
    return any(_long(t, "format", "pretty") for t in tokens)


def args_without_oneline(args: list[str], tokens: list[Token]) -> list[str]:
    """`args` sem `--oneline`, pelo indice do proprio token (um pathspec depois de `--` fica)."""
    cortados = {t.source_index for t in tokens if _long(t, "oneline")}
    return [a for i, a in enumerate(args) if i not in cortados]


def args_without_patch_shape(args: list[str], tokens: list[Token]) -> list[str]:
    """`args` sem as flags que pedem patch; num grupo (`-pl 100`) so saem as letras do patch."""
    saida: list[str] = []
    for indice, arg in enumerate(args):
        donos = [t for t in tokens if t.source_index == indice and t.kind != POSITIONAL]
        if not donos or not any(requests_patch_output(t) for t in donos):
            saida.append(arg)
            continue
        mantidos = [t for t in donos if t.kind == SHORT and not requests_patch_output(t)]
        if not mantidos:
            continue
        refeito = "-" + "".join(t.text for t in mantidos)
        if mantidos[-1].attached is not None:
            refeito += mantidos[-1].attached
        saida.append(refeito)
    return saida


# ── git status ───────────────────────────────────────────────────────────────

_REBASE_INDICATORS = (
    "rebase in progress", "You are currently rebasing", "You are currently editing",
    "You are currently splitting", "Last command done", "Next command to do", "No commands remaining")
_STOPPERS = (
    "Changes to be committed:", "Changes not staged for commit:", "Untracked files:", "Unmerged paths:",
    "no changes added to commit", "nothing to commit", "nothing added to commit")


def uses_compact_status_path(args: list[str]) -> bool:
    tokens = at.tokenize(args)
    if not tokens:
        return True
    viu_branch = viu_flag = False
    for t in tokens:
        if t.kind == DASH_DASH:
            continue
        if _short(t, "b") or _long(t, "branch"):
            viu_branch = viu_flag = True
        elif _short(t, "s") or _long(t, "short"):
            viu_flag = True
        else:
            return False
    return viu_branch or not viu_flag


def format_status_output(porcelain: str, detached: str | None = None) -> str:
    ls = [l for l in linhas(porcelain) if trim(l)]
    if not ls:
        return "Clean working tree"
    saida: list[str] = []
    if ls[0].startswith("##"):
        branch = ls[0]
        while branch.startswith("## "):
            branch = branch[3:]
        saida.append(f"* {detached if detached is not None else branch}")
    else:
        saida.append(ls[0])
    saida += ls[1:]
    if len(ls) == 1 and ls[0].startswith("##"):
        saida.append("clean \u2014 nothing to commit")
    return "\n".join(saida)


def _detect_status_state(linha: str) -> str | None:
    if "All conflicts fixed but you are still merging" in linha:
        return "merge in progress. no conflicts"
    if "You have unmerged paths" in linha:
        return "merge in progress. unresolved conflicts"
    if "You are currently cherry-picking" in linha:
        return "cherry-pick in progress"
    if "You are currently reverting" in linha:
        return "revert in progress"
    if "You are currently bisecting" in linha:
        return "bisect in progress"
    if "You are in the middle of an am session" in linha:
        return "am session in progress"
    if "You are in a sparse checkout" in linha:
        return "sparse checkout enabled"
    if any(i in linha for i in _REBASE_INDICATORS):
        return "rebase in progress"
    return None


def extract_state_header(bruto: str) -> str | None:
    """O `--porcelain -b` omite rebase/merge/cherry-pick em andamento; o status simples tem."""
    for linha in linhas(bruto):
        limpa = trim(linha)
        if any(limpa.startswith(s) for s in _STOPPERS):
            break
        estado = _detect_status_state(limpa)
        if estado is not None:
            return estado
    return None


def extract_detached_head(bruto: str) -> str | None:
    for linha in linhas(bruto):
        limpa = trim(linha)
        if limpa.startswith("HEAD detached "):
            return limpa
    return None


def filter_status_with_args(saida: str) -> str:
    """Filtro minimo para `git status` com argumentos do usuario: sem dicas e sem linhas vazias."""
    resultado: list[str] = []
    for linha in linhas(saida):
        limpa = trim(linha)
        if not limpa:
            continue
        if (limpa.startswith('(use "git') or limpa.startswith("(create/copy files")
                or '(use "git add' in limpa or '(use "git restore' in limpa):
            continue
        if "nothing to commit" in limpa and "working tree clean" in limpa:
            resultado.append(limpa)
            break
        resultado.append(linha)
    return "ok" if not resultado else "\n".join(resultado)


def run_status(args: list[str], g: list[str], amb: Ambiente) -> int:
    if not uses_compact_status_path(args):
        r = amb.capturar(_git(g, "status", *args))
        if not r.ok():
            if trim(r.stderr):
                amb.err(r.stderr)
            return r.codigo
        if r.stderr:
            amb.err(r.stderr)
        amb.out(never_worse(r.stdout, filter_status_with_args(r.stdout)))
        return 0

    try:
        bruto = amb.capturar(_git(g, "status", *args), env={"LC_ALL": "C"}).stdout
    except OSError:
        bruto = ""
    r = amb.capturar(_git(g, "status", "--porcelain", "-b"))
    if not r.ok():
        mensagem = "Not a git repository" if "not a git repository" in r.stderr else trim(r.stderr)
        if mensagem:
            amb.err(mensagem + "\n")
        return r.codigo
    destacado = extract_detached_head(bruto)
    formatado = format_status_output(r.stdout, destacado)
    estado = extract_state_header(bruto)
    final = f"{estado}\n{formatado}" if estado is not None else formatado
    amb.out(never_worse(bruto, final) + "\n")
    return 0


# ── git add, git fetch ───────────────────────────────────────────────────────

def run_add(args: list[str], g: list[str], amb: Ambiente) -> int:
    r = amb.capturar(_git(g, "add", *(args or ["."])))
    if not r.ok():
        amb.err("FAILED: git add\n")
        if trim(r.stderr):
            amb.err(r.stderr + "\n")
        if trim(r.stdout):
            amb.err(r.stdout + "\n")
        return r.codigo
    stat = amb.capturar(_git(g, "diff", "--cached", "--stat", "--shortstat"))
    if not trim(stat.stdout):
        compacto = ""
    else:
        ultima = linhas(stat.stdout)[-1] if linhas(stat.stdout) else ""
        curta = trim(ultima)
        compacto = f"ok {curta}" if curta else "ok"
    if compacto:
        amb.out(compacto + "\n")
    elif trim(r.stderr):
        # Nada foi preparado, mas o git explicou por que (`git add --`).
        amb.err(trim(r.stderr) + "\n")
    return 0


def run_fetch(args: list[str], g: list[str], amb: Ambiente) -> int:
    r = amb.capturar(_git(g, "fetch", *args))
    if not r.ok():
        amb.err("FAILED: git fetch\n")
        if trim(r.stderr):
            amb.err(r.stderr + "\n")
        return r.codigo
    novas = sum(1 for l in linhas(r.stderr) if "->" in l or "[new" in l)
    amb.out((f"ok fetched ({novas} new refs)" if novas > 0 else "ok fetched") + "\n")
    return 0


# ── git diff ─────────────────────────────────────────────────────────────────

def run_diff(args: list[str], g: list[str], amb: Ambiente) -> int:
    tokens = tokenize_git_diff_args(args)
    quer_stat = any(diff_wants_raw_shape(t, tokens) or suppresses_diff_body(t) for t in tokens)
    sem_compactar = {t.source_index for t in tokens if _long(t, "no-compact")}
    quer_compacto = not sem_compactar and not emits_word_diff(tokens)

    if quer_stat or not quer_compacto:
        # `--check` imprime tudo em stdout e so depois sai com 2: a saida vai antes do codigo.
        r = amb.capturar(_git(g, "diff", *[a for i, a in enumerate(args) if i not in sem_compactar]))
        amb.out(r.stdout)
        if not r.ok():
            if trim(r.stderr):
                amb.err(trim(r.stderr) + "\n")
            return r.codigo
        return 0

    # O comando do usuario roda primeiro: so ele da o veredito do git sobre o que foi digitado.
    diff = amb.capturar(_git(g, "diff", *args))
    if not diff.ok():
        if trim(diff.stderr):
            amb.err(diff.stderr)
        return diff.codigo
    stat = amb.capturar(_git(g, "diff", "--no-patch", "--stat", *args_without_patch_shape(args, tokens)))
    if diff.stdout:
        compactado = compact_diff(strip_ansi(diff.stdout), DIFF_MAX_LINES)
        impresso = f"{trim(stat.stdout)}\n\nChanges:\n{compactado}"
    else:
        impresso = trim(stat.stdout)
    bruto = f"{stat.stdout}\n{diff.stdout}"
    amb.out(never_worse(bruto, impresso) + "\n")
    return 0


# ── git show ─────────────────────────────────────────────────────────────────

def _consumes_next_token_as_value(arg: str) -> bool:
    if arg.startswith("--"):
        tipo, nome = LONG, arg[2:]
    elif arg.startswith("-"):
        tipo, nome = SHORT, arg[1:]
    else:
        return False
    spec = log_takes_value(tipo, nome)
    return spec is not None and not spec.attached_only


def _is_short_value_flag(c: str) -> bool:
    return c.isascii() and _consumes_next_token_as_value(f"-{c}")


def flag_token_consumes_next(arg: str) -> bool:
    """A flag consome o argumento seguinte como valor (inclusive em grupos: `-wG foo`)."""
    grupo = arg[1:] if arg.startswith("-") else None
    if grupo and not grupo.startswith("-"):
        for i, c in enumerate(grupo):
            if _is_short_value_flag(c):
                return i + 1 == len(grupo)
        return False
    return _consumes_next_token_as_value(arg)


def show_positionals(args: list[str]) -> list[str]:
    """Os objetos de um `git show`: o que nao e opcao nem valor de opcao, antes de `--`."""
    rev_args = args[:args.index("--")] if "--" in args else args
    posicionais: list[str] = []
    it = iter(rev_args)
    for arg in it:
        if arg.startswith("-"):
            if flag_token_consumes_next(arg):
                next(it, None)
            continue
        posicionais.append(arg)
    return posicionais


def is_blob_show_arg(arg: str) -> bool:
    """`rev:caminho` nomeia um blob. `:/texto` e pathspec magico nao sao."""
    return (not arg.startswith("-") and not arg.startswith(":/") and not arg.startswith(":(")
            and not arg.startswith(":!") and not arg.startswith(":^") and ":" in arg
            and any(c != ":" for c in arg))


def blob_candidates(args: list[str]) -> list[str]:
    return [a for a in show_positionals(args) if is_blob_show_arg(a)]


def has_content_transform_flag(args: list[str]) -> bool:
    antes = args[:args.index("--")] if "--" in args else args
    return any(a in ("--textconv", "--filters", "--ext-diff") for a in antes)


def has_trailing_pathspec(args: list[str]) -> bool:
    return "--" in args and len(args) > args.index("--") + 1


BLOB, STAT_OR_FORMAT, COMMIT_DIFF = "blob", "stat_or_format", "commit_diff"


def commit_or_stat_route(args: list[str]) -> str:
    tokens = tokenize_git_diff_args(args)
    if (any(show_wants_raw_shape(t, tokens) for t in tokens) or show_wants_format(tokens)
            or emits_word_diff(tokens)):
        return STAT_OR_FORMAT
    return COMMIT_DIFF


def show_route(args: list[str]) -> str:
    return BLOB if blob_candidates(args) else commit_or_stat_route(args)


def probe_is_blob(g: list[str], arg: str, amb: Ambiente) -> bool:
    """`git cat-file -t`: so um `blob` exato e alvo de janela."""
    r = amb.capturar(_git(g, "cat-file", "-t", arg))
    return r.ok() and trim(r.stdout) == "blob"


def blob_truncation(raw: str, budget: int) -> tuple[str, int, int] | None:
    """(inicio, linhas restantes, deslocamento do `tail`) se o blob deve ser cortado; None se passa inteiro."""
    if "\0" in raw or "�" in raw:
        return None
    b = raw.encode("utf-8")
    if len(b) <= budget:
        return None
    fim = budget
    while fim > 0 and (b[fim] & 0xC0) == 0x80:
        fim -= 1
    corte = b[:fim].rfind(b"\n")
    if corte < 0:
        return None
    inicio = b[:corte + 1].decode("utf-8")
    linhas_do_inicio = len(linhas(inicio))
    restantes = len(linhas(raw)) - linhas_do_inicio
    if restantes <= 0:
        return None
    return inicio, restantes, linhas_do_inicio + 1


def _aspas_simples(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def compact_blob_show(raw: str, blob_arg: str, g: list[str]) -> str:
    achado = blob_truncation(raw, MAX_BLOB_BYTES)
    if achado is None:
        return raw
    inicio, restantes, deslocamento = achado
    prefixo = "".join(_aspas_simples(a) + " " for a in g)
    comando = f"git {prefixo}show {_aspas_simples(blob_arg)}"
    dica = f"[see remaining: {sem_filtro(comando)} | tail -n +{deslocamento}]"
    return never_worse(raw, f"{inicio}... (+{restantes} lines) {dica}\n")


def _show_cmd(g: list[str], args: list[str], tokens: list[Token], rtk_flags: list[str],
              drop_patch_shape: bool) -> list[str]:
    enviados = args_without_patch_shape(args, tokens) if drop_patch_shape else list(args)
    return _git(g, "show", *rtk_flags, *enviados)


def run_show(args: list[str], g: list[str], amb: Ambiente) -> int:
    posicionais = show_positionals(args)
    rota = show_route(args)
    objetos: list[str] = []
    if rota == BLOB:
        objetos = [c for c in blob_candidates(args) if probe_is_blob(g, c, amb)]
        rota = BLOB if objetos else commit_or_stat_route(args)

    if rota == STAT_OR_FORMAT:
        r = amb.capturar(_git(g, "show", *args))
        # `git show --check` informa em stdout e sai com 2: a saida vai antes do codigo.
        amb.out(r.stdout)
        if not r.ok():
            if trim(r.stderr):
                amb.err(trim(r.stderr) + "\n")
            return r.codigo
        return 0

    if rota == BLOB:
        # Bytes, nao texto: `git show` de um arquivo Latin-1 nao e UTF-8.
        r = amb.capturar_bytes(_git(g, "show", *args))
        if not r.ok():
            amb.err(r.stderr.decode("utf-8", "replace"))
            return r.codigo
        if r.stderr:
            amb.err(r.stderr.decode("utf-8", "replace"))
        try:
            texto = r.stdout.decode("utf-8")
        except UnicodeDecodeError:
            amb.out_bytes(r.stdout)
            return r.codigo
        pode_janela = (len(posicionais) == 1 and len(objetos) == 1
                       and not has_content_transform_flag(args) and not has_trailing_pathspec(args))
        if pode_janela:
            amb.out(compact_blob_show(texto, objetos[0], g))
        else:
            amb.out_bytes(r.stdout)
        return 0

    tokens = tokenize_git_diff_args(args)
    bruta = amb.capturar(_git(g, "show", *args))
    if not bruta.ok():
        if trim(bruta.stderr):
            amb.err(bruta.stderr)
        return bruta.codigo
    saida_bruta = bruta.stdout

    resumo = amb.capturar(_show_cmd(g, args, tokens, ["--no-patch", "--pretty=format:%h %s (%ar) <%an>"], True))
    if not resumo.ok():
        amb.err(resumo.stderr + "\n")
        return resumo.codigo
    impresso = trim(resumo.stdout)

    if body_is_suppressed(tokens):
        amb.out(never_worse(saida_bruta, impresso) + "\n")
        return 0

    # `--oneline` sai: o `--pretty=format:` do RTK suprime o cabecalho, e o do usuario o traria de volta.
    args_stat = args_without_oneline(args, tokens)
    tokens_stat = tokenize_git_diff_args(args_stat)
    stat = amb.capturar(_show_cmd(g, args_stat, tokens_stat, ["--no-patch", "--stat", "--pretty=format:"], True))
    texto_stat = trim(stat.stdout)
    if texto_stat:
        impresso += "\n" + texto_stat

    diff = amb.capturar(_show_cmd(g, args, tokens, ["--pretty=format:"], False))
    texto_diff = trim(diff.stdout)
    if texto_diff:
        impresso += "\n" + compact_diff(strip_ansi(texto_diff), DIFF_MAX_LINES)

    amb.out(never_worse(saida_bruta, impresso) + "\n")
    return 0


# ── git log ──────────────────────────────────────────────────────────────────

def truncate_line(linha: str, largura: int) -> str:
    if len(linha) > largura:
        return linha[:largura - 3] + "..."
    return linha


def has_limit_flag(tokens: list[Token]) -> bool:
    for t in tokens:
        if t.kind == LONG and t.text == "max-count":
            return True
        if t.kind == SHORT and ((t.text == "n" and t.value(tokens) is not None) or at.is_digit_run(t.text)):
            return True
    return False


def _parse_usize(texto: str | None) -> int | None:
    from .compact_diff import _parse_usize as p
    return None if texto is None else p(texto)


def parse_limit_from_tokens(tokens: list[Token]) -> int | None:
    for t in tokens:
        if t.kind == LONG and t.text == "max-count":
            valor = t.value(tokens)
        elif t.kind == SHORT and at.is_digit_run(t.text):
            valor = t.text
        elif t.kind == SHORT and t.text == "n":
            valor = t.value(tokens)
        else:
            continue
        n = _parse_usize(valor)
        if n is not None:
            return n
    return None


def bounds_the_walk(tokens: list[Token]) -> bool:
    """Um intervalo de revisoes (`HEAD~15..HEAD`) ja limita a caminhada: o teto de 10 nao se aplica."""
    return any(t.is_free_positional() and ".." in t.text and not t.text.startswith("./")
               and not t.text.startswith("../") for t in at.before_dashdash(tokens))


def raw_log_is_capped(tokens: list[Token]) -> bool:
    return not has_limit_flag(tokens) and not bounds_the_walk(tokens)


def selects_by_diff(tokens: list[Token]) -> bool:
    for t in at.before_dashdash(tokens):
        if t.kind == LONG and t.text in ("find-object", "diff-filter", "pickaxe-regex", "pickaxe-all"):
            return True
        if t.kind == SHORT and t.text in ("S", "G"):
            return True
    return False


def user_skip(tokens: list[Token]) -> int:
    for t in reversed(tokens):
        if _long(t, "skip"):
            return _parse_usize(t.value(tokens)) or 0
    return 0


def log_probe_args(args: list[str], tokens: list[Token]) -> list[str]:
    cortados: set[int] = set()
    for t in tokens:
        if not _long(t, "pretty", "format", "oneline", "skip", "output", "exit-code"):
            continue
        cortados.add(t.source_index)
        if t.linked is not None and t.linked < len(tokens):
            cortados.add(tokens[t.linked].source_index)
    mantidos = [a for i, a in enumerate(args) if i not in cortados]
    return args_without_patch_shape(mantidos, tokenize_git_log_args(mantidos))


def is_commit_name(linha: str) -> bool:
    nome = linha.strip("\t\n\x0b\x0c\r \x85\xa0         "
                       "       　*|/\\")
    return len(nome) >= 7 and all(c in "0123456789abcdefABCDEF" for c in nome)


def walk_exceeds_limit(g: list[str], args: list[str], tokens: list[Token], limit: int,
                       amb: Ambiente) -> bool | None:
    """Ha mais commits do que o teto mostra? Pergunta ao git pelo commit logo depois do teto."""
    cmd = _git(g, "log", "--pretty=format:%H")
    contando = selects_by_diff(tokens)
    if contando:
        cmd.append(f"--max-count={limit + 1}")
    else:
        cmd += ["--max-count=1", f"--skip={limit + user_skip(tokens)}"]
    cmd += log_probe_args(args, tokens)
    try:
        r = amb.capturar(cmd)
    except OSError:
        return None
    if not r.ok():
        return None
    if not contando:
        return bool(trim(r.stdout))
    return sum(1 for l in linhas(strip_ansi(r.stdout)) if is_commit_name(l)) > limit


def filter_log_output(saida: str, limit: int, user_set_limit: bool, user_format: bool) -> str:
    largura = 120 if user_set_limit else 80
    if user_format:
        todas = linhas(saida)
        maximo = len(todas) if user_set_limit else limit
        return "\n".join(truncate_line(l, largura) for l in todas[:maximo])

    commits = saida.split("---END---")
    max_commits = len(commits) if user_set_limit else limit
    resultado: list[str] = []
    for bloco in commits[:max_commits]:
        bloco = trim(bloco)
        if not bloco:
            continue
        ls = linhas(bloco)
        if not ls:
            continue
        cabecalho = truncate_line(trim(ls[0]), largura)
        corpo = [trim(l) for l in ls[1:]]
        corpo = [l for l in corpo if l and not l.startswith("Signed-off-by:") and not l.startswith("Co-authored-by:")]
        omitidas = max(0, len(corpo) - 3)
        mostradas = corpo[:3]
        if not mostradas:
            resultado.append(cabecalho)
        else:
            entrada = cabecalho
            for linha in mostradas:
                entrada += f"\n  {truncate_line(linha, largura)}"
            if omitidas > 0:
                entrada += f"\n  [+{omitidas} lines omitted]"
            resultado.append(entrada)
    return trim("\n".join(resultado))


def run_log(args: list[str], g: list[str], amb: Ambiente) -> int:
    tokens = tokenize_git_log_args(args)

    if any(log_wants_raw_shape(t, tokens) for t in tokens):
        limitado = raw_log_is_capped(tokens)
        enviados = ["log", *([DEFAULT_LOG_LIMIT_ARG] if limitado else []), *args]
        if not limitado:
            return amb.repassar(_git(g, *enviados))
        r = amb.capturar(_git(g, *enviados))
        amb.out(r.stdout)
        if trim(r.stderr):
            amb.err(r.stderr)
        # Antes de olhar o codigo: `--exit-code` faz um `git log` bem-sucedido sair com 1.
        if walk_exceeds_limit(g, args, tokens, DEFAULT_LOG_LIMIT, amb) is True:
            amb.err(f"[{base.PREFIXO}] capped at {DEFAULT_LOG_LIMIT} commits; pass -n <count> for more\n")
        return r.codigo

    cmd = _git(g, "log")
    tem_formato = any(_long(t, "format", "oneline", "pretty") for t in tokens)
    tem_limite = has_limit_flag(tokens)
    if not tem_formato:
        cmd.append("--pretty=format:%h %s (%ar) <%an>%n%b%n---END---")
    if tem_limite:
        limite = parse_limit_from_tokens(tokens)
        limite = 10 if limite is None else limite
        usuario_limitou = True
    elif tem_formato:
        cmd.append("-50")
        limite, usuario_limitou = 50, False
    else:
        cmd.append(DEFAULT_LOG_LIMIT_ARG)
        limite, usuario_limitou = 10, False

    quer_merges = False
    for t in tokens:
        if t.kind != LONG:
            continue
        if t.text in ("merges", "no-merges"):
            quer_merges = True
        elif t.text == "min-parents" and t.attached is not None:
            n = _parse_usize(t.attached)
            if n is not None and n >= 2 and n <= 0xFFFFFFFF:
                quer_merges = True
    if not quer_merges and not tem_limite:
        cmd.append("--no-merges")
    cmd += args

    r = amb.capturar(cmd)
    if not r.ok():
        amb.err(r.stderr + "\n")
        return r.codigo
    filtrado = never_worse(r.stdout, filter_log_output(r.stdout, limite, usuario_limitou, tem_formato))
    amb.out(filtrado + "\n")
    return 0


# ── entrada ──────────────────────────────────────────────────────────────────

_RUNNERS = {"status": run_status, "add": run_add, "fetch": run_fetch, "diff": run_diff,
            "log": run_log, "show": run_show}


def rodar(args: list[str], amb: Ambiente) -> int:
    """`rtk git [opcoes] <subcomando> ...` para os seis subcomandos portados."""
    achado = analisar(args)
    if achado is None:
        return amb.repassar(["git", *args])
    globais, sub, resto = achado
    try:
        return _RUNNERS[sub](resto, globais, amb)
    except OSError as e:
        amb.err(f"Error: Failed to run git {sub}: {e}\n")
        return 1


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """Para o `filter_output`: o agente ja rodou o comando, e so ha a saida (sem poder
    perguntar ao git de novo). Cada subcomando faz o que da com o texto."""
    achado = analisar(list(args))
    sub = achado[1] if achado else ""
    resto = achado[2] if achado else []
    if sub == "status":
        return filter_status_with_args(bruto)
    if sub == "fetch":
        if codigo != 0:
            return bruto
        novas = sum(1 for l in linhas(bruto) if "->" in l or "[new" in l)
        return f"ok fetched ({novas} new refs)" if novas > 0 else "ok fetched"
    if sub == "diff":
        return compact_diff(strip_ansi(bruto), DIFF_MAX_LINES) if bruto else "No diff"
    if sub == "log" and any(_long(t, "format", "oneline", "pretty") for t in tokenize_git_log_args(resto)):
        tokens = tokenize_git_log_args(resto)
        usuario = has_limit_flag(tokens)
        return filter_log_output(bruto, parse_limit_from_tokens(tokens) or 50, usuario, True)
    return bruto


def trata(args: list[str]) -> bool:
    """`modulos.modulo_para`: a saida de que comandos este modulo sabe reduzir sem rodar o git."""
    achado = analisar(list(args))
    if achado is None:
        return False
    _, sub, resto = achado
    if sub in ("status", "fetch"):
        return True
    if sub == "diff":
        tokens = tokenize_git_diff_args(resto)
        return not any(diff_wants_raw_shape(t, tokens) or suppresses_diff_body(t) or _long(t, "no-compact")
                       for t in tokens) and not emits_word_diff(tokens)
    if sub == "log":
        return any(_long(t, "format", "oneline", "pretty") for t in tokenize_git_log_args(resto))
    return False
