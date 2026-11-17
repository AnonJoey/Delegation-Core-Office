"""Ligacao: o pedaco de `headroom/config.py` que os arquivos copiados importam.

Escrito para o delegation-core (nao e copia): o TransformResult, com os campos que
`transforms/base.py` e o Kompress usam, e os nomes de ferramenta e a configuracao que o
`transforms/read_lifecycle.py` importa (as definicoes de `headroom/config.py`, sem alteracao).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TransformResult:
    messages: list[dict[str, Any]]
    tokens_before: int
    tokens_after: int
    transforms_applied: list[str]
    markers_inserted: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timing: dict[str, float] = field(default_factory=dict)


# Tool names recognized as Read/Edit/Write for lifecycle tracking
_READ_TOOL_NAMES: frozenset[str] = frozenset({"Read", "read"})
_EDIT_TOOL_NAMES: frozenset[str] = frozenset({"Edit", "edit"})
_WRITE_TOOL_NAMES: frozenset[str] = frozenset({"Write", "write"})
_MUTATING_TOOL_NAMES: frozenset[str] = _EDIT_TOOL_NAMES | _WRITE_TOOL_NAMES


@dataclass
class ReadLifecycleConfig:
    """Event-driven Read lifecycle management: stale/superseded Reads become markers + CCR hashes."""

    enabled: bool = True
    compress_stale: bool = True  # Replace Reads of files that were later edited
    compress_superseded: bool = False  # Disabled upstream: busts Anthropic prompt cache prefix
    min_size_bytes: int = 512  # Skip tiny Read outputs (not worth the overhead)
