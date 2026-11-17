"""Porte de `crates/headroom-core/src/transforms/search_compressor.rs` (Headroom, Apache 2.0).

Comprime saida de grep, ripgrep e ag (`arquivo:linha:conteudo`, e o `-` de
contexto do ripgrep): pontua cada achado (palavras do pedido, erro/aviso/
importancia, palavras-chave da config), ordena arquivos pela soma, limita a
`max_files`, decide o total pelo `compute_optimal_k`, e em cada arquivo guarda
o primeiro, o ultimo e os de maior pontuacao. Inclui as duas correcoes do
Rust sobre o Python: caminho de Windows (`C:\\...`) e arquivo com `-` no nome.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

from .adaptativo import compute_optimal_k
from .sinais import categoria


def _f32(x: float) -> float:
    return struct.unpack("f", struct.pack("f", x))[0]


def _ascii_lower(s: str) -> str:
    return s.translate(_TABELA)


_TABELA = {c: c + 32 for c in range(ord("A"), ord("Z") + 1)}
_ESPACO_ASCII = " \t\n\x0c\r"


def _cjk(c: str) -> bool:
    o = ord(c)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF)


def _bigramas_cjk(texto: str) -> set[str]:
    saida, run = set(), []
    for c in list(texto) + [None]:
        if c is not None and _cjk(c):
            run.append(c)
        else:
            for i in range(len(run) - 1):
                saida.add(run[i] + run[i + 1])
            run = []
    return saida


@dataclass
class SearchCompressorConfig:
    max_matches_per_file: int = 5
    always_keep_first: bool = True
    always_keep_last: bool = True
    max_total_matches: int = 30
    max_files: int = 15
    context_keywords: list = field(default_factory=list)
    boost_errors: bool = True
    enable_ccr: bool = True
    min_matches_for_ccr: int = 10
    min_compression_ratio_for_ccr: float = 0.8
    group_by_file: bool = False


@dataclass
class SearchMatch:
    file: str
    line_number: int
    content: str
    score: float = 0.0


@dataclass
class SearchCompressionResult:
    compressed: str
    original: str
    original_match_count: int
    compressed_match_count: int
    files_affected: int
    compression_ratio: float
    cache_key: str | None
    summaries: dict


# ─── leitura das linhas ─────────────────────────────────────────────────

def _tem_ponto_de_extensao(tok: str) -> bool:
    for i, c in enumerate(tok):
        if c != "." or i + 1 == len(tok):
            continue
        cauda = tok[i + 1:]
        fim = next((k for k, ch in enumerate(cauda) if not (ch.isascii() and ch.isalnum())), len(cauda))
        ext = cauda[:fim]
        if 1 <= len(ext.encode("utf-8")) <= 8 and any(ch.isascii() and ch.isalpha() for ch in ext):
            return True
    return False


def _ultimo_segmento_tem_extensao(caminho: str) -> bool:
    import re
    return _tem_ponto_de_extensao(re.split(r"[/\\]", caminho)[-1])


def _caminho_continua(resto: str) -> bool:
    partes = resto.split()
    if not partes:
        return False
    tok = partes[0]
    return "/" in tok or "\\" in tok or _tem_ponto_de_extensao(tok)


def _marca(linha: str, nivel: str):
    b = linha
    inicio = 2 if (len(b) >= 3 and b[0].isascii() and b[0].isalpha() and b[1] == ":" and b[2] in "\\/") else 0
    primeira = escolhida = None
    i = inicio
    while i < len(b):
        if nivel == "colon":
            e_sep = b[i] == ":"
        elif nivel == "dash":
            e_sep = b[i] == "-"
        else:
            e_sep = b[i] in ":-"
        if e_sep:
            if i > 0 and b[i - 1] in ":-":
                i += 1
                continue
            if nivel != "permissive" and any(c in _ESPACO_ASCII for c in b[:i]):
                break
            d0 = i + 1
            j = d0
            while j < len(b) and "0" <= b[j] <= "9":
                j += 1
            fecha = j > d0 and j < len(b) and (b[j] in ":-" if nivel == "permissive" else b[j] == b[i])
            if fecha:
                if i == 0:
                    return None
                if primeira is None:
                    primeira = (i, d0, j)
                if nivel != "dash":
                    escolhida = (i, d0, j)
                    break
                if _ultimo_segmento_tem_extensao(b[:i]) or not _caminho_continua(b[j + 1:]):
                    escolhida = (i, d0, j)
                    break
                i = j + 1
                continue
        i += 1
    m = escolhida or primeira
    return None if m is None else (m, escolhida is not None)


def parse_match_line(linha: str):
    dois = _marca(linha, "colon")
    traco = _marca(linha, "dash")
    traco_vence = dois is not None and traco is not None and traco[1] and dois[0][0] > traco[0][2]
    if traco_vence:
        m = traco
    else:
        m = dois or traco or _marca(linha, "permissive")
    if m is None:
        return None
    fim_caminho, d0, d1 = m[0]
    try:
        n = int(linha[d0:d1])
    except ValueError:
        return None
    if n >= 2 ** 64:
        return None
    return linha[:fim_caminho], n, linha[d1 + 1:]


# ─── compressor ─────────────────────────────────────────────────────────

class SearchCompressor:
    def __init__(self, config: SearchCompressorConfig | None = None):
        self.config = config or SearchCompressorConfig()

    def parse(self, content: str) -> dict[str, list[SearchMatch]]:
        saida: dict[str, list[SearchMatch]] = {}
        for bruto in content.split("\n"):
            linha = bruto.strip()
            if not linha:
                continue
            r = parse_match_line(linha)
            if r is not None:
                saida.setdefault(r[0], []).append(SearchMatch(r[0], r[1], r[2]))
        return dict(sorted(saida.items(), key=lambda kv: kv[0].encode("utf-8")))

    def score(self, arquivos: dict[str, list[SearchMatch]], contexto: str) -> None:
        ctx = _ascii_lower(contexto)
        palavras = {w for w in ctx.split() if len(w) > 2} | _bigramas_cjk(ctx)
        palavras = sorted(palavras, key=lambda w: w.encode("utf-8"))
        kws = [_ascii_lower(k) for k in self.config.context_keywords]
        for ms in arquivos.values():
            for m in ms:
                s = _f32(0.0)
                baixo = _ascii_lower(m.content)
                for w in palavras:
                    if w in baixo:
                        s = _f32(s + _f32(0.3))
                if self.config.boost_errors:
                    c = categoria(m.content, "search")
                    s = _f32(s + _f32({"error": 0.5, "warning": 0.4, "importance": 0.3}.get(c, 0.0)))
                for k in kws:
                    if k in baixo:
                        s = _f32(s + _f32(0.4))
                m.score = min(s, 1.0)

    @staticmethod
    def _soma(ms: list[SearchMatch]) -> float:
        t = _f32(0.0)
        for m in ms:
            t = _f32(t + m.score)
        return t

    def select(self, arquivos: dict[str, list[SearchMatch]], bias: float) -> dict[str, list[SearchMatch]]:
        cfg = self.config
        ordem = sorted(arquivos.items(), key=lambda kv: -self._soma(kv[1]))[:cfg.max_files]
        todas = [f"{f}:{m.line_number}:{m.content}" for f, ms in ordem for m in ms]
        alvo = compute_optimal_k(todas, bias, 5, cfg.max_total_matches)
        escolhidas: dict[str, list[SearchMatch]] = {}
        total = 0
        for f, ms in ordem:
            if total >= alvo:
                continue
            por_pontos = sorted(ms, key=lambda m: (-m.score, m.line_number))
            sel, vistos = [], set()
            teto = min(cfg.max_matches_per_file, max(0, alvo - total))

            def por(m):
                k = (m.line_number, m.content)
                if k not in vistos:
                    vistos.add(k)
                    sel.append(m)
            if cfg.always_keep_first and ms and len(sel) < teto:
                por(ms[0])
            if cfg.always_keep_last and len(ms) > 1 and len(sel) < teto:
                por(ms[-1])
            for m in por_pontos:
                if len(sel) >= teto:
                    break
                por(m)
            sel.sort(key=lambda m: m.line_number)
            total += len(sel)
            escolhidas[f] = sel
        return dict(sorted(escolhidas.items(), key=lambda kv: kv[0].encode("utf-8")))

    def format(self, escolhidas, originais):
        linhas, resumos = [], {}
        for f, ms in escolhidas.items():
            if self.config.group_by_file:
                if linhas:
                    linhas.append("")
                linhas.append(f)
                linhas += [f"{m.line_number}:{m.content}" for m in ms]
            else:
                linhas += [f"{m.file}:{m.line_number}:{m.content}" for m in ms]
            orig = originais.get(f)
            if orig is not None and len(orig) > len(ms):
                omitidos = len(orig) - len(ms)
                r = (f"[... and {omitidos} more matches]" if self.config.group_by_file
                     else f"[... and {omitidos} more matches in {f}]")
                linhas.append(r)
                resumos[f] = r
        return "\n".join(linhas), resumos

    def compress(self, content: str, context: str = "", bias: float = 1.0, store=None) -> SearchCompressionResult:
        cfg = self.config
        arquivos = self.parse(content)
        if not arquivos:
            return SearchCompressionResult(content, content, 0, 0, 0, 1.0, None, {})
        original = sum(len(ms) for ms in arquivos.values())
        self.score(arquivos, context)
        escolhidas = self.select(arquivos, bias)
        corpo, resumos = self.format(escolhidas, arquivos)
        n = sum(len(ms) for ms in escolhidas.values())
        razao = len(corpo.encode("utf-8")) / max(len(content.encode("utf-8")), 1)
        chave = None
        if (cfg.enable_ccr and original >= cfg.min_matches_for_ccr
                and razao < cfg.min_compression_ratio_for_ccr and store is not None):
            chave = hashlib.md5(content.encode("utf-8")).hexdigest()[:24]
            store.put(chave, content)
            corpo += f"\n[{original} matches compressed to {n}. Retrieve more: hash={chave}]"
        return SearchCompressionResult(corpo, content, original, n, len(arquivos), razao, chave, resumos)
