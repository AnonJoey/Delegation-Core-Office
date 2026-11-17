"""Porte de `crates/headroom-core/src/transforms/log_compressor.rs` (Headroom, Apache 2.0).

Comprime saida de build e teste (pytest, npm, cargo, jest, make, generica):
deteccao de formato, nivel por linha, stack traces por linguagem (Python, JS,
Java, .NET, Rust, Go), pontuacao, orcamento adaptativo, selecao por
categoria com contexto e, quando o resultado fica abaixo de metade do
original, a marca reversivel `[N lines compressed to M... Retrieve more:
hash=<chave>]` com o original guardado (`ccr.py`).

Fiel ao Rust nas regras que mudam a saida; nomes de funcao mantidos em ingles
onde espelham o original, para a comparacao linha a linha.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .adaptativo import compute_optimal_k

# ─── formato ────────────────────────────────────────────────────────────

_FORMATOS = [
    ("pytest", ["=== FAILURES", "=== ERRORS", "=== test session", "=== short test summary", "PASSED [",
                "FAILED [", "ERROR [", "SKIPPED [", "collected "]),
    ("npm", ["npm ERR!", "npm WARN", "npm info", "npm http"]),
    ("cargo", ["Compiling ", "Finished ", "Running ", "warning: ", "error[E"]),
    ("jest", ["PASS ", "FAIL ", "Test Suites:"]),
    ("make", ["make[", "make:", "gcc ", "g++ ", "clang "]),
]


def detect_format(linhas: list[str]) -> str:
    amostra = linhas[:100]
    melhor = None
    for fmt, padroes in _FORMATOS:
        pontos = sum(1 for l in amostra if any(p in l for p in padroes))
        if pontos > 0 and (melhor is None or pontos > melhor[1]):
            melhor = (fmt, pontos)
    return melhor[0] if melhor else "generic"


# ─── nivel ──────────────────────────────────────────────────────────────

_NIVEIS = [
    ("error", ["ERROR", "error", "Error", "FATAL", "fatal", "Fatal", "CRITICAL", "critical"]),
    ("fail", ["FAIL", "FAILED", "fail", "failed", "Fail", "Failed"]),
    ("warn", ["WARN", "WARNING", "warn", "warning", "Warn", "Warning"]),
    ("info", ["INFO", "info", "Info"]),
    ("debug", ["DEBUG", "debug", "Debug"]),
    ("trace", ["TRACE", "trace", "Trace"]),
]
_NIVEL_DE = {w: nivel for nivel, ws in _NIVEIS for w in ws}
# Alternacao do mais longo para o mais curto = leftmost-longest do aho-corasick.
_NIVEL_RE = re.compile("|".join(re.escape(w) for w in sorted(_NIVEL_DE, key=len, reverse=True)))


def _palavra(c: str) -> bool:
    return c.isascii() and (c.isalnum() or c == "_")


def classify(linha: str) -> str:
    for m in _NIVEL_RE.finditer(linha):
        s, e = m.start(), m.end()
        if (s == 0 or not _palavra(linha[s - 1])) and (e == len(linha) or not _palavra(linha[e])):
            return _NIVEL_DE[m.group(0)]
    return "unknown"


# ─── stack trace ────────────────────────────────────────────────────────

def _digito(c: str) -> bool:
    return "0" <= c <= "9"


def _hex(c: str) -> bool:
    return c in "0123456789abcdefABCDEF"


def _alnum(c: str) -> bool:
    return c.isascii() and c.isalnum()


def has_line_col_suffix(s: str) -> bool:
    b = s
    for i in range(max(0, len(b) - 2)):
        if b[i] == ":" and _digito(b[i + 1]):
            j = i + 1
            while j < len(b) and _digito(b[j]):
                j += 1
            if j < len(b) and b[j] == ":" and j + 1 < len(b) and _digito(b[j + 1]):
                return True
    return False


def is_python_file_frame(s: str) -> bool:
    return s.startswith('File "') and '", line ' in s and bool(s) and _digito(s[-1])


def is_js_at_frame(s: str) -> bool:
    return s.startswith("at ") and "(" in s and ")" in s and has_line_col_suffix(s)


def is_java_at_frame(s: str) -> bool:
    if not s.startswith("at ") or "(" not in s:
        return False
    corpo = s[3:s.index("(")] if s.index("(") >= 3 else ""
    return bool(corpo) and all(_alnum(c) or c in "._$/" for c in corpo)


def is_rust_panic_opener(s: str) -> bool:
    return s.startswith("thread '") and "panicked at" in s


def is_goroutine_header(linha: str) -> bool:
    if not linha.startswith("goroutine "):
        return False
    resto = linha[len("goroutine "):]
    d = 0
    while d < len(resto) and _digito(resto[d]):
        d += 1
    return d > 0 and resto[d:].startswith(" [")


def is_go_panic_opener(linha: str) -> bool:
    return linha.startswith("panic: ") or linha.startswith("fatal error: ") or is_goroutine_header(linha)


def is_go_file_frame(linha: str) -> bool:
    if not linha.startswith("\t"):
        return False
    resto = linha[1:]
    return ".go:" in resto and " +0x" in resto


def is_go_call_frame(linha: str) -> bool:
    if linha.startswith("created by "):
        return True
    if linha.startswith((" ", "\t")) or not linha.endswith(")"):
        return False
    if "(" not in linha:
        return False
    simbolo = linha[:linha.index("(")]
    return bool(simbolo) and "." in simbolo and all(_alnum(c) or c in "._/*" for c in simbolo)


def is_dotnet_frame(s: str) -> bool:
    return s.startswith("at ") and ") in " in s and ":line " in s


def is_dotnet_opener(s: str) -> bool:
    return s.startswith("Unhandled exception.") or is_dotnet_frame(s)


def is_rust_backtrace_frame(s: str) -> bool:
    t = s.lstrip()
    i = 0
    while i < len(t) and _digito(t[i]):
        i += 1
    if i == 0 or i >= len(t) or t[i] != ":":
        return False
    i += 1
    while i < len(t) and t[i] == " ":
        i += 1
    resto = t[i:]
    return resto.startswith("0x") and len(resto) > 2 and _hex(resto[2])


def _lstrip(s: str) -> str:
    return s.lstrip()


def flavor_for(linha: str) -> str | None:
    t = _lstrip(linha)
    if t.startswith("Traceback (most recent call last)") or is_python_file_frame(t):
        return "python"
    if is_dotnet_opener(t):
        return "dotnet"
    if is_js_at_frame(t):
        return "js"
    if is_java_at_frame(t):
        return "java"
    if t.startswith("--> ") and has_line_col_suffix(t):
        return "rust_error"
    if is_rust_panic_opener(t) or t.startswith("stack backtrace:") or is_rust_backtrace_frame(linha):
        return "rust_backtrace"
    if is_go_panic_opener(linha):
        return "go"
    return None


def is_dotnet_exception_head(t: str) -> bool:
    if ":" not in t:
        return False
    cabeca = t[:t.index(":")]
    return (cabeca.endswith("Exception") and "." in cabeca
            and all(_alnum(c) or c in "._`+" for c in cabeca))


def is_java_more_summary(t: str) -> bool:
    if not t.startswith("... "):
        return False
    resto = t[4:]
    d = 0
    while d < len(resto) and _digito(resto[d]):
        d += 1
    return d > 0 and resto[d:].strip() == "more"


def terminates(sabor: str, linha: str, ate_agora: int) -> bool:
    t = _lstrip(linha)
    if sabor == "python":
        recuado_ou_vazio = linha.startswith((" ", "\t")) or linha == ""
        continua = (t.startswith("Traceback") or t.startswith("File ") or t.startswith("During handling")
                    or t.startswith("The above exception"))
        if recuado_ou_vazio or continua:
            return False
        return not (t[:1].isupper())
    if sabor == "js":
        return not t.startswith("at ") and linha != ""
    if sabor == "java":
        cadeia = t.startswith("Caused by:") or t.startswith("Suppressed:") or is_java_more_summary(t)
        return not t.startswith("at ") and not cadeia and linha != ""
    if sabor == "dotnet":
        if linha == "":
            return False
        continua = (t.startswith("at ") or t.startswith("--->") or t.startswith("--- End of")
                    or is_dotnet_exception_head(t))
        return not continua
    if sabor == "rust_error":
        return not t.startswith("--> ") and linha != ""
    if sabor == "rust_backtrace":
        if linha == "" or ate_agora == 1:
            return False
        e_quadro = bool(t) and _digito(t[0])
        continua = (linha.startswith((" ", "\t")) or t.startswith("stack backtrace:")
                    or t.startswith("note: run with"))
        return not e_quadro and not continua
    if sabor == "go":
        if linha == "":
            return False
        continua = (linha.startswith("\t") or is_goroutine_header(linha) or is_go_call_frame(linha)
                    or linha.startswith("panic: ") or linha.startswith("fatal error: ")
                    or linha.startswith("[signal "))
        return not continua
    return True


# ─── colapso de quadros ─────────────────────────────────────────────────

def is_frame_line(linha: str) -> bool:
    t = _lstrip(linha)
    return (t.startswith("at ") or (t.startswith('File "') and '", line ' in t)
            or is_rust_backtrace_frame(linha) or is_go_file_frame(linha) or is_go_call_frame(linha))


def is_chain_head_line(linha: str) -> bool:
    t = _lstrip(linha)
    return t.startswith(("Caused by:", "Suppressed:", "... ", "--->", "--- End of", "During handling",
                         "The above exception"))


_PREFIXOS_RUNTIME = ("at java.", "at jdk.", "at sun.", "at javax.", "at scala.", "at System.",
                     "at Microsoft.", "runtime.", "created by runtime.")
_MARCAS_RUNTIME = ("site-packages/", "/usr/lib/python", "lib/python3.", "node:internal/", "node_modules/",
                   "(internal/", "core::", "std::", "alloc::", "rust_begin_unwind", "__rust_", "/rustc/",
                   "/usr/local/go/src/", "/libexec/src/runtime/")


def is_runtime_frame(linha: str) -> bool:
    return _lstrip(linha).startswith(_PREFIXOS_RUNTIME) or any(m in linha for m in _MARCAS_RUNTIME)


@dataclass(eq=False)
class LogLine:
    line_number: int
    content: str
    level: str = "unknown"
    is_stack_trace: bool = False
    is_summary: bool = False
    score: float = 0.0


def collapse_trace_frames(pilha: list[LogLine], head_frames: int, app_frames: int):
    mantidas: list[LogLine] = []
    descartadas: list[int] = []
    vistos = app = 0
    inicio = None
    tamanho = 0
    anterior_descartada = False

    def esvaziar():
        nonlocal inicio, tamanho
        if inicio is not None:
            marca = LogLine(inicio, f"      [... {tamanho} frames collapsed]")
            marca.score = 0.8
            marca.is_stack_trace = True
            mantidas.append(marca)
            inicio = None
            tamanho = 0

    for l in pilha:
        if is_frame_line(l.content) and not is_chain_head_line(l.content):
            vistos += 1
            runtime = is_runtime_frame(l.content)
            if vistos <= head_frames or (not runtime and app < app_frames):
                if not runtime:
                    app += 1
                esvaziar()
                mantidas.append(l)
                anterior_descartada = False
            else:
                if inicio is None:
                    inicio = l.line_number
                tamanho += 1
                descartadas.append(l.line_number)
                anterior_descartada = True
        elif anterior_descartada and l.content.startswith((" ", "\t")) and not is_chain_head_line(l.content):
            tamanho += 1
            descartadas.append(l.line_number)
        else:
            esvaziar()
            mantidas.append(l)
            anterior_descartada = False
    esvaziar()
    return mantidas, descartadas


# ─── resumo ─────────────────────────────────────────────────────────────

def is_summary_line(linha: str) -> bool:
    if linha.startswith("===") or linha.startswith("---"):
        return True
    d = 0
    while d < len(linha) and _digito(linha[d]):
        d += 1
    if d > 0 and linha[d:].startswith(" "):
        resto = linha[d + 1:]
        if resto.startswith(("passed", "failed", "skipped", "error", "warning")):
            return True
    for p in ("Test ", "Tests ", "Tests:", "Test:", "Suite ", "Suites ", "Suites:", "Suite:"):
        if linha.startswith(p):
            resto = linha[len(p):]
            primeiro = next((c for c in resto if not c.isspace()), None)
            return primeiro is not None and _digito(primeiro)
    if linha.startswith(("TOTAL", "Total", "Summary")):
        return True
    for p in ("Build", "Compile", "Test"):
        if linha.startswith(p) and any(o in linha for o in ("succeeded", "failed", "complete")):
            return True
    return False


@dataclass
class _Sumario:
    entries: dict = field(default_factory=dict)
    totals_lines: set = field(default_factory=set)
    first_header: int | None = None


def scan_pytest_short_summary(linhas: list[str]) -> _Sumario:
    s = _Sumario()
    dentro = False
    for n, linha in enumerate(linhas):
        rec = linha[:-1] if linha.endswith("\r") else linha
        if rec.startswith("==="):
            abre = rec.endswith("===") and "short test summary info" in rec
            if abre:
                if s.first_header is None:
                    s.first_header = n
            elif dentro:
                s.totals_lines.add(n)
            dentro = abre
            continue
        if not dentro:
            continue
        resto = None
        if linha.startswith("FAILED "):
            resto = linha[7:]
        elif linha.startswith("ERROR "):
            resto = linha[6:]
        if resto is not None:
            node = (resto.split(" - ", 1)[0] if " - " in resto else resto).strip()
            if node:
                s.entries[n] = node
    return s


def pytest_cap_reserve(log_lines: list[LogLine], scan: _Sumario) -> set:
    reservadas = set(scan.totals_lines)
    for l in log_lines:
        if scan.first_header is not None and l.line_number >= scan.first_header:
            break
        if l.content.startswith("E "):
            reservadas.add(l.line_number)
            break
    return reservadas


def extract_error_label(linha: str) -> str | None:
    t = linha.strip()
    if t.startswith("error["):
        resto = t[6:]
        if "]" in resto:
            cod = resto[:resto.index("]")]
            if cod and all(_alnum(c) for c in cod):
                return cod
    depois = t[2:].lstrip() if t.startswith("E ") else t
    if ":" not in depois:
        return None
    cabeca = depois[:depois.index(":")]
    ok = (bool(cabeca) and all(_alnum(c) or c in "_." for c in cabeca) and cabeca[0].isascii()
          and cabeca[0].isupper() and cabeca.endswith(("Error", "Exception", "Warning")))
    return cabeca if ok else None


def extract_source_file(linha: str) -> str | None:
    t = linha.strip()
    if t.startswith('File "'):
        resto = t[6:]
        if '"' in resto:
            return resto[:resto.index('"')]
    if "--> " not in t:
        return None
    resto = t[t.index("--> ") + 4:]
    parte = resto.split(":")[0]
    return parte if parte and "." in parte else None


def summarize_omitted(todas: list[LogLine], escolhidas: list[LogLine]) -> str:
    mantidas = {l.line_number for l in escolhidas}
    tipos_mantidos = {x for x in (extract_error_label(l.content) for l in escolhidas) if x}
    arquivos_mantidos = {x for x in (extract_source_file(l.content) for l in escolhidas) if x}
    tipos, arquivos = set(), set()
    for l in todas:
        if l.line_number in mantidas:
            continue
        r = extract_error_label(l.content)
        if r and r not in tipos_mantidos:
            tipos.add(r)
        a = extract_source_file(l.content)
        if a and a not in arquivos_mantidos:
            arquivos.add(a)
    partes = []
    if arquivos:
        partes.append(f"{len(arquivos)} file{'' if len(arquivos) == 1 else 's'}")
    if tipos:
        nomes = sorted(tipos)
        mais = ", ..." if len(nomes) > 5 else ""
        partes.append(f"{len(nomes)} exception type{'' if len(nomes) == 1 else 's'} ({', '.join(nomes[:5])}{mais})")
    return f": {', '.join(partes)}" if partes else ""


# ─── compressor ─────────────────────────────────────────────────────────

@dataclass
class LogCompressorConfig:
    max_errors: int = 10
    error_context_lines: int = 3
    keep_first_error: bool = True
    keep_last_error: bool = True
    max_stack_traces: int = 3
    stack_trace_max_lines: int = 20
    max_warnings: int = 5
    dedupe_warnings: bool = True
    keep_summary_lines: bool = True
    max_total_lines: int = 100
    enable_ccr: bool = True
    min_lines_for_ccr: int = 50
    min_compression_ratio_for_ccr: float = 0.5
    collapse_runtime_frames: bool = True
    trace_head_frames: int = 3
    trace_app_frames: int = 5


@dataclass
class LogCompressionResult:
    compressed: str
    original: str
    original_line_count: int
    compressed_line_count: int
    format_detected: str
    compression_ratio: float
    cache_key: str | None
    stats: dict


def score_log_line(l: LogLine) -> float:
    """Em f32, soma a soma, como o Rust (arredondar o dobro depois de cada soma e exato)."""
    base = {"error": 1.0, "fail": 1.0, "warn": 0.5, "info": 0.1, "unknown": 0.1, "debug": 0.05,
            "trace": 0.02}[l.level]
    s = _f32(_f32(base) + _f32(0.3 if l.is_stack_trace else 0.0))
    s = _f32(s + _f32(0.4 if l.is_summary else 0.0))
    return min(s, 1.0)


_DIG, _HEXRE, _CAM = re.compile(r"\d+"), re.compile(r"0x[0-9a-fA-F]+"), re.compile(r"/[\w/]+/")


def normalize_for_dedupe(c: str) -> str:
    corte = min([i for i in (c.find(":"), c.find("=")) if i >= 0], default=len(c))
    sufixo = _CAM.sub("/PATH/", _HEXRE.sub("ADDR", _DIG.sub("N", c[corte:])))
    return c[:corte] + sufixo


def _f32(x: float) -> float:
    """A pontuacao e f32 no Rust; a ordenacao por pontuacao compara f32."""
    import struct
    return struct.unpack("f", struct.pack("f", x))[0]


class LogCompressor:
    def __init__(self, config: LogCompressorConfig | None = None):
        self.config = config or LogCompressorConfig()

    def compress(self, content: str, bias: float = 1.0, store=None) -> LogCompressionResult:
        cfg = self.config
        linhas = content.split("\n")
        total = len(linhas)
        if total < cfg.min_lines_for_ccr:
            return LogCompressionResult(content, content, total, total, "generic", 1.0, None, {})
        fmt = detect_format(linhas)
        log_lines = self.parse_lines(linhas)
        escolhidas = self.select_lines(log_lines, bias)
        corpo, stats = self.format_output(escolhidas, log_lines)
        comprimido = corpo
        razao = len(comprimido.encode("utf-8")) / max(len(content.encode("utf-8")), 1)
        chave = None
        if cfg.enable_ccr and razao < cfg.min_compression_ratio_for_ccr and store is not None:
            chave = hashlib.md5(content.encode("utf-8")).hexdigest()[:24]
            store.put(chave, content)
            comprimido += (f"\n[{total} lines compressed to {len(escolhidas)}"
                           f"{summarize_omitted(log_lines, escolhidas)}. Retrieve more: hash={chave}]")
        return LogCompressionResult(comprimido, content, total, len(escolhidas), fmt, razao, chave, stats)

    def parse_lines(self, linhas: list[str]) -> list[LogLine]:
        cfg = self.config
        saida = []
        ativo = None
        n_trace = 0
        resumo = scan_pytest_short_summary(linhas).entries
        for i, linha in enumerate(linhas):
            e = LogLine(i, linha)
            e.level = classify(linha)
            e.is_summary = is_summary_line(linha) or i in resumo
            if ativo is not None:
                if n_trace >= cfg.stack_trace_max_lines or terminates(ativo, linha, n_trace):
                    teto = n_trace >= cfg.stack_trace_max_lines
                    anterior = ativo
                    ativo, n_trace = None, 0
                    novo = flavor_for(linha)
                    if novo is not None:
                        ativo, n_trace, e.is_stack_trace = novo, 1, True
                    elif teto and not terminates(anterior, linha, 2):
                        ativo, n_trace, e.is_stack_trace = anterior, 1, True
                else:
                    e.is_stack_trace = True
                    n_trace += 1
            else:
                novo = flavor_for(linha)
                if novo is not None:
                    ativo, n_trace, e.is_stack_trace = novo, 1, True
            e.score = score_log_line(e)
            saida.append(e)
        return saida

    def select_with_first_last(self, linhas: list[LogLine], maximo: int) -> list[LogLine]:
        if len(linhas) <= maximo:
            return list(linhas)
        out, vistos = [], set()

        def por(l):
            if l.line_number not in vistos:
                vistos.add(l.line_number)
                out.append(l)
        if self.config.keep_first_error:
            por(linhas[0])
        if self.config.keep_last_error:
            por(linhas[-1])
        if maximo - len(out) > 0:
            for l in sorted(linhas, key=lambda x: (-x.score, x.line_number)):
                if l.line_number not in vistos:
                    por(l)
                    if len(out) >= maximo:
                        break
        return out

    def dedupe_similar(self, linhas: list[LogLine]) -> list[LogLine]:
        vistos, out = set(), []
        for l in linhas:
            k = normalize_for_dedupe(l.content)
            if k not in vistos:
                vistos.add(k)
                out.append(l)
        return out

    def select_lines(self, log_lines: list[LogLine], bias: float) -> list[LogLine]:
        cfg = self.config
        textos = [l.content for l in log_lines]
        resumo = scan_pytest_short_summary(textos)
        maximo = compute_optimal_k(textos, bias, 10, cfg.max_total_lines)
        erros, falhas, avisos, sumarios, pilhas, atual = [], [], [], [], [], []
        for l in log_lines:
            if l.level == "error":
                erros.append(l)
            elif l.level == "fail":
                falhas.append(l)
            elif l.level == "warn":
                avisos.append(l)
            if l.is_stack_trace:
                atual.append(l)
            elif atual:
                pilhas.append(atual)
                atual = []
            if l.is_summary:
                sumarios.append(l)
        if atual:
            pilhas.append(atual)

        escolhidas: dict[int, LogLine] = {}

        def por(l):
            escolhidas.setdefault(l.line_number, l)  # BTreeSet: a primeira com o numero fica
        for l in self.select_with_first_last(erros, cfg.max_errors):
            por(l)
        for l in self.select_with_first_last(falhas, cfg.max_errors):
            por(l)
        if cfg.dedupe_warnings:
            avisos = self.dedupe_similar(avisos)
        for l in avisos[:cfg.max_warnings]:
            por(l)
        colapsadas: set = set()
        for pilha in pilhas[:cfg.max_stack_traces]:
            if cfg.collapse_runtime_frames and len(pilha) > cfg.stack_trace_max_lines:
                mantidas, descartadas = collapse_trace_frames(pilha, cfg.trace_head_frames, cfg.trace_app_frames)
                colapsadas.update(descartadas)
                for l in mantidas[:cfg.stack_trace_max_lines]:
                    por(l)
            else:
                for l in pilha[:cfg.stack_trace_max_lines]:
                    por(l)
        if cfg.keep_summary_lines:
            for l in sumarios:
                por(l)
        indices = set(escolhidas)
        contexto = set()
        for idx in indices:
            for i in range(max(0, idx - cfg.error_context_lines), min(idx + cfg.error_context_lines + 1, len(log_lines))):
                if i != idx:
                    contexto.add(i)
        for idx in sorted(contexto):
            if idx not in indices and idx < len(log_lines) and idx not in colapsadas:
                por(log_lines[idx])
        ordenadas = [escolhidas[k] for k in sorted(escolhidas)]
        if len(ordenadas) > maximo:
            reservadas = (pytest_cap_reserve(log_lines, resumo)
                          if cfg.keep_summary_lines and resumo.entries else set())
            presentes = {l.line_number for l in ordenadas}
            for l in log_lines:
                if l.line_number in reservadas and l.line_number not in presentes:
                    ordenadas.append(l)
                    presentes.add(l.line_number)
            ordenadas.sort(key=lambda l: (
                0 if l.line_number in reservadas else 1, -l.score,
                (0 if l.line_number in resumo.entries else 1) if cfg.keep_summary_lines else 0,
                l.line_number))
            ordenadas = sorted(ordenadas[:maximo], key=lambda l: l.line_number)
        return ordenadas

    def format_output(self, escolhidas: list[LogLine], todas: list[LogLine]):
        resumo = scan_pytest_short_summary([l.content for l in todas]).entries
        numeros = {l.line_number for l in escolhidas}
        omitidos_ids = [resumo[k] for k in sorted(resumo) if k not in numeros]
        stats = {k: sum(1 for l in todas if l.level == n) for k, n in
                 (("errors", "error"), ("fails", "fail"), ("warnings", "warn"), ("info", "info"))}
        stats["total"] = len(todas)
        stats["selected"] = len(escolhidas)
        stats = dict(sorted(stats.items()))
        saida = [l.content for l in escolhidas]
        omitidas = max(0, len(todas) - len(escolhidas))
        if omitidas > 0:
            partes = [f"{stats[k]} {rot}" for rot, k in (("ERROR", "errors"), ("FAIL", "fails"),
                                                          ("WARN", "warnings"), ("INFO", "info")) if stats[k] > 0]
            if partes:
                nomes = ""
                if omitidos_ids:
                    mostrados = ", ".join(omitidos_ids[:5])
                    extra = len(omitidos_ids) - 5
                    nomes = f"; omitted: {mostrados}, +{extra} more" if extra > 0 else f"; omitted: {mostrados}"
                saida.append(f"[{omitidas} lines omitted: {', '.join(partes)}{nomes}]")
        return "\n".join(saida), stats
