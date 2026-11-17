"""`src/cmds/python/pytest_cmd.rs` do RTK: resumo do pytest com as falhas que importam.

O RTK roda o pytest com `--tb=short -q -rxX` quando o usuario nao passou essas
flags; aqui o comando roda como o agente escreveu, entao o filtro recebe o que
o pytest imprimiu. A saida bruta vai para o armazem de recuperacao quando o
pytest falha (`tee`), como no RTK.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..base import force_tee_hint, force_tee_tail_hint, linhas, print_with_hint, strip_ansi, trim, truncate

COMANDOS = ("pytest", "py.test")
#: O RTK filtra so o stdout do pytest (`RunOptions::stdout_only`).
SO_STDOUT = True
PYTEST_NO_TESTS = "Pytest: No tests collected"
PYTEST_EXIT_NO_TESTS = 5
CAP_WARNINGS = 10
MAX_XFAIL = CAP_WARNINGS
MAX_PYTEST_FAILURES = CAP_WARNINGS
PASSTHROUGH_MAX_CHARS = 2000


def argumentos(args: list[str]) -> list[str]:
    """O que o RTK passa ao pytest: --tb=short, -q e -rxX quando ausentes, antes dos do usuario."""
    extra = []
    if not any(a.startswith("--tb") for a in args):
        extra.append("--tb=short")
    if not any(a in ("-q", "--quiet") for a in args):
        extra.append("-q")
    if not any(a.startswith("-r") and not a.startswith("--") for a in args):
        extra.append("-rxX")
    return extra + list(args)


def parse_duration(summary: str) -> str | None:
    unwrapped = trim(trim(summary).strip("="))
    if " in " not in unwrapped:
        return None
    tail = unwrapped.rsplit(" in ", 1)[1]
    partes = tail.split()
    if not partes:
        return None
    duracao = partes[0]
    if not duracao.endswith("s"):
        return None
    numero = duracao[:-1]
    # `f64::parse` do Rust: como o float() do Python, menos o sublinhado ("1_0").
    if "_" in numero:
        return None
    try:
        float(numero)
    except ValueError:
        return None
    return duracao


def _usize(s: str) -> int | None:
    # `str::parse::<usize>`: so digitos ASCII, com '+' opcional.
    t = s[1:] if s.startswith("+") else s
    if not t or not t.isascii() or not t.isdigit():
        return None
    return int(t)


@dataclass
class PytestCounts:
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0
    duration: str | None = None


def parse_summary_line(summary: str) -> PytestCounts:
    c = PytestCounts(duration=parse_duration(summary))
    for parte in summary.split(","):
        palavras = parte.split()
        for i, w in enumerate(palavras):
            if i == 0:
                continue
            n = _usize(palavras[i - 1])
            if n is None:
                continue
            if "xpassed" in w:
                c.xpassed = n
            elif "xfailed" in w:
                c.xfailed = n
            elif "passed" in w:
                c.passed = n
            elif "failed" in w:
                c.failed = n
            elif "skipped" in w:
                c.skipped = n
    return c


def filter_pytest_output(output: str) -> str:
    estado = "header"
    test_files: list[str] = []
    failures: list[str] = []
    atual: list[str] = []
    xfail_lines: list[str] = []
    summary_line = ""
    for line in linhas(output):
        t = trim(line)
        if t.startswith("===") and "test session starts" in t:
            estado = "header"
            continue
        elif t.startswith("===") and "FAILURES" in t:
            estado = "failures"
            continue
        elif t.startswith("===") and "short test summary" in t:
            estado = "summary"
            if atual:
                failures.append("\n".join(atual))
                atual = []
            continue
        elif t.startswith("===") and ("passed" in t or "failed" in t or "skipped" in t):
            summary_line = t
            continue
        elif (not summary_line and not t.startswith("===") and not t.startswith("FAILED")
              and not t.startswith("ERROR")
              and (" passed" in t or " failed" in t or " skipped" in t) and " in " in t):
            summary_line = t
            continue
        if estado == "header":
            if t.startswith("collected"):
                estado = "progress"
        elif estado == "progress":
            if t and not t.startswith("===") and (".py" in t or "%]" in t):
                test_files.append(t)
        elif estado == "failures":
            if t.startswith("___"):
                if atual:
                    failures.append("\n".join(atual))
                    atual = []
                atual.append(t)
            elif t and not t.startswith("==="):
                atual.append(t)
        elif estado == "summary":
            if t.startswith("FAILED") or t.startswith("ERROR"):
                failures.append(t)
            elif t.startswith("XFAIL") or t.startswith("XPASS"):
                xfail_lines.append(t)
    if atual:
        failures.append("\n".join(atual))
    return _build_summary(summary_line, failures, xfail_lines)


def _build_summary(summary: str, failures: list[str], xfail_lines: list[str]) -> str:
    c = parse_summary_line(summary)
    passed, failed, skipped, xfailed, xpassed = c.passed, c.failed, c.skipped, c.xfailed, c.xpassed
    if passed == 0 and failed == 0 and skipped == 0 and xfailed == 0 and xpassed == 0:
        return PYTEST_NO_TESTS
    extras = skipped > 0 or xfailed > 0 or xpassed > 0 or bool(xfail_lines)
    dur = f" in {c.duration}" if c.duration is not None else ""
    if failed == 0 and passed > 0 and not extras:
        return f"Pytest: {passed} passed{dur}"
    r = [f"Pytest: {passed} passed, {failed} failed"]
    if skipped > 0:
        r.append(f", {skipped} skipped")
    if xfailed > 0:
        r.append(f", {xfailed} xfailed")
    if xpassed > 0:
        r.append(f", {xpassed} xpassed")
    r.append(dur + "\n")
    if xfail_lines:
        r.append("\nExpected-failure outcomes:\n")
        for line in xfail_lines[:MAX_XFAIL]:
            r.append(f"  {truncate(line, 120)}\n")
        if len(xfail_lines) > MAX_XFAIL:
            r.append(f"  … +{len(xfail_lines) - MAX_XFAIL} more\n")
            dica = force_tee_tail_hint("\n".join(xfail_lines), "pytest-xfail", MAX_XFAIL + 1)
            if dica:
                r.append(f"  {dica}\n")
    if not failures:
        return trim("".join(r))
    r.append("\nFailures:\n")
    for i, failure in enumerate(failures[:MAX_PYTEST_FAILURES]):
        ls = linhas(failure)
        if ls:
            primeira = ls[0]
            if primeira.startswith("___"):
                r.append(f"{i + 1}. [FAIL] {trim(primeira.strip('_'))}\n")
            elif primeira.startswith("FAILED"):
                partes = primeira.split(" - ")
                nome = partes[0]
                while nome.startswith("FAILED "):
                    nome = nome[len("FAILED "):]
                r.append(f"{i + 1}. [FAIL] {nome}\n")
                if len(partes) > 1:
                    r.append(f"     {truncate(partes[1], 100)}\n")
                continue
        relevantes = 0
        for line in ls[1:]:
            baixa = line.lower()
            relevante = (trim(line).startswith(">") or trim(line).startswith("E")
                         or "assert" in baixa or "error" in baixa or ".py:" in line)
            if relevante and relevantes < 3:
                r.append(f"     {truncate(line, 100)}\n")
                relevantes += 1
        if i < len(failures) - 1:
            r.append("\n")
    if len(failures) > MAX_PYTEST_FAILURES:
        r.append(f"\n… +{len(failures) - MAX_PYTEST_FAILURES} more failures\n")
        dica = force_tee_hint("\n\n".join(failures), "pytest-failures")
        if dica:
            r.append(f"  {dica}\n")
    return trim("".join(r))


def filtrar(bruto: str, codigo: int) -> str:
    clean = strip_ansi(bruto)
    filtrado = filter_pytest_output(clean)
    if codigo != 0 and codigo != PYTEST_EXIT_NO_TESTS and filtrado == PYTEST_NO_TESTS:
        return truncate(trim(clean), PASSTHROUGH_MAX_CHARS)
    return filtrado


def mostrar(bruto: str, codigo: int) -> str:
    """O que o RTK imprime: filtro, dica de recuperacao se falhou, e a guarda."""
    return print_with_hint(filtrar(bruto, codigo), bruto, bruto, "pytest", codigo)
