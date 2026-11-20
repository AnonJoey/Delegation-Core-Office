"""Functional cores bundled with delegation-core.

- agent_harness: local skills catalog (SQLite FTS5), prompt sanitizer, Python code inspection
- multimodal: document conversion to Markdown (MarkItDown)
- platform: context pruning and host metrics
- self_hosted: a static catalog of self-hosted services (names, ports, roles)
"""

from .unified_facade import UnifiedCoresBridge, get_cores_bridge

__all__ = ["UnifiedCoresBridge", "get_cores_bridge"]
