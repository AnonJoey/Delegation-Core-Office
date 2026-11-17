"""Ligacao: o armazenamento CCR do Headroom vira a guarda do delegation-core.

`store()` grava o original na `compressao.ccr.Guarda` (a mesma que
`recall_output` le) e devolve a chave que vai na marca `Retrieve more: hash=`.
"""

from __future__ import annotations

import hashlib


class _Store:
    def store(self, original: str, compressed: str, **_kwargs) -> str:
        from ...ccr import Guarda
        chave = hashlib.md5(original.encode("utf-8")).hexdigest()[:24]
        Guarda().put(chave, original)
        return chave


def get_compression_store() -> _Store:
    return _Store()
