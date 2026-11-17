"""`src/cmds/python/ruff_cmd.rs` do RTK: `ruff check` agrupado por regra e arquivo, e `ruff format`.

O RTK roda `ruff check` com `--output-format=json` e filtra o JSON; `argumentos`
faz a mesma reescrita para o `delegation-core shell`. No `filter_output` o
agente ja rodou o comando, entao so ha JSON se ele o pediu: o filtro olha os
argumentos como foram de fato usados (`injetado=False`).

Diferencas deliberadas:
- Em empate de contagem a ordem do RTK muda a cada execucao (HashMap); aqui
  fica a de primeira aparicao.
- Quando o JSON nao tem o formato esperado, o RTK repete a mensagem de erro do
  serde_json (com linha e coluna); aqui a mensagem diz o que faltou, sem a
  posicao. O resto da saida desse caso e igual.
"""

from __future__ import annotations

import json

from ..base import force_tee_tail_hint, linhas, trim, truncate

COMANDOS = ("ruff",)
SO_STDOUT = True
CAP_WARNINGS = 10
PASSTHROUGH_MAX_CHARS = 2000
RUFF_SUBCOMMANDS = ["analyze", "check", "clean", "config", "format", "generate-shell-completion",
                    "help", "linter", "rule", "server", "version"]


def is_check_invocation(args) -> bool:
    if not args:
        return True
    a = args[0]
    return a == "check" or (not a.startswith("-") and a not in RUFF_SUBCOMMANDS)


def _formato(args) -> tuple[bool, bool]:
    """(usuario escolheu --output-format, e escolheu json)."""
    escolheu = any(a == "--output-format" or a.startswith("--output-format=") for a in args)
    json_ = any(a == "--output-format=json" or (a == "--output-format" and i + 1 < len(args) and args[i + 1] == "json")
                for i, a in enumerate(args))
    return escolheu, json_


def argumentos(args: list[str]) -> list[str]:
    """Os argumentos que o RTK passa ao ruff (o `run` do ruff_cmd.rs)."""
    if not is_check_invocation(args):
        return list(args)
    escolheu, _ = _formato(args)
    saida = ["check"] if escolheu else ["check", "--output-format=json"]
    ini = 1 if args and args[0] == "check" else 0
    resto = list(args[ini:])
    saida += resto
    if all(a.startswith("-") or "=" in a for a in resto):
        saida.append(".")
    return saida


def clean_outputs(args) -> tuple[str, ...]:
    escolheu, _ = _formato(args)
    return ("[]",) if is_check_invocation(args) and not escolheu else ()


def compact_path(path: str) -> str:
    path = path.replace("\\", "/")
    for marca, prefixo in (("/src/", "src/"), ("/lib/", "lib/"), ("/tests/", "tests/")):
        pos = path.rfind(marca)
        if pos >= 0:
            return prefixo + path[pos + len(marca):]
    pos = path.rfind("/")
    return path[pos + 1:] if pos >= 0 else path


def _usize(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def _diagnosticos(texto: str):
    """Vec<RuffDiagnostic> como o serde_json leria, ou (None, motivo)."""
    try:
        dados = json.loads(texto)
    except ValueError as e:
        return None, f"invalid JSON: {e.msg}"
    if not isinstance(dados, list):
        return None, "invalid type: expected a sequence"
    saida = []
    for d in dados:
        if not isinstance(d, dict):
            return None, "invalid type: expected struct RuffDiagnostic"
        for campo in ("code", "message", "filename"):
            if campo not in d:
                return None, f"missing field `{campo}`"
            if not isinstance(d[campo], str):
                return None, f"invalid type for `{campo}`: expected a string"
        loc = d.get("location")
        if not isinstance(loc, dict) or not _usize(loc.get("row")) or not _usize(loc.get("column")):
            return None, "invalid `location`: expected struct RuffLocation"
        fix = d.get("fix")
        if fix is not None and not (isinstance(fix, dict) and isinstance(fix.get("applicability", ""), (str, type(None)))):
            return None, "invalid type for `fix`: expected struct RuffFix"
        saida.append(d)
    return saida, None


def filter_ruff_check_json(output: str) -> str:
    diags, erro = _diagnosticos(output)
    if diags is None:
        return f"Ruff check (JSON parse failed: {erro})\n{truncate(output, PASSTHROUGH_MAX_CHARS)}"
    if not diags:
        return "Ruff: No issues found"
    total = len(diags)
    fixable = sum(1 for d in diags if d.get("fix") is not None)
    arquivos = len({d["filename"] for d in diags})
    by_rule: dict[str, int] = {}
    by_file: dict[str, int] = {}
    for d in diags:
        by_rule[d["code"]] = by_rule.get(d["code"], 0) + 1
    for d in diags:
        by_file[d["filename"]] = by_file.get(d["filename"], 0) + 1
    file_counts = sorted(by_file.items(), key=lambda kv: -kv[1])
    r = [f"Ruff: {total} issues in {arquivos} files"]
    if fixable > 0:
        r.append(f" ({fixable} fixable)")
    r.append("\n")
    rule_counts = sorted(by_rule.items(), key=lambda kv: -kv[1])
    if rule_counts:
        r.append("Top rules:\n")
        for regra, n in rule_counts[:CAP_WARNINGS]:
            r.append(f"  {regra} ({n}x)\n")
        r.append("\n")
    r.append("Top files:\n")
    for arq, n in file_counts[:CAP_WARNINGS]:
        r.append(f"  {compact_path(arq)} ({n} issues)\n")
        regras: dict[str, int] = {}
        for d in diags:
            if d["filename"] == arq:
                regras[d["code"]] = regras.get(d["code"], 0) + 1
        for regra, k in sorted(regras.items(), key=lambda kv: -kv[1])[:3]:
            r.append(f"    {regra} ({k})\n")
    if len(file_counts) > CAP_WARNINGS:
        r.append(f"\n... +{len(file_counts) - CAP_WARNINGS} more files\n")
    violacoes = [f"  {compact_path(d['filename'])}:{d['location']['row']}:{d['location']['column']} "
                 f"{d['code']} {truncate(trim(d['message']), 100)}\n" for d in diags]
    r.append("\nViolations:\n")
    r += violacoes[:50]
    if len(violacoes) > 50:
        r.append(f"  … +{len(violacoes) - 50} more\n")
        dica = force_tee_tail_hint("".join(violacoes), "ruff-check", 51)
        if dica:
            r.append(f"  {dica}\n")
    if fixable > 0:
        r.append(f"\n[hint] Run `ruff check --fix` to auto-fix {fixable} issues\n")
    return trim("".join(r))


def _usize_txt(s: str) -> int | None:
    t = s[1:] if s.startswith("+") else s
    return int(t) if t and t.isascii() and t.isdigit() else None


def filter_ruff_format(output: str) -> str:
    a_formatar: list[str] = []
    conferidos = 0
    for line in linhas(output):
        t = trim(line)
        baixa = t.lower()
        if "would reformat:" in baixa:
            partes = t.split(":")
            if len(partes) > 1:
                a_formatar.append(trim(partes[1]))
        if "left unchanged" in baixa:
            for parte in t.split(","):
                if "left unchanged" in parte.lower():
                    palavras = parte.split()
                    for i, w in enumerate(palavras):
                        if w in ("file", "files") and i > 0:
                            n = _usize_txt(palavras[i - 1])
                            if n is not None:
                                conferidos = n
                                break
                    break
    baixa_tudo = output.lower()
    if not a_formatar and "left unchanged" in baixa_tudo:
        return "Ruff format: All files formatted correctly"
    r = []
    if "would reformat" in baixa_tudo:
        if not a_formatar:
            r.append("Ruff format: All files formatted correctly\n")
        else:
            r.append(f"Ruff format: {len(a_formatar)} files need formatting\n")
            for i, f in enumerate(a_formatar[:CAP_WARNINGS]):
                r.append(f"{i + 1}. {compact_path(f)}\n")
            if len(a_formatar) > CAP_WARNINGS:
                r.append(f"\n... +{len(a_formatar) - CAP_WARNINGS} more files\n")
            if conferidos > 0:
                r.append(f"\n{conferidos} files already formatted\n")
            r.append("\n[hint] Run `ruff format` to format these files\n")
    else:
        r.append(trim(output))
    return trim("".join(r))


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = True) -> str:
    args = list(args)
    is_check = is_check_invocation(args)
    is_format = "format" in args
    escolheu, json_ = _formato(args)
    # Com a reescrita do RTK, check sem --output-format vira JSON; sem ela
    # (filter_output), so e JSON se o agente pediu.
    usa_json = (not escolheu or json_) if injetado else json_
    if is_check and usa_json and trim(bruto):
        return filter_ruff_check_json(bruto)
    if is_format:
        return filter_ruff_format(bruto)
    return truncate(trim(bruto), PASSTHROUGH_MAX_CHARS)
