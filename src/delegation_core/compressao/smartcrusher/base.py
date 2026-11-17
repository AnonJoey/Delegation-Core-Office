"""Porte de types.rs, config.rs, hashing.rs, error_keywords.rs, stats_math.rs,
statistics.rs, field_detect.rs e classifier.rs do SmartCrusher (Headroom, Apache 2.0).

Soma de float sempre em laco (`soma`): o `sum()` do Python 3.12+ compensa o
erro de arredondamento e da resultado diferente da soma ingenua do Rust.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any

from .jsonv import Num, as_f64


def soma(valores) -> float:
    t = 0.0
    for v in valores:
        t += v
    return t


# ── types.rs ────────────────────────────────────────────────────────────────

class Estrategia:
    NONE, SKIP, TIME_SERIES, CLUSTER_SAMPLE, TOP_N, SMART_SAMPLE = (
        "none", "skip", "time_series", "cluster", "top_n", "smart_sample")


@dataclass
class FieldStats:
    name: str
    field_type: str
    count: int
    unique_count: int
    unique_ratio: float
    is_constant: bool
    constant_value: Any = None
    min_val: float | None = None
    max_val: float | None = None
    mean_val: float | None = None
    variance: float | None = None
    change_points: list = field(default_factory=list)
    avg_length: float | None = None
    top_values: list = field(default_factory=list)


@dataclass
class CrushabilityAnalysis:
    crushable: bool
    confidence: float
    reason: str
    signals_present: list = field(default_factory=list)
    signals_absent: list = field(default_factory=list)
    has_id_field: bool = False
    id_uniqueness: float = 0.0
    avg_string_uniqueness: float = 0.0
    has_score_field: bool = False
    error_item_count: int = 0
    anomaly_count: int = 0


@dataclass
class ArrayAnalysis:
    item_count: int
    field_stats: dict
    detected_pattern: str
    recommended_strategy: str
    constant_fields: dict
    estimated_reduction: float
    crushability: CrushabilityAnalysis | None = None


@dataclass
class CompressionPlan:
    strategy: str = Estrategia.NONE
    keep_indices: list = field(default_factory=list)
    constant_fields: dict = field(default_factory=dict)
    summary_ranges: list = field(default_factory=list)
    cluster_field: str | None = None
    sort_field: str | None = None
    keep_count: int = 10


@dataclass
class CrushResult:
    compressed: str
    original: str
    was_modified: bool
    strategy: str


# ── config.rs ───────────────────────────────────────────────────────────────

@dataclass
class SmartCrusherConfig:
    enabled: bool = True
    min_items_to_analyze: int = 5
    min_tokens_to_crush: int = 200
    variance_threshold: float = 2.0
    uniqueness_threshold: float = 0.1
    similarity_threshold: float = 0.8
    max_items_after_crush: int = 15
    preserve_change_points: bool = True
    factor_out_constants: bool = False
    include_summaries: bool = False
    use_feedback_hints: bool = True
    toin_confidence_threshold: float = 0.5
    dedup_identical_items: bool = True
    first_fraction: float = 0.3
    last_fraction: float = 0.15
    relevance_threshold: float = 0.3
    lossless_min_savings_ratio: float = 0.15
    enable_ccr_marker: bool = True
    lossless_only: bool = False
    compaction_core_field_fraction: float = 0.8
    compaction_heterogeneous_core_ratio: float = 0.6
    compaction_max_flatten_inner_keys: int = 6
    compaction_min_buckets: int = 2
    compaction_max_buckets: int = 8

    def opaque_markers_enabled(self) -> bool:
        return self.enable_ccr_marker and not self.lossless_only


# ── hashing.rs / error_keywords.rs ──────────────────────────────────────────

def hash_field_name(nome: str) -> str:
    return hashlib.sha256(nome.encode("utf-8")).hexdigest()[:8]


ERROR_KEYWORDS = ("error", "exception", "failed", "failure", "critical", "fatal", "crash", "panic", "abort",
                  "timeout", "denied", "rejected")


# ── stats_math.rs ───────────────────────────────────────────────────────────

def mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    m = soma(vals) / len(vals)
    return m if math.isfinite(m) else None


def sample_variance(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    m = mean(vals)
    if m is None:
        return None
    var = soma((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return var if math.isfinite(var) else None


def sample_stdev(vals: list[float]) -> float | None:
    v = sample_variance(vals)
    return None if v is None else math.sqrt(v)


def median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    return (s[n // 2 - 1] + s[n // 2]) / 2.0 if n % 2 == 0 else s[n // 2]


def format_g(x: float) -> str:
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == 0.0:
        return "0"
    exp = math.floor(math.log10(abs(x)))
    if not -4 <= exp < 4:
        mant, _, e = f"{x:.3e}".partition("e")
        if "." in mant:
            mant = mant.rstrip("0").rstrip(".")
        n = int(e)
        return f"{mant}e{'+' if n >= 0 else '-'}{abs(n):02d}"
    s = f"{x:.{max(3 - exp, 0)}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


# ── statistics.rs ───────────────────────────────────────────────────────────

_HEX = set("0123456789abcdefABCDEF")


def is_uuid_format(v: str) -> bool:
    if len(v.encode("utf-8")) != 36:
        return False
    partes = v.split("-")
    if len(partes) != 5:
        return False
    for p, n in zip(partes, (8, 4, 4, 4, 12)):
        if len(p.encode("utf-8")) != n or not all(c in _HEX for c in p):
            return False
    return True


def calculate_string_entropy(s: str) -> float:
    n = len(s)
    if n < 2:
        return 0.0
    freq: dict[str, int] = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    ent = 0.0
    for c in freq.values():
        p = c / n
        if p > 0.0:
            ent -= p * math.log2(p)
    maxe = math.log2(min(len(freq), n))
    return ent / maxe if maxe > 0.0 else 0.0


_INT_RUST = re.compile(r"[+-]?[0-9]+")


def python_int_parse(s: str) -> int | None:
    t = s.strip()
    if not t:
        return None
    if "_" in t:
        if t[0] == "_" or t[-1] == "_" or "__" in t:
            return None
        t = t.replace("_", "")
    if not _INT_RUST.fullmatch(t):
        return None
    n = int(t)
    return n if -(2 ** 63) <= n < 2 ** 63 else None


def detect_sequential_pattern(values: list, check_order: bool) -> bool:
    if len(values) < 5:
        return False
    nums: list[float] = []
    teve_numero = False
    for v in values:
        if isinstance(v, Num):
            f = v.as_f64()
            nums.append(f)
            teve_numero = True
        elif isinstance(v, str):
            p = python_int_parse(v)
            if p is not None:
                nums.append(float(p))
    if len(nums) < 5 or not teve_numero:
        return False
    ordenados = sorted(nums)
    diffs = [ordenados[i + 1] - ordenados[i] for i in range(len(ordenados) - 1)]
    if not diffs:
        return False
    media = soma(diffs) / len(diffs)
    if not 0.5 <= media <= 2.0:
        return False
    if sum(1 for d in diffs if 0.5 <= d <= 2.0) / len(diffs) <= 0.8:
        return False
    if check_order:
        asc = sum(1 for i in range(len(nums) - 1) if nums[i] <= nums[i + 1])
        return asc / (len(nums) - 1) > 0.7
    return True


# ── field_detect.rs ─────────────────────────────────────────────────────────

def detect_id_field_statistically(stats: FieldStats, values: list) -> tuple[bool, float]:
    if stats.unique_ratio < 0.9:
        return False, 0.0
    if stats.field_type == "string":
        amostra = [v for v in values[:20] if isinstance(v, str)]
        if amostra:
            if sum(1 for s in amostra if is_uuid_format(s)) / len(amostra) > 0.8:
                return True, 0.95
            if soma(calculate_string_entropy(s) for s in amostra) / len(amostra) > 0.7 and stats.unique_ratio > 0.95:
                return True, 0.8
    if stats.field_type == "numeric":
        if detect_sequential_pattern(values, True) and stats.unique_ratio > 0.95:
            return True, 0.9
        if stats.min_val is not None and stats.max_val is not None:
            if stats.max_val - stats.min_val > 0.0 and stats.unique_ratio > 0.95:
                return True, 0.85
    if stats.unique_ratio > 0.98:
        return True, 0.7
    return False, 0.0


def detect_score_field_statistically(stats: FieldStats, items: list) -> tuple[bool, float]:
    if stats.field_type != "numeric" or stats.min_val is None or stats.max_val is None:
        return False, 0.0
    mn, mx = stats.min_val, stats.max_val
    conf = 0.0
    if 0.0 <= mn <= 1.0 and 0.0 <= mx <= 1.0:
        conf += 0.4
    elif 0.0 <= mn <= 10.0 and 0.0 <= mx <= 10.0:
        conf += 0.3
    elif 0.0 <= mn <= 100.0 and 0.0 <= mx <= 100.0:
        conf += 0.25
    elif mn >= -1.0 and mx <= 1.0:
        conf += 0.35
    else:
        return False, 0.0
    amostra = [it[stats.name] for it in items[:50] if isinstance(it, dict) and stats.name in it]
    if detect_sequential_pattern(amostra, True):
        return False, 0.0
    em_ordem = [f for f in (as_f64(it[stats.name]) for it in items if isinstance(it, dict) and stats.name in it)
                if f is not None and math.isfinite(f)]
    if len(em_ordem) >= 5:
        pares = len(em_ordem) - 1
        desc = sum(1 for i in range(pares) if em_ordem[i] >= em_ordem[i + 1])
        if pares > 0 and desc / pares > 0.7:
            conf += 0.3
    primeiros = em_ordem[:20]
    flutuantes = sum(1 for v in primeiros if math.isfinite(v) and v != math.trunc(v))
    if primeiros and flutuantes > len(primeiros) * 0.3:
        conf += 0.1
    return conf >= 0.4, min(conf, 0.95)


# ── classifier.rs ───────────────────────────────────────────────────────────

def classify_array(items: list) -> str:
    if not items:
        return "empty"
    tipos = set()
    for it in items:
        if it is True or it is False:
            tipos.add("bool")
        elif isinstance(it, Num):
            tipos.add("number")
        elif isinstance(it, str):
            tipos.add("string")
        elif isinstance(it, dict):
            tipos.add("object")
        elif isinstance(it, list):
            tipos.add("array")
        else:
            tipos.add("null")
    if len(tipos) == 1:
        return {"bool": "bool_array", "object": "dict_array", "string": "string_array", "number": "number_array",
                "array": "nested_array"}.get(next(iter(tipos)), "mixed_array")
    return "mixed_array"
