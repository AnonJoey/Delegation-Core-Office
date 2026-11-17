"""`src/cmds/system/find_cmd.rs` do RTK: agrupamento de arquivos por diretorio e contagem de extensoes.

Compacta saidas de `find` e `fd`:
    4F 2D:

    src/ a.py b.py
    tests/ test_a.py test_b.py

    ext: .py(4)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from ..ambiente import Ambiente
from ..base import force_tee_tail_hint
from ..runner import run_filtered

COMANDOS = ("find", "fd")
CAP_INVENTORY = 50

VERBATIM_ACTIONS = frozenset([
    "-exec", "-execdir", "-ok", "-okdir", "-delete", "-print", "-print0", "-printf", "-fprint",
    "-fprint0", "-fprintf", "-ls", "-fls"
])


def group_by_dir(files: list[str]) -> dict[str, list[str]]:
    by_dir: dict[str, list[str]] = defaultdict(list)
    for file in files:
        clean = file[2:] if file.startswith("./") else file
        p = Path(clean)
        parent = str(p.parent) if str(p.parent) not in ("", ".") else "."
        by_dir[parent].append(p.name if p.name else clean)
    for d in by_dir:
        by_dir[d].sort()
    return by_dir


def display_ordered(files: list[str]) -> list[str]:
    by_dir = group_by_dir(files)
    dirs = sorted(by_dir.keys())
    ordered = []
    for d in dirs:
        for f in by_dir[d]:
            ordered.append(f if d == "." else f"{d}/{f}")
    return ordered


def filter_find_output(raw_output: str, max_results: int = CAP_INVENTORY, max_explicit: bool = False) -> str:
    lines = [ln.strip() for ln in raw_output.splitlines() if ln.strip()]
    if not lines:
        return ""

    files = lines
    total_files = len(files)
    by_dir = group_by_dir(files)
    dirs = sorted(by_dir.keys())
    dirs_count = len(dirs)

    body_lines = [f"{total_files}F {dirs_count}D:\n"]

    displayed = 0
    for d in dirs:
        if displayed >= max_results:
            break
        files_in_dir = by_dir[d]
        dir_display = f"...{d[-47:]}" if len(d) > 50 else d
        remaining = max_results - displayed

        if len(files_in_dir) <= remaining:
            body_lines.append(f"{dir_display}/ {' '.join(files_in_dir)}")
            displayed += len(files_in_dir)
        else:
            partial = files_in_dir[:remaining]
            body_lines.append(f"{dir_display}/ {' '.join(partial)}")
            displayed += len(partial)
            break

    if displayed < total_files:
        body_lines.append(f"+{total_files - displayed} more")

    # Extension summary
    exts = Counter()
    for f in files:
        ext = Path(f).suffix.lstrip(".") or "none"
        exts[ext] += 1

    if len(exts) > 1:
        ext_parts = [f".{e}({c})" for e, c in exts.most_common(5)]
        body_lines.append(f"\next: {' '.join(ext_parts)}")

    result = "\n".join(body_lines)

    if displayed < total_files and not max_explicit:
        ordered = display_ordered(files)
        hint = force_tee_tail_hint("\n".join(ordered), "find", displayed + 1)
        if hint:
            result = f"{result}\n{hint}"

    return result


def parse_max_args(args: list[str]) -> tuple[int, bool]:
    max_res = CAP_INVENTORY
    explicit = False
    for i, a in enumerate(args):
        if a in ("-m", "--max") and i + 1 < len(args):
            try:
                max_res = int(args[i + 1])
                explicit = True
            except ValueError:
                pass
    return max_res, explicit


def executa(args: list[str], comando: str = "find") -> bool:
    return not any(a in VERBATIM_ACTIONS for a in args)


def trata(args: list[str], comando: str = "find") -> bool:
    return not any(a in VERBATIM_ACTIONS for a in args)


def filtrar(bruto: str, codigo: int, args: tuple = (), injetado: bool = False) -> str:
    if codigo != 0 or not bruto.strip():
        return bruto
    max_res, explicit = parse_max_args(list(args))
    return filter_find_output(bruto, max_results=max_res, max_explicit=explicit)


def rodar(args: list[str], amb: Ambiente, comando: str = "find") -> int:
    cmd_bin = amb.resolver(comando)
    clean_args = []
    i = 0
    while i < len(args):
        if args[i] in ("-m", "--max") and i + 1 < len(args):
            i += 2
        else:
            clean_args.append(args[i])
            i += 1
    max_res, explicit = parse_max_args(args)
    filtro_fn = lambda out, code: filter_find_output(out, max_results=max_res, max_explicit=explicit)
    return run_filtered(amb, [cmd_bin, *clean_args], comando, filtro_fn, stdout_only=True)
