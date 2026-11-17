"""O registro dos grafos construidos (graphs_registry.json): ler e gravar, nada mais."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger("graphbridge")


def _load_registry(cfg) -> dict:
    path = cfg.graphs_registry_path
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as e:
        logger.warning("Could not load graphs registry: %s", e)
        return {}


def _save_registry(cfg, registry: dict) -> None:
    cfg.graphs_dir.mkdir(parents=True, exist_ok=True)
    cfg.graphs_registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
