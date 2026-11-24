"""Uma porta so: detecta o tipo da saida e manda para o compressor certo.

O ContentRouter do Headroom em escala de delegation-core:

| tipo detectado | compressor | reversivel |
|---|---|---|
| diff | `diff.DiffCompressor` | guarda CCR |
| search | `busca.SearchCompressor` | guarda CCR |
| build (log) | `logs.LogCompressor` | guarda CCR |
| texto, config, tabela, codigo... | `lossless_compaction.compact_lossless` | sem perda |
| texto em prosa (depois do sem perda) | Kompress (ModernBERT, se o modelo estiver em cache) | guarda CCR |
| JSON (array ou objeto com arrays) | `smartcrusher.SmartCrusher`: tabela sem perda ou amostra | guarda CCR |

Antes do compressor com perda, roda a compactacao sem perda do mesmo tipo; se
ela ja resolve, para ali. O tipo pode ser forcado (`kind`).
"""

from __future__ import annotations

import math
import re

from .ccr import Guarda

_TIPOS = ("auto", "diff", "search", "log", "text", "json", "code")
_SEM_PERDA = {"diff": "diff", "search": "search", "build": "log", "log": "log", "text": "text",
              "structured_config": "config"}


_MARCA_CCR = re.compile(r"<<ccr:([0-9a-f]{12})")


def _tokens(t: str) -> int:
    return math.ceil(len(t.encode("utf-8")) / 4)


def _kompress(texto: str, guarda):
    """(comprimido, chave) pelo Kompress, ou None se desligado, sem modelo em cache ou com erro."""
    try:
        from .. import config as _config
        cfg = _config.Config.load()
        if not cfg.kompress_enabled:
            return None
        from .headroom_py.transforms.kompress_compressor import KompressCompressor, KompressConfig
        c = KompressCompressor(KompressConfig(device=cfg.kompress_device, enable_ccr=guarda is not None))
        r = c.compress(texto, allow_download=False)
        return r.compressed, r.cache_key
    except Exception:  # noqa: BLE001 - sem modelo, sem onnxruntime, ou falha: fica o resultado anterior
        return None


def _codigo_ast_ligado() -> bool:
    try:
        from .. import config as _config
        return bool(getattr(_config.Config.load(), "compress_code_ast", False))
    except Exception:  # noqa: BLE001
        return False


def _codigo(texto: str, contexto: str, guarda):
    """(comprimido, chave) pelo compressor de codigo, ou None se ele nao comprimiu ou falhou.

    So aceita saida que o proprio compressor validou como sintaxe valida."""
    try:
        from .headroom_py.transforms.code_compressor import CodeAwareCompressor, CodeCompressorConfig
        c = CodeAwareCompressor(CodeCompressorConfig(enable_ccr=guarda is not None))
        r = c.compress(texto, context=contexto)
        if not r.syntax_valid or r.compressed == texto:
            return None
        return r.compressed, r.cache_key
    except Exception:  # noqa: BLE001 - sem tree-sitter, linguagem sem gramatica ou falha: fica o anterior
        return None


def comprimir(conteudo: str, contexto: str = "", tipo: str = "auto", bias: float = 1.0,
              guardar: bool = True, kompress: bool = True) -> dict:
    from .headroom_py.transforms.content_detector import detect_content_type
    from .headroom_py.transforms.lossless_compaction import compact_lossless
    if tipo not in _TIPOS:
        raise ValueError(f"kind must be one of {', '.join(_TIPOS)}")
    if tipo == "auto":
        d = detect_content_type(conteudo)
        detectado, confianca = d.content_type.value, round(float(d.confidence), 3)
    else:
        detectado, confianca = {"log": "build", "json": "json_array", "code": "source_code"}.get(tipo, tipo), None
    guarda = Guarda() if guardar else None
    chave = None
    compressor = "lossless"
    saida = compact_lossless(conteudo, _SEM_PERDA.get(detectado, "text"))
    if detectado == "diff":
        from .diff import DiffCompressor
        r = DiffCompressor().compress(conteudo, contexto, store=guarda)
        if r.compressed_line_count < r.original_line_count:
            saida, chave, compressor = r.compressed, r.cache_key, "diff"
    elif detectado == "search":
        from .busca import SearchCompressor
        r = SearchCompressor().compress(conteudo, contexto, bias, store=guarda)
        if r.compressed_match_count < r.original_match_count:
            saida, chave, compressor = r.compressed, r.cache_key, "search"
    elif detectado == "build":
        from .logs import LogCompressor
        r = LogCompressor().compress(conteudo, bias, store=guarda)
        if r.compressed_line_count < r.original_line_count:
            saida, chave, compressor = r.compressed, r.cache_key, "log"
    elif detectado == "json_array":
        from .smartcrusher import MemoriaCcr, SmartCrusher
        r = SmartCrusher(store=guarda if guarda is not None else MemoriaCcr()).crush(conteudo, contexto, bias)
        if r.was_modified and _tokens(r.compressed) < _tokens(saida):
            m = _MARCA_CCR.search(r.compressed)
            saida, chave, compressor = r.compressed, (m.group(1) if m else None), "smartcrusher"
    elif detectado == "source_code" and (tipo == "code" or _codigo_ast_ligado()):
        # 6.3.1: compressor por AST do Headroom. Pedido explicito (`kind="code"`) sempre; na deteccao
        # automatica so com `compress_code_ast`, desligado como no original ("use code graph MCP
        # tools instead"). Se ele nao comprimir, o Kompress tenta, como no original.
        r = _codigo(conteudo, contexto, guarda)
        if r is not None and _tokens(r[0]) < _tokens(saida):
            saida, chave, compressor = r[0], r[1], "code"
        elif kompress:
            k = _kompress(saida, guarda)
            if k is not None and _tokens(k[0]) < _tokens(saida):
                saida, chave, compressor = k[0], k[1], "kompress"
    if detectado == "text" and kompress and compressor in ("lossless", "none"):
        r = _kompress(saida, guarda)
        if r is not None and _tokens(r[0]) < _tokens(saida):
            saida, chave, compressor = r[0], r[1], "kompress"
    if _tokens(saida) >= _tokens(conteudo):
        saida, chave, compressor = conteudo, None, "none"
    return {"content_type": detectado, "confidence": confianca, "compressor": compressor,
            "output": saida, "cache_key": chave, "raw_tokens": _tokens(conteudo),
            "shown_tokens": _tokens(saida)}
