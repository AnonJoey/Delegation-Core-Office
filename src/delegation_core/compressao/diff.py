"""Porte de `crates/headroom-core/src/transforms/diff_compressor.rs` (Headroom, Apache 2.0).

Comprime `git diff`: le arquivos e hunks, limita arquivos (`max_files`, os de
mais mudancas ficam) e hunks por arquivo (primeiro, ultimo e os de maior
pontuacao no meio: densidade de mudanca, palavras do pedido e padroes de
prioridade como error/security/todo), corta contexto a `max_context_lines` em
volta de cada `+`/`-`, e acrescenta o resumo `[N files changed, +A -D lines,
H hunks omitted]`. Se sobrar menos de 80% das linhas, o original vai para a
guarda CCR e o resultado termina com `Retrieve full diff: hash=<chave>`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

_HUNK = re.compile(r"^(?:@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@"
                   r"|@@@ -\d+(?:,\d+)? -\d+(?:,\d+)? \+\d+(?:,\d+)? @@@"
                   r"|@@@@ -\d+(?:,\d+)? -\d+(?:,\d+)? -\d+(?:,\d+)? \+\d+(?:,\d+)? @@@@)(.*)$")
_NOVA_FAIXA = re.compile(r"\+(\d+)")
_CAB = [re.compile(r"^diff --git a/(.+) b/(.+)$"), re.compile(r"^diff --combined (.+)$"),
        re.compile(r"^diff --cc (.+)$")]
_VELHO = re.compile(r"^--- (a/(.+)|/dev/null)$")
_NOVO = re.compile(r"^\+\+\+ (b/(.+)|/dev/null)$")
_BINARIO = re.compile(r"^Binary files .+ differ$")
_PRIORIDADE = [re.compile(r"(?i)\b(error|exception|fail(?:ed|ure)?|fatal|critical|crash|panic)\b"),
               re.compile(r"(?i)\b(important|note|todo|fixme|hack|xxx|bug|fix)\b"),
               re.compile(r"(?i)\b(security|auth|password|secret|token)\b")]


@dataclass
class DiffCompressorConfig:
    max_context_lines: int = 2
    max_hunks_per_file: int = 10
    max_files: int = 20
    always_keep_additions: bool = True
    always_keep_deletions: bool = True
    enable_ccr: bool = True
    min_lines_for_ccr: int = 50
    min_compression_ratio_for_ccr: float = 0.8


@dataclass
class DiffCompressionResult:
    compressed: str
    original_line_count: int
    compressed_line_count: int
    files_affected: int = 0
    additions: int = 0
    deletions: int = 0
    hunks_kept: int = 0
    hunks_removed: int = 0
    cache_key: str | None = None


@dataclass
class _Hunk:
    header: str
    lines: list = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    context_lines: int = 0
    score: float = 0.0


@dataclass
class _Arquivo:
    header: str
    old_file: str = ""
    new_file: str = ""
    hunks: list = field(default_factory=list)
    is_binary: bool = False
    is_new_file: bool = False
    is_deleted_file: bool = False
    is_renamed: bool = False
    rename_lines: list = field(default_factory=list)

    def mudancas(self) -> int:
        return sum(h.additions for h in self.hunks) + sum(h.deletions for h in self.hunks)


def _cjk(c: str) -> bool:
    o = ord(c)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF)


def _bigramas_cjk(texto: str) -> list[str]:
    saida, run = set(), []
    for c in texto + "\x00":
        if c != "\x00" and _cjk(c):
            run.append(c)
        else:
            for i in range(len(run) - 1):
                saida.add(run[i] + run[i + 1])
            run = []
    return sorted(saida)


def parse_diff(linhas: list[str]):
    arquivos, atual, hunk, antes = [], None, None, []
    for linha in linhas:
        if any(r.match(linha) for r in _CAB):
            if hunk is not None and atual is not None:
                atual.hunks.append(hunk)
            hunk = None
            if atual is not None:
                arquivos.append(atual)
            atual = _Arquivo(linha)
            continue
        if atual is None:
            antes.append(linha)
            continue
        if linha.startswith("new file mode"):
            atual.is_new_file = True
        elif linha.startswith("deleted file mode"):
            atual.is_deleted_file = True
        elif linha.startswith(("rename ", "similarity ", "copy ", "dissimilarity ")):
            atual.is_renamed = True
            atual.rename_lines.append(linha)
        elif _BINARIO.match(linha):
            atual.is_binary = True
        if _VELHO.match(linha):
            atual.old_file = linha
            continue
        if _NOVO.match(linha):
            atual.new_file = linha
            continue
        if _HUNK.match(linha):
            if hunk is not None:
                atual.hunks.append(hunk)
            hunk = _Hunk(linha)
            continue
        if hunk is not None:
            if linha.startswith("+") and not linha.startswith("+++"):
                hunk.additions += 1
            elif linha.startswith("-") and not linha.startswith("---"):
                hunk.deletions += 1
            elif linha.startswith(" ") or linha == "":
                hunk.context_lines += 1
            hunk.lines.append(linha)
    if hunk is not None and atual is not None:
        atual.hunks.append(hunk)
    if atual is not None:
        arquivos.append(atual)
    return antes, arquivos


def _pontuar(arquivos: list[_Arquivo], contexto: str) -> None:
    ctx = contexto.lower()
    palavras = ctx.split()
    bigramas = _bigramas_cjk(ctx)
    for f in arquivos:
        for h in f.hunks:
            s = min((h.additions + h.deletions) * 0.03, 0.3)
            texto = "\n".join(h.lines).lower()
            for w in palavras:
                if len(w.encode("utf-8")) > 2 and w in texto:
                    s += 0.2
            for bg in bigramas:
                if bg in texto:
                    s += 0.2
            for p in _PRIORIDADE:
                if p.search(texto):
                    s += 0.3
                    break
            h.score = min(s, 1.0)


def _linha_do_header(header: str) -> int:
    m = _NOVA_FAIXA.search(header)
    return int(m.group(1)) if m else 0


def _escolher(hunks: list[_Hunk], maximo: int):
    if len(hunks) <= maximo:
        return list(hunks), []
    indexados = list(enumerate(hunks))
    primeiro = indexados.pop(0)
    ultimo = indexados.pop() if indexados else None
    vagas = max(0, maximo - (2 if ultimo is not None else 1))
    meio = sorted(indexados, key=lambda x: -x[1].score)
    mantidos, largados = meio[:vagas], [h for _, h in meio[vagas:]]
    escolhidos = [primeiro] + mantidos + ([ultimo] if ultimo is not None else [])
    escolhidos.sort(key=lambda x: _linha_do_header(x[1].header))
    return [h for _, h in escolhidos], largados


def _reduzir(h: _Hunk, ctx: int) -> _Hunk:
    mudancas = [i for i, l in enumerate(h.lines) if l.startswith(("+", "-"))]
    if not mudancas:
        n = min(ctx, len(h.lines))
        return _Hunk(h.header, h.lines[:n], 0, 0, n, h.score)
    manter = set()
    for p in mudancas:
        manter.update(range(max(0, p - ctx), min(p + ctx + 1, len(h.lines))))
    manter.update(i for i, l in enumerate(h.lines) if l.startswith("\\"))
    novo = _Hunk(h.header, score=h.score)
    for i in sorted(manter):
        l = h.lines[i]
        novo.lines.append(l)
        if l.startswith("+"):
            novo.additions += 1
        elif l.startswith("-"):
            novo.deletions += 1
        else:
            novo.context_lines += 1
    return novo


class DiffCompressor:
    def __init__(self, config: DiffCompressorConfig | None = None):
        self.config = config or DiffCompressorConfig()

    def compress(self, content: str, context: str = "", store=None) -> DiffCompressionResult:
        cfg = self.config
        linhas = content.split("\n")
        total = len(linhas)
        if total < cfg.min_lines_for_ccr:
            return DiffCompressionResult(content, total, total)
        antes, arquivos = parse_diff(linhas)
        if not arquivos:
            return DiffCompressionResult(content, total, total)
        _pontuar(arquivos, context)
        if len(arquivos) > cfg.max_files:
            arquivos = sorted(arquivos, key=lambda f: -f.mudancas())[:cfg.max_files]
        adicoes = delecoes = mantidos = removidos = 0
        saida_arquivos = []
        for f in arquivos:
            adicoes += sum(h.additions for h in f.hunks)
            delecoes += sum(h.deletions for h in f.hunks)
            original = len(f.hunks)
            escolhidos, _ = _escolher(f.hunks, cfg.max_hunks_per_file)
            novos = [_reduzir(h, cfg.max_context_lines) for h in escolhidos]
            mantidos += len(novos)
            removidos += original - len(novos)
            f.hunks = novos
            saida_arquivos.append(f)
        out = list(antes)
        for f in saida_arquivos:
            out.append(f.header)
            out.extend(f.rename_lines)
            if f.is_new_file:
                out.append("new file mode 100644")
            elif f.is_deleted_file:
                out.append("deleted file mode 100644")
            if f.is_binary:
                out.append("Binary files differ")
                continue
            if f.old_file:
                out.append(f.old_file)
            if f.new_file:
                out.append(f.new_file)
            for h in f.hunks:
                out.append(h.header)
                out.extend(h.lines)
        n_arquivos = len(saida_arquivos)
        if removidos > 0 or n_arquivos > 0:
            partes = [f"{n_arquivos} files changed", f"+{adicoes} -{delecoes} lines"]
            if removidos > 0:
                partes.append(f"{removidos} hunks omitted")
            out.append(f"[{', '.join(partes)}]")
        comprimido = "\n".join(out)
        n_comprimido = len(comprimido.split("\n"))
        chave = None
        if cfg.enable_ccr and n_comprimido < total * cfg.min_compression_ratio_for_ccr:
            chave = hashlib.md5(content.encode("utf-8")).hexdigest()[:24]
            comprimido += f"\n[{total} lines compressed to {n_comprimido}. Retrieve full diff: hash={chave}]"
            if store is not None:
                store.put(chave, content)
        return DiffCompressionResult(comprimido, total, n_comprimido, n_arquivos, adicoes, delecoes,
                                     mantidos, removidos, chave)
