"""Single entry point to the cores bundled with delegation-core.

What each core does, and only that:

- agent harness: search a local skills catalog (SQLite FTS5), audit and clean text of filler
  phrases, inspect a Python file's structure
- multimodal: convert documents to Markdown (delegation_core.markitdown)
- platform: prune text for fewer tokens, read host metrics (disk use of the home folder, load)
- self-hosted: a static catalog of services (name, domain, port, role); nothing is contacted

Until 17/11/2026 this facade also exposed OCR, audio transcription, speech synthesis, diagram
generation, an "agent session", request routing to self-hosted services and a CI runner. None
of them did the work they reported: they returned fixed or invented results marked as success.
They were removed for v0.17.0.
"""

import time
from typing import Any, Dict, List, Optional

from .agent_harness.server import AgentHarnessServer
from .multimodal.pipeline import MultimodalPipeline
from .platform.platform_engine import UnifiedLocalPlatform
from .self_hosted.gateway import HomelabServiceGateway


class UnifiedCoresBridge:
    def __init__(self, skills_db_path: Optional[str] = None):
        self.agent_harness = AgentHarnessServer(skills_db_path)
        self.multimodal = MultimodalPipeline()
        self.platform = UnifiedLocalPlatform()
        self.self_hosted = HomelabServiceGateway()

    # --- agent harness ---
    def search_skills(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        return self.agent_harness.skills.search(query, limit)

    def get_skill_by_id(self, skill_id: int) -> Optional[Dict[str, Any]]:
        return self.agent_harness.skills.get_by_id(skill_id)

    def sanitize_text(self, text: str) -> Dict[str, Any]:
        audit = self.agent_harness.sanitizer.audit(text)
        purified = self.agent_harness.sanitizer.purify(text)
        return {"audit": audit, "purified": purified, "is_clean": audit["is_clean"], "score": audit["score"]}

    # --- multimodal ---
    def ingest_multimodal_asset(self, file_path: str) -> Dict[str, Any]:
        return self.multimodal.ingest_asset(file_path)

    # --- platform ---
    def prune_context(self, raw_text: str) -> Dict[str, Any]:
        return self.platform.prune_context(raw_text)

    def get_hardware_metrics(self) -> Dict[str, Any]:
        return self.platform.hardware.get_server_metrics()

    # --- self-hosted catalog ---
    def list_homelab_services(self, domain: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.self_hosted.list_services(domain)

    # --- status ---
    def get_unified_status(self) -> Dict[str, Any]:
        stats = self.agent_harness.skills.get_stats()
        return {
            "status": "OPERATIONAL",
            "timestamp": time.time(),
            "cores_active": ["agent-harness-core", "multimodal-media-core", "local-platform-core",
                             "self-hosted-catalog"],
            "skills": {
                "total_indexed": sum(v["count"] for v in stats.values()) if stats else 0,
                "sources": list(stats.keys()),
            },
            "multimodal_capabilities": ["document conversion to Markdown"],
            "local_platform": {"hardware": self.get_hardware_metrics(), "context_reducer": "regex pruning"},
            "self_hosted_catalog": self.self_hosted.summary(),
        }


_GLOBAL_BRIDGE: Optional[UnifiedCoresBridge] = None


def get_cores_bridge() -> UnifiedCoresBridge:
    global _GLOBAL_BRIDGE
    if _GLOBAL_BRIDGE is None:
        _GLOBAL_BRIDGE = UnifiedCoresBridge()
    return _GLOBAL_BRIDGE
