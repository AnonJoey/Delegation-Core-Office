"""`src/cmds/python/mypy_cmd.rs` do RTK: erros do mypy agrupados por arquivo.

Diferenca deliberada: o Rust agrupa em HashMap, cuja ordem e aleatoria a cada
execucao, e ordena por contagem; em empate a ordem do RTK muda de uma rodada
para outra. Aqui o empate fica na ordem de primeira aparicao (dict do Python),
o que e uma das ordens que o RTK pode produzir e a unica estavel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..base import linhas, strip_ansi, trim, truncate

COMANDOS = ("mypy",)
MYPY_CLEAN = "mypy: No issues found"
MYPY_DIAG = re.compile(r"^(.+?):(\d+)(?::\d+)?: (error|warning|note): (.+?)(?:\s+\[(.+)\])?$")


@dataclass
class MypyError:
    file: str
    line: int
    code: str
    message: str
    context_lines: list[str] = field(default_factory=list)


def _diag(linha: str):
    # `$` do Python aceita um \n final; o do crate regex nao. linhas() ja tira
    # o \n, mas um \r solto no meio nao e linha: fullmatch evita a diferenca.
    return MYPY_DIAG.fullmatch(linha)


def filter_mypy_output(output: str) -> str:
    ls = linhas(output)
    errors: list[MypyError] = []
    fileless_lines: list[str] = []
    i = 0
    while i < len(ls):
        line = ls[i]
        if line.startswith("Found ") and " error" in line:
            i += 1
            continue
        if line.startswith("Success:"):
            i += 1
            continue
        m = _diag(line)
        if m:
            severity, file = m.group(3), m.group(1)
            try:
                line_num = int(m.group(2))
            except ValueError:  # usize que estoura vira 0, como o unwrap_or(0)
                line_num = 0
            if line_num >= 2 ** 64:
                line_num = 0
            message, code = m.group(4), m.group(5) or ""
            if severity == "note":
                if errors and errors[-1].file == file:
                    errors[-1].context_lines.append(message)
                    i += 1
                    continue
                fileless_lines.append(line)
                i += 1
                continue
            err = MypyError(file, line_num, code, message)
            i += 1
            while i < len(ls):
                n = _diag(ls[i])
                if n and n.group(3) == "note" and n.group(1) == err.file:
                    err.context_lines.append(n.group(4))
                    i += 1
                    continue
                break
            errors.append(err)
        elif "error:" in line and trim(line):
            fileless_lines.append(line)
            i += 1
        else:
            i += 1

    if not errors and not fileless_lines:
        return MYPY_CLEAN

    by_file: dict[str, list[MypyError]] = {}
    for err in errors:
        by_file.setdefault(err.file, []).append(err)
    by_code: dict[str, int] = {}
    for err in errors:
        if err.code:
            by_code[err.code] = by_code.get(err.code, 0) + 1

    out = [line + "\n" for line in fileless_lines]
    if fileless_lines and errors:
        out.append("\n")
    if errors:
        out.append(f"mypy: {len(errors)} errors in {len(by_file)} files\n")
        code_counts = sorted(by_code.items(), key=lambda kv: -kv[1])
        if len(code_counts) > 1:
            out.append("Top codes: " + ", ".join(f"{c} ({n}x)" for c, n in code_counts[:5]) + "\n\n")
        for file, file_errors in sorted(by_file.items(), key=lambda kv: -len(kv[1])):
            out.append(f"{file} ({len(file_errors)} errors)\n")
            for err in file_errors:
                if not err.code:
                    out.append(f"  L{err.line}: {truncate(err.message, 120)}\n")
                else:
                    out.append(f"  L{err.line}: [{err.code}] {truncate(err.message, 120)}\n")
                for ctx in err.context_lines:
                    out.append(f"    {truncate(ctx, 120)}\n")
            out.append("\n")
    return trim("".join(out))


def filtrar(bruto: str, codigo: int) -> str:
    clean = strip_ansi(bruto)
    filtrado = filter_mypy_output(clean)
    if codigo != 0 and filtrado == MYPY_CLEAN:
        return trim(clean)
    return filtrado
