"""
token_reducer.py — Motor unificado de redução de tokens e compressão de contexto.
Fusão de Headroom (CCR AST Pruning com Guarda reversível) + RTK (Stage Filter) + Humanizer.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, Any, Optional

from delegation_core.compressao.ccr import Guarda


class TokenPruningEngine:
    """Motor unificado de compressão de contexto, integrando CCR do Headroom e filtros RTK."""

    def __init__(self):
        self.engine_name = "Headroom CCR + RTK Context Compressor"
        self._guarda = Guarda()

    def prune_context(self, raw_text: str, store_ccr: bool = True) -> Dict[str, Any]:
        t_orig = len(raw_text)

        # Estágio 1: Remoção de espaços em branco redundantes e linhas vazias sucessivas (RTK Stage 1-2)
        pruned = re.sub(r"[ \t]+", " ", raw_text)
        pruned = re.sub(r"\n{3,}", "\n\n", pruned)

        # Estágio 2: Poda de comentários óbvios de código sem corromper URLs nem cabeçalhos Markdown
        # Remove // apenas quando não precedido por ':' ou '/' (preserva https://, http://, file://)
        pruned = re.sub(r"(?<![:/])//.*?(?=\n|$)", "", pruned)
        # Remove comentários inline de código precedidos por espaço (ex: "x = 1 # valor")
        pruned = re.sub(r"[ \t]+#(?![#!]).*?(?=\n|$)", "", pruned)
        # Remove linhas de comentários de código isolados sem destruir cabeçalhos markdown (^#{1,6}\s) nem shebang (^#!)
        pruned = re.sub(r"(?m)^[ \t]*#(?![\!#\s]).*?(?=\n|$)", "", pruned)
        pruned = re.sub(r"\n{3,}", "\n\n", pruned)
        pruned = pruned.strip()

        t_final = len(pruned)
        chars_saved = max(0, t_orig - t_final)
        tokens_saved = int(chars_saved / 3.8)

        ccr_hash: Optional[str] = None
        if store_ccr and chars_saved > 0:
            ccr_hash = hashlib.md5(raw_text.encode("utf-8", errors="ignore")).hexdigest()[:24]
            try:
                self._guarda.put(ccr_hash, raw_text)
            except Exception:
                pass

        return {
            "engine": self.engine_name,
            "original_chars": t_orig,
            "pruned_chars": t_final,
            "tokens_saved_estimate": tokens_saved,
            "reduction_ratio": f"{round((1 - (t_final / max(1, t_orig))) * 100, 1)}%",
            "pruned_text": pruned,
            "ccr_hash": ccr_hash,
            "retrievable": ccr_hash is not None,
        }

    def retrieve_original(self, ccr_hash: str) -> Optional[str]:
        """Recupera o texto original completo via chave CCR do Headroom."""
        try:
            return self._guarda.get(ccr_hash)
        except Exception:
            return None
