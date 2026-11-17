"""`src/cmds/system/search.rs` do RTK: `grep` e `rg` agrupados por arquivo, com teto.

Roda o motor que o agente chamou (grep ou rg, nunca um no lugar do outro) com
`-n -H --null` por cima, para poder ler a saida sem ambiguidade, e a refaz como
ele a teria impresso. So muda de forma quando o teto (200 resultados, 25 por
arquivo) corta alguma coisa e o resultado agrupado e menor que o original; o
que sobra do corte vai para o armazem de recuperacao, com uma dica.

Cinco caminhos, como no RTK:

- `--help`/`--version`: a saida do motor, sem filtro;
- comando sem padrao (`rg --files`, `--type-list`) ou com flag de formato
  (`-c`, `-l`, `-o`, `--json`...): a saida do motor, sem as cores; `-l`, `-L` e
  `--files` ganham o diretorio comum dobrado num cabecalho;
- com entrada padrao legivel (arquivo, FIFO ou socket) e sem caminho (ou `-`): o
  motor le a entrada e cada linha e reescrita assim que chega;
- o resto: captura, agrupa por arquivo (ordem alfabetica), corta e imprime.

Diferencas deliberadas:
- Os limites (200 resultados, 25 por arquivo, 80 colunas) sao os padroes do RTK. O
  `config.toml` do RTK nao e lido.
- `restore_double_dash` nao e portado: o `--` ja chega no comando.
- O sinal de interrupcao nao e repassado ao motor (o `signal_relay` do RTK).
- `--context-only` existe na funcao (`context_only`), mas o `shell` nunca o liga.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .. import arg_tokenizer as at
from .. import base
from ..ambiente import Ambiente
from ..arg_tokenizer import LONG, POSITIONAL, SHORT, Token, ValueSpec
from ..base import force_tee_tail_hint, linhas, never_worse, strip_ansi, trim

COMANDOS = ("grep", "rg")
GREP, RG = "grep", "rg"
MAX_LINE_LEN = 80
MAX_RESULTS = 200
GREP_MAX_PER_FILE = 25
USIZE_MAX = 2**64 - 1

_GREP_LONGAS = frozenset("""
after-context before-context binary-files context devices directories exclude exclude-dir
exclude-from file group-separator include label max-count regexp
""".split())
_GREP_CURTAS = frozenset("A B C D X d e f m".split())
_RG_LONGAS = frozenset("""
after-context before-context color colors context context-separator dfa-size-limit encoding engine
field-context-separator field-match-separator file generate glob hostname-bin hyperlink-format iglob
ignore-file max-columns max-count max-depth max-filesize path-separator pre pre-glob regex-size-limit
regexp replace sort sortr threads type type-add type-clear type-not
""".split())
_RG_CURTAS = frozenset("A B C E M T d e f g j m r t".split())

_FLAGS_DE_FORMATO = frozenset("""
byte-offset column count count-matches files files-with-matches files-without-match json null null-data
only-matching passthru quiet silent vimgrep
""".split())

_MATCH_LINE = re.compile(r"([^\x00]+)\x00([0-9]+)([:-])(.*)")


# ── a gramatica de flags de cada motor ───────────────────────────────────────

def grep_takes_value(kind: str, name: str) -> bool:
    if kind == LONG:
        return name in _GREP_LONGAS
    return kind == SHORT and name in _GREP_CURTAS


def rg_takes_value(kind: str, name: str) -> bool:
    if kind == LONG:
        return name in _RG_LONGAS
    return kind == SHORT and name in _RG_CURTAS


def search_takes_value(engine: str, kind: str, name: str) -> ValueSpec | None:
    """Toda flag com valor de grep e rg aceita ate um `--` literal como valor (ao contrario do git)."""
    toma = grep_takes_value(kind, name) if engine == GREP else rg_takes_value(kind, name)
    return ValueSpec.value().claiming_dash_dash() if toma else None


def tokenize_search_args(args: list[str], engine: str) -> list[Token]:
    return at.tokenize_grammar(args, lambda kind, name: search_takes_value(engine, kind, name))


def unwrap_attached_value(engine: str, valor: str) -> str:
    """O rg aceita `-A=1` e `-e=PAT` e tira o `=`; o grep nao. So o valor preso."""
    return valor[1:] if engine == RG and valor.startswith("=") else valor


# ── predicados de flag ───────────────────────────────────────────────────────

def is_format_flag_token(engine: str, kind: str, text: str) -> bool:
    """Formas minimas que o agente ja escolheu (`-c`, `-l`, `-o`, `--json`...)."""
    if kind == LONG:
        return text in _FLAGS_DE_FORMATO or (engine == GREP and text == "initial-tab")
    if kind == SHORT:
        if text in ("L", "T", "z"):
            return engine == GREP
        return text in ("Z", "b", "c", "l", "o", "q")
    return False


def is_bare_file_list(engine: str, args: list[str]) -> bool:
    """A unica flag de forma e uma lista de arquivos (`-l`, `-L` do grep, `--files`)."""
    lista = False
    for t in tokenize_search_args(args, engine):
        if t.kind == LONG:
            e_lista = t.text in ("files", "files-with-matches", "files-without-match")
        elif t.kind == SHORT:
            e_lista = t.text == "l" or (t.text == "L" and engine == GREP)
        else:
            e_lista = False
        if e_lista:
            lista = True
        elif is_format_flag_token(engine, t.kind, t.text):
            return False
    return lista


def is_show_file_token(kind: str, text: str) -> bool:
    return (kind == LONG and text == "with-filename") or (kind == SHORT and text == "H")


def is_recursive_token(engine: str, kind: str, text: str) -> bool:
    if engine != GREP:
        return False
    return (kind == LONG and text == "recursive") or (kind == SHORT and text in ("R", "r"))


def is_show_line_on_token(kind: str, text: str) -> bool:
    return (kind == LONG and text == "line-number") or (kind == SHORT and text == "n")


def is_show_file_off_token(engine: str, kind: str, text: str) -> bool:
    """`-h`/`--no-filename`. O `-h` do rg e `--help` e o `-I` do grep e outra coisa."""
    if kind == LONG:
        return text == "no-filename"
    if kind == SHORT:
        return (text == "h" and engine == GREP) or (text == "I" and engine == RG)
    return False


def is_show_line_off_token(engine: str, kind: str, text: str) -> bool:
    """`-N`/`--no-line-number`: so do rg (o grep sai com 2 nas duas)."""
    if engine != RG:
        return False
    return (kind == LONG and text == "no-line-number") or (kind == SHORT and text == "N")


def is_context_token(engine: str, kind: str, text: str) -> bool:
    if kind == LONG:
        return text in ("after-context", "before-context", "context")
    if kind == SHORT:
        return text in ("A", "B", "C") or (engine == GREP and at.is_digit_run(text))
    return False


@dataclass
class DetectedFlags:
    #: `-H` (True) ou `-h` (False), a ultima grafia vence; None se o usuario nao disse.
    show_file: bool | None = None
    show_line: bool = False
    #: `-r`/`-R`/`--recursive` do grep: nao pede o nome do arquivo, so e motivo para ele aparecer.
    recursive: bool = False
    context: bool = False


# ── extracao de padroes, caminhos e flags ────────────────────────────────────

def extract_pattern_path(args: list[str], engine: str):
    """(padroes, caminhos, flags repassadas, tem flag de formato, DetectedFlags)."""
    tokens = tokenize_search_args(args, engine)
    e_patterns: list[str] = []
    patterns_from_file = False
    positionals: list[str] = []
    flags: list[str] = []
    has_format = False
    show_file: bool | None = None
    show_line: bool | None = None
    recursive = context = False
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.kind == LONG and t.text == "regexp":
            v = t.value(tokens)
            if v is not None:
                e_patterns.append(v)
        elif t.kind == LONG:
            if t.text == "file":
                patterns_from_file = True
            if is_format_flag_token(engine, t.kind, t.text):
                has_format = True
            if is_show_file_token(t.kind, t.text):
                show_file = True
            if is_recursive_token(engine, t.kind, t.text):
                recursive = True
            if is_show_line_on_token(t.kind, t.text):
                show_line = True
            # Nenhuma das negacoes segue para o motor: o RTK forca `-nH` para ler a saida.
            if is_show_file_off_token(engine, t.kind, t.text):
                show_file = False
                i += 1
                continue
            if is_show_line_off_token(engine, t.kind, t.text):
                show_line = False
                i += 1
                continue
            if is_context_token(engine, t.kind, t.text):
                context = True
            if t.attached is not None:
                flags.append(f"--{t.text}={t.attached}")
            else:
                flags.append(f"--{t.text}")
                v = t.value(tokens)
                if v is not None:
                    flags.append(v)
        elif t.kind == POSITIONAL and t.is_free_positional():
            positionals.append(t.text)
        elif t.kind == SHORT:
            origem = t.source_index
            inicio = i
            while i + 1 < len(tokens) and tokens[i + 1].kind == SHORT and tokens[i + 1].source_index == origem:
                i += 1
            grupo = tokens[inicio:i + 1]
            if any(is_format_flag_token(engine, c.kind, c.text) for c in grupo):
                has_format = True
            # Letra a letra, para `-hH` e `-Hh` caiam onde o motor os poe: a ultima vence.
            for c in grupo:
                if is_show_file_token(c.kind, c.text):
                    show_file = True
                elif is_show_file_off_token(engine, c.kind, c.text):
                    show_file = False
                if is_show_line_on_token(c.kind, c.text):
                    show_line = True
                elif is_show_line_off_token(engine, c.kind, c.text):
                    show_line = False
                if is_recursive_token(engine, c.kind, c.text):
                    recursive = True
            if any(is_context_token(engine, c.kind, c.text) for c in grupo):
                context = True
            ultima = grupo[-1]
            if search_takes_value(engine, SHORT, ultima.text) is not None:
                letras, letra_com_valor = grupo[:-1], ultima
            else:
                letras, letra_com_valor = grupo, None
            # `-h` e `-N` saem do grupo pelo mesmo motivo das formas longas.
            colado = "".join(c.text for c in letras
                             if not is_show_file_off_token(engine, c.kind, c.text)
                             and not is_show_line_off_token(engine, c.kind, c.text))
            if colado:
                flags.append(f"-{colado}")
            if letra_com_valor is not None:
                vt = letra_com_valor
                valor = unwrap_attached_value(engine, vt.attached) if vt.attached is not None else vt.value(tokens)
                if vt.text == "e":
                    if valor is not None:
                        e_patterns.append(valor)
                    else:
                        flags.append("-e")
                else:
                    if vt.text == "f":
                        patterns_from_file = True
                    flags.append(f"-{vt.text}")
                    if valor is not None:
                        flags.append(valor)
        i += 1

    # `-e` e `-f` ja trazem os padroes: todo posicional e caminho.
    if e_patterns or patterns_from_file:
        patterns, paths = e_patterns, positionals
    else:
        patterns, paths = positionals[:1], positionals[1:]
    return (patterns, paths, flags, has_format,
            DetectedFlags(show_file, bool(show_line), recursive, context))


# ── linhas da saida ──────────────────────────────────────────────────────────

def parse_match_line(linha: str):
    """`arquivo\\0numero[:-]conteudo` -> (arquivo, numero, e_match, conteudo). Exige `--null`."""
    m = _MATCH_LINE.fullmatch(linha)
    if m is None:
        return None
    numero = int(m.group(2))
    if numero > USIZE_MAX:
        return None
    return m.group(1), numero, m.group(3) == ":", m.group(4)


def format_match_line(linha: str, show_file: bool, show_line: bool) -> str | None:
    p = parse_match_line(linha)
    if p is None:
        return None
    arquivo, numero, e_match, conteudo = p
    sep = ":" if e_match else "-"
    saida = ""
    if show_file:
        saida += arquivo + sep
    if show_line:
        saida += f"{numero}{sep}"
    return saida + conteudo + "\n"


def unparsed_signal(stdout: str) -> int:
    return sum(1 for l in linhas(stdout)
               if trim(l) and trim(l) != "--" and parse_match_line(l) is None)


def grep_slug(idx: int, path: str) -> str:
    limpo = "".join(c if (c.isascii() and c.isalnum()) else "_" for c in path)
    return f"grep_{idx}_{limpo[max(0, len(limpo) - 32):]}"


def match_block(path: str, entradas: list[tuple[int, bool, str]]) -> str:
    saida = ""
    for numero, e_match, conteudo in entradas:
        sep = ":" if e_match else "-"
        saida += f"{path}{sep}{numero}{sep}{conteudo}\n"
    return saida


def clean_line(linha: str, max_len: int, context_re, pattern: str) -> str:
    aparada = trim(linha)
    if context_re is not None:
        m = context_re.search(aparada)
        if m is not None and len(m.group(0).encode("utf-8")) <= max_len:
            return m.group(0)
    if len(aparada.encode("utf-8")) <= max_len:
        return aparada
    minuscula = aparada.lower()
    pos = minuscula.find(pattern.lower())
    if pos >= 0:
        letras = list(aparada)
        total = len(letras)
        inicio = max(0, pos - max_len // 3)
        fim = min(inicio + max_len, total)
        if fim == total:
            inicio = max(0, fim - max_len)
        fatia = "".join(letras[inicio:fim])
        if inicio > 0 and fim < total:
            return f"...{fatia}..."
        if inicio > 0:
            return f"...{fatia}"
        return f"{fatia}..."
    return "".join(list(aparada)[:max_len - 3]) + "..."


def compact_path(path: str) -> str:
    if len(path.encode("utf-8")) <= 50:
        return path
    partes = path.split("/")
    if len(partes) <= 3:
        return path
    return f"{partes[0]}/.../{partes[-2]}/{partes[-1]}"


def fold_path_prefix(bruto: str) -> str | None:
    """Dobra o diretorio que toda linha de uma lista de arquivos repete num cabecalho."""
    if any(c in bruto for c in ("\0", "\r", "\x1b")):
        return None
    caminhos = linhas(bruto)
    if len(caminhos) < 2 or any(not p for p in caminhos):
        return None

    def dirs(p: str) -> list[str]:
        return p.rsplit("/", 1)[0].split("/") if "/" in p else []

    primeiro = dirs(caminhos[0])
    comum = len(primeiro)
    for p in caminhos[1:]:
        compartilhado = 0
        for a, b in zip(dirs(p)[:comum], primeiro):
            if a != b:
                break
            compartilhado += 1
        comum = compartilhado
        if comum == 0:
            return None
    prefixo = "/".join(primeiro[:comum]) + "/"
    if len(prefixo) <= 1:
        return None
    saida = f"{prefixo} ({len(caminhos)} files)\n"
    for p in caminhos:
        saida += (p[len(prefixo):] if p.startswith(prefixo) else p) + "\n"
    return saida


# ── execucao ─────────────────────────────────────────────────────────────────

def _parse_flags(engine: str) -> list[str]:
    """`-n -H --null` ajudam a ler a saida; `-I` pula binarios (o `-a` do usuario manda)."""
    return ["-n", "-H", "-I", "--null"] if engine == GREP else ["-n", "--with-filename", "--null"]


def engine_argv(engine: str, extra_args: list[str], patterns: list[str], paths: list[str],
                line_buffered: bool = False) -> list[str]:
    """Sem o executavel: quem chama poe `amb.resolver(engine)` na frente."""
    argv = [*_parse_flags(engine), *extra_args]
    if line_buffered:
        argv.append("--line-buffered")
    for p in patterns:
        argv += ["-e", p]
    return argv + ["--", *paths]


def wants_show_file(paths: list[str], flags_show_file: bool, amb: Ambiente) -> bool:
    return len(paths) > 1 or any(_e_diretorio(p, amb) for p in paths) or flags_show_file


def _e_diretorio(p: str, amb: Ambiente) -> bool:
    import os
    return os.path.isdir(amb.caminho(p))


class SearchStreamFilter:
    """Reescreve cada linha assim que chega: `tail -f app.log | grep ERROR` nao pode esperar o fim."""

    def __init__(self, show_file: bool, show_line: bool, max_results: int):
        self.show_file, self.show_line, self.max_results = show_file, show_line, max_results
        self.shown = 0
        self.cap_reported = False

    def feed_line(self, linha: str, eh_stderr: bool = False) -> str | None:
        saida = format_match_line(linha, self.show_file, self.show_line)
        if saida is None:
            if linha == "--" and self.shown >= self.max_results:
                return None
            return linha + "\n"
        if self.shown >= self.max_results:
            if self.cap_reported:
                return None
            self.cap_reported = True
            return f"[{base.PREFIXO}] output capped at {self.max_results} results\n"
        self.shown += 1
        return saida


def passthrough(amb: Ambiente, engine: str, args: list[str], stream_stdin: bool, fold_file_list: bool) -> int:
    """O comando do agente como foi digitado, para as formas que o RTK nao agrupa."""
    argv = [amb.resolver(engine)]
    if stream_stdin and not amb.stdout_e_terminal():
        argv.append("--line-buffered")
    argv += args
    if stream_stdin:
        return amb.repassar(argv)
    r = amb.capturar(argv, herdar_stdin=True)
    limpo = strip_ansi(r.stdout)
    dobrado = None
    if fold_file_list:
        candidato = fold_path_prefix(limpo)
        if candidato is not None and never_worse(limpo, candidato) == candidato:
            dobrado = candidato
    amb.out(dobrado if dobrado is not None else limpo)
    if r.stderr:
        amb.err(r.stderr)
    return r.codigo


def run(engine: str, max_line_len: int, max_results: int, context_only: bool, args: list[str], amb: Ambiente) -> int:
    ajuda = tokenize_search_args(args, engine)
    antes = at.before_dashdash(ajuda)
    pede_ajuda = any((t.kind == LONG and t.text in ("version", "help")) or (t.kind == SHORT and t.text == "h" and engine == RG)
                     for t in antes)
    valor_pendente = any(t.kind in (LONG, SHORT) and search_takes_value(engine, t.kind, t.text) is not None
                         and t.value(ajuda) is None for t in ajuda)
    if valor_pendente:
        return passthrough(amb, engine, args, False, False)
    if pede_ajuda:
        r = amb.capturar([amb.resolver(engine), *args])
        amb.out(r.stdout)
        if r.stderr:
            amb.err(r.stderr)
        return r.codigo

    patterns, paths, extra_args, extra_tem_formato, detected = extract_pattern_path(args, engine)

    if not patterns:
        return passthrough(amb, engine, args, False, is_bare_file_list(engine, args))

    pattern_display = patterns[0] if len(patterns) == 1 else "|".join(patterns)
    le_stdin = amb.stdin_legivel() and (not paths or any(p == "-" for p in paths))

    if extra_tem_formato:
        return passthrough(amb, engine, args, le_stdin, is_bare_file_list(engine, args))

    if le_stdin:
        filtro = SearchStreamFilter(
            detected.show_file if detected.show_file is not None else wants_show_file(paths, detected.recursive, amb),
            detected.show_line, max_results)
        return amb.transmitir([amb.resolver(engine), *engine_argv(engine, extra_args, patterns, paths, True)],
                              filtro.feed_line)

    r = amb.capturar([amb.resolver(engine), *engine_argv(engine, extra_args, patterns, paths)], herdar_stdin=True)
    bruto = r.stdout

    # Forma que nao da para ler: refaz o comando sem o que o RTK injetou (com o stderr dele).
    if unparsed_signal(bruto) > 0:
        return passthrough(amb, engine, args, False, False)
    if r.stderr:
        amb.err(r.stderr)
    if not trim(r.stdout):
        return r.codigo

    context_re = None
    if context_only:
        try:
            context_re = re.compile(f"(?i).{{0,20}}{re.escape(pattern_display)}.*")
        except re.error:
            context_re = None

    por_arquivo: dict[str, list[tuple[int, bool, str]]] = {}
    for linha in linhas(bruto):
        p = parse_match_line(linha)
        if p is None:
            continue
        arquivo, numero, e_match, conteudo = p
        por_arquivo.setdefault(arquivo, []).append(
            (numero, e_match, clean_line(conteudo, max_line_len, context_re, pattern_display)))

    total = sum(1 for v in por_arquivo.values() for _, e_match, _c in v if e_match)

    anda_no_cwd = engine == RG and not paths
    show_file = detected.show_file if detected.show_file is not None else (
        len(por_arquivo) > 1 or anda_no_cwd or wants_show_file(paths, detected.recursive, amb))
    show_line = detected.show_line

    simples = ""
    for linha in linhas(bruto):
        saida = format_match_line(linha, show_file, show_line)
        if saida is None:
            if linha == "--":
                simples += "--\n"
            continue
        simples += saida

    tem_contexto = detected.context
    corpo = ""
    mostradas = 0
    arquivos_pulados = 0
    bloco_pulado = ""
    for idx, arquivo in enumerate(sorted(por_arquivo)):
        entradas = por_arquivo[arquivo]
        if mostradas >= max_results:
            arquivos_pulados += 1
            bloco_pulado += match_block(arquivo, entradas)
            continue
        exibido = compact_path(arquivo)
        do_arquivo = 0
        anterior = 0
        for numero, e_match, conteudo in entradas[:GREP_MAX_PER_FILE]:
            if mostradas >= max_results:
                break
            if tem_contexto and anterior > 0 and numero > anterior + 1:
                corpo += "--\n"
            anterior = numero
            sep = ":" if e_match else "-"
            if show_file:
                corpo += exibido + sep
            if show_line:
                corpo += f"{numero}{sep}"
            corpo += conteudo + "\n"
            mostradas += 1
            do_arquivo += 1
        restantes = len(entradas) - do_arquivo
        if restantes == 0:
            continue
        dica = force_tee_tail_hint(match_block(arquivo, entradas), grep_slug(idx, arquivo), do_arquivo + 1)
        corpo += f"  +{restantes} more in {exibido} {dica}\n" if dica else f"  +{restantes} more in {exibido}\n"

    if arquivos_pulados > 0:
        dica = force_tee_tail_hint(bloco_pulado, "grep_skipped", 1)
        corpo += f"+{arquivos_pulados} more files{' ' + dica if dica else ''}\n"

    cortou = mostradas < total or arquivos_pulados > 0
    agrupado = f"{total} matches in {len(por_arquivo)} files:\n\n{corpo}" if cortou else corpo
    saida = agrupado if cortou and len(agrupado.encode("utf-8")) < len(simples.encode("utf-8")) else simples
    amb.out(saida)
    return r.codigo


def executa(args: list[str], comando: str = "") -> bool:
    return comando in COMANDOS


def rodar(args: list[str], amb: Ambiente, comando: str = GREP) -> int:
    """`rtk grep ...` e `rtk rg ...` com os padroes do RTK (80 colunas, 200 resultados)."""
    try:
        return run(comando, MAX_LINE_LEN, MAX_RESULTS, False, list(args), amb)
    except OSError as e:
        amb.err(f"Error: search failed: {e}\n")
        return 1


def filtrar(bruto: str, codigo: int, args=(), injetado: bool = False) -> str:
    """O RTK so reduz a busca rodando o motor com `--null`; a saida que o agente ja tem nao
    traz o limite entre arquivo e linha. O `filter_output` segue pelo compressor de busca."""
    return bruto


def trata(args: list[str], comando: str = "") -> bool:
    return False

