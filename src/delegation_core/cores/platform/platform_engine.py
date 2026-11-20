"""The local platform core: context pruning and host metrics.

Until 17/11/2026 this module also ran an "agent session" that executed nothing (fixed toy code
graph, a voice step that returned metadata only, a dead-code sweep that reported invented
counts). Those parts were removed for v0.17.0: only what does real work stays.
"""

from typing import Any, Dict

from .pruner.token_reducer import TokenPruningEngine
from .telemetry.hardware import HardwareSupervisor


class UnifiedLocalPlatform:
    """Context pruning (regex stages over the text) and host metrics (disk and load)."""

    def __init__(self):
        self.pruner = TokenPruningEngine()
        self.hardware = HardwareSupervisor()

    def prune_context(self, raw_text: str) -> Dict[str, Any]:
        return self.pruner.prune_context(raw_text)
