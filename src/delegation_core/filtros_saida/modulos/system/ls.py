"""`src/cmds/system/ls.rs` do RTK: `ls` em uma linha por entrada, diretorios primeiro.

O RTK roda `ls -l` (ou `-la`) com `LC_ALL=C` mais as flags do usuario, le a listagem longa e a
refaz:

    src/                 pasta
    README.md  1.2K      arquivo e tamanho
    755  bin/            com -l, as permissoes em octal

Pastas de ruido (node_modules, .git, target...) saem, salvo com `-a` ou `-A`. O que passa de 50
entradas, e o que o RTK escondeu, vai para o armazem de recuperacao com uma dica. Se nenhuma linha
for entendida (outro idioma, por exemplo), mostra a saida original.
"""

from __future__ import annotations

import re

from ..ambiente import Ambiente
from ..base import _ESPACOS, force_tee_tail_hint, linhas, split_whitespace, trim
from ..runner import run_filtered

COMANDOS = ("ls",)
CAP_INVENTORY = 50
NOISE_DIRS = ("node_modules", ".git", "target", "__pycache__", ".next", "dist", "build", ".cache", ".turbo",
              ".vercel", ".pytest_cache", ".mypy_cache", ".tox", ".venv", "venv", "env", "coverage",
              ".nyc_output", ".DS_Store", "Thumbs.db", ".idea", ".vscode", ".vs", "*.egg-info", ".eggs")

# `\s` do crate regex e Unicode (White_Space); o do Python inclui mais quatro caracteres.
_S = "[" + re.escape(_ESPACOS) + "]"
_LS_DATE = re.compile(rf"{_S}+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec){_S}+[0-9]{{1,2}}{_S}+(?:[0-9]{{4}}|[0-9]{{2}}:[0-9]{{2}}){_S}+")
_U64 = re.compile(r"\+?[0-9]+")


def is_short_flag(arg: str) -> bool:
    return arg.startswith("-") and not arg.startswith("--")


def shows_dotfiles(args: list[str]) -> bool:
    """`-a`/`--all` e `-A`/`--almost-all`: o RTK mostra tudo o que o ls listou."""
    return any((is_short_flag(a) and any(c in "aA" for c in a)) or a in ("--all", "--almost-all") for a in args)


def is_dotdir(linha: str) -> bool:
    aparada = trim(linha)
    return aparada.endswith(".") or aparada.endswith("..")


def human_size(n: int) -> str:
    if n >= 1_048_576:
        return f"{n / 1_048_576.0:.1f}M"
    if n >= 1024:
        return f"{n / 1024.0:.1f}K"
    return f"{n}B"


def parse_ls_line(linha: str):
    """(tipo, permissoes, tamanho, nome) de uma linha de `ls -la`; a data e a ancora."""
    if is_dotdir(linha):
        return None
    m = _LS_DATE.search(linha)
    if m is None:
        return None
    nome = linha[m.end():]
    antes = split_whitespace(linha[:m.start()])
    if len(antes) < 4:
        return None
    perms = antes[0]
    tipo = perms[0]
    tamanho = 0
    # O tamanho e o numero mais a direita antes da data (o numero de links vem antes).
    for parte in reversed(antes):
        if _U64.fullmatch(parte) and int(parte) <= 2**64 - 1:
            tamanho = int(parte)
            break
    return tipo, perms, tamanho, nome


def perms_to_octal(perms: str) -> str | None:
    """`-rw-r--r--` -> `644`; bits especiais viram um quarto digito inicial."""
    if len(perms) < 10 or not perms.isascii():
        return None
    b = perms

    def valor(r: bool, w: bool, x: bool) -> int:
        return (int(r) << 2) | (int(w) << 1) | int(x)

    dono = valor(b[1] == "r", b[2] == "w", b[3] in "xs")
    grupo = valor(b[4] == "r", b[5] == "w", b[6] in "xs")
    outros = valor(b[7] == "r", b[8] == "w", b[9] in "xt")
    especial = valor(b[3] in "sS", b[6] in "sS", b[9] in "tT")
    return f"{especial}{dono}{grupo}{outros}" if especial > 0 else f"{dono}{grupo}{outros}"


def compact_ls(bruto: str, show_all: bool, show_long: bool):
    """(entradas, linhas lidas, cortadas, filtradas)."""
    dirs: list[tuple[str, str | None]] = []
    arquivos: list[tuple[str, str, str | None]] = []
    vistas = lidas = pontos = 0
    filtradas: list[str] = []
    for linha in linhas(bruto):
        if linha.startswith("total ") or not linha:
            continue
        vistas += 1
        p = parse_ls_line(linha)
        if p is None:
            if is_dotdir(linha):
                pontos += 1
            else:
                filtradas.append(trim(linha))
            continue
        tipo, perms, tamanho, nome = p
        lidas += 1
        if not show_all and nome in NOISE_DIRS:
            filtradas.append(f"{nome}/")
            continue
        octal = perms_to_octal(perms) if show_long else None
        if tipo == "d":
            dirs.append((nome, octal))
        else:
            arquivos.append((nome, human_size(tamanho), octal))

    if not dirs and not arquivos:
        if vistas > 0 and lidas == 0:
            if pontos == vistas:
                return "(empty)\n", 0, [], []
            return "", 0, [], []
        return "(empty)\n", lidas, [], filtradas

    todas: list[str] = []
    for nome, octal in dirs:
        todas.append(f"{octal}  {nome}/" if octal is not None else f"{nome}/")
    for nome, tamanho, octal in arquivos:
        todas.append(f"{octal}  {nome}  {tamanho}" if octal is not None else f"{nome}  {tamanho}")
    cortadas = todas[CAP_INVENTORY:]
    todas = todas[:CAP_INVENTORY]
    return "".join(l + "\n" for l in todas), lidas, cortadas, filtradas


def hidden_hint(cortadas: list[str], filtradas: list[str]) -> str | None:
    """A nota e a dica de recuperacao do que ficou de fora (o corte primeiro, depois o filtrado)."""
    if not cortadas and not filtradas:
        return None
    if not cortadas:
        nota = f"... ({len(filtradas)} filtered)"
    elif not filtradas:
        nota = f"... ({len(cortadas)} more)"
    else:
        nota = f"... ({len(cortadas)} more, {len(filtradas)} filtered)"
    escondidas = "".join(l + "\n" for l in cortadas + filtradas)
    dica = force_tee_tail_hint(escondidas, "ls-hidden", 1)
    return f"{nota}\n{dica}" if dica else nota


def _filtro(show_all: bool, show_long: bool):
    def filtro(bruto: str) -> str:
        entradas, lidas, cortadas, filtradas = compact_ls(bruto, show_all, show_long)
        tem_conteudo = any(not l.startswith("total ") and l and not is_dotdir(l) for l in linhas(bruto))
        if lidas == 0 and tem_conteudo:
            return bruto
        saida = entradas
        dica = hidden_hint(cortadas, filtradas)
        if dica is not None:
            saida += dica + "\n"
        return saida
    return filtro


def argumentos(args: list[str]) -> list[str]:
    """O que o RTK passa ao `ls`: `-l` (ou `-la`), as flags do usuario sem `l`, `a`, `h` e `--all`, e os caminhos."""
    quer_tudo = any((is_short_flag(a) and "a" in a) or a == "--all" for a in args)
    argv = ["-la" if quer_tudo else "-l"]
    for flag in (a for a in args if a.startswith("-")):
        if flag.startswith("--"):
            if flag != "--all":
                argv.append(flag)
        else:
            extra = "".join(c for c in flag.lstrip("-") if c not in "lah")
            if extra:
                argv.append("-" + extra)
    caminhos = [a for a in args if not a.startswith("-")]
    return argv + (caminhos or ["."])


def mostra_longa(args: list[str]) -> bool:
    """`-l`, e o que o `man ls` diz que o implica (`-g`, `-n`, `-o`, `--full-time`, `--format=long|verbose`)."""
    for a in args:
        if a in ("--full-time", "--format=long", "--format=verbose"):
            return True
        if a.startswith("-") and not a.startswith("--") and any(c in "lgno" for c in a):
            return True
    return False


def executa(args: list[str]) -> bool:
    return True


def rodar(args: list[str], amb: Ambiente) -> int:
    try:
        return run_filtered(amb, [amb.resolver("ls"), *argumentos(args)], "ls", _filtro(shows_dotfiles(args), mostra_longa(args)),
                            stdout_only=True, early_exit_on_failure=True, no_trailing_newline=True,
                            env={"LC_ALL": "C"})
    except OSError as e:
        amb.err(f"Error: Failed to run ls: {e}\n")
        return 1


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """Sem o `ls -l` do RTK nao ha o que ler: a saida que o agente ja tem segue como esta."""
    return bruto


def trata(args: list[str]) -> bool:
    return False
