"""Ligacao: o Tokenizer do Headroom, contando tokens como o resto do delegation-core (bytes/4)."""

from __future__ import annotations

import math
from typing import Any


class Tokenizer:
    def __init__(self, token_counter: Any = None, model: str = ""):
        self._counter = token_counter
        self.model = model

    def count_text(self, text: str) -> int:
        if self._counter is not None:
            return self._counter.count_text(text)
        return math.ceil(len((text or "").encode("utf-8")) / 4)

    def count_message(self, message: dict[str, Any]) -> int:
        return self.count_text(str(message.get("content", "")))

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        return sum(self.count_message(m) for m in messages)

    @property
    def available(self) -> bool:
        return True
