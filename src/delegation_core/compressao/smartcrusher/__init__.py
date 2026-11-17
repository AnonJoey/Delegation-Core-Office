"""SmartCrusher do Headroom, portado do Rust (`headroom-core/src/transforms/smart_crusher`)."""

from .base import CrushResult, SmartCrusherConfig
from .crusher import MemoriaCcr, SmartCrusher

__all__ = ["CrushResult", "MemoriaCcr", "SmartCrusher", "SmartCrusherConfig"]
