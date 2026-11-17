"""Porte de crushers.rs, orchestration.rs e constraints.rs do SmartCrusher (Headroom, Apache 2.0)."""

from __future__ import annotations

import hashlib
import math
from decimal import Decimal

from ..adaptativo import compute_optimal_k
from .base import ERROR_KEYWORDS, format_g, mean, median, sample_stdev
from .itens import detect_error_items_for_preservation, detect_structural_outliers
from .jsonv import Num, as_f64, dumps
from .selecao import compute_item_hash


def rust_f64(x: float) -> str:
    """`format!("{}", x)` do Rust: o menor texto que volta ao mesmo f64, sem notacao cientifica."""
    s = format(Decimal(repr(x)), "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") and x == 0 else s


def _repr_numero(x: float) -> str:
    if math.isnan(x):
        return "nan"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == math.trunc(x) and abs(x) < 1e16:
        return str(int(x))
    return rust_f64(x)


# ── crushers.rs ─────────────────────────────────────────────────────────────

def compute_k_split(items: list[str], config, bias: float):
    max_k = config.max_items_after_crush if config.max_items_after_crush > 0 else None
    k_total = compute_optimal_k(items, bias, 3, max_k)
    k_first = min(max(1, int(round(k_total * config.first_fraction))), k_total)
    k_last = min(max(1, int(round(k_total * config.last_fraction))), max(0, k_total - k_first))
    return k_total, k_first, k_last, max(0, k_total - (k_first + k_last))


def crush_string_array(items: list[str], config, bias: float):
    n = len(items)
    if n <= 8:
        return list(items), "string:passthrough"
    if config.lossless_only:
        return list(items), "string:lossless_only"
    k_total, k_first, k_last, _ = compute_k_split(items, config, bias)
    erros = {i for i, s in enumerate(items) if any(k in s.lower() for k in ERROR_KEYWORDS)}
    tams = [float(len(s)) for s in items]
    anomalias = set()
    if len(tams) > 1:
        m = mean(tams) or 0.0
        dp = sample_stdev(tams) or 0.0
        if dp > 0.0:
            lim = config.variance_threshold * dp
            anomalias = {i for i, t in enumerate(tams) if abs(t - m) > lim}
    manter = set(erros) | anomalias | set(range(min(k_first, n))) | set(range(max(0, n - k_last), n))
    vistos = {items[i] for i in manter}
    repetidos = 0
    resto = max(0, k_total - len(manter))
    if resto > 0:
        passo = max(max(0, n - 1) // (resto + 1), 1)
        teto = k_total + len(erros) + len(anomalias)
        i = 0
        while i < n:
            if len(manter) >= teto:
                break
            if i not in manter:
                if items[i] not in vistos:
                    manter.add(i)
                    vistos.add(items[i])
                else:
                    repetidos += 1
            i += passo
    resultado = [items[i] for i in sorted(manter)]
    estr = f"string:adaptive({n}->{len(resultado)}"
    if repetidos:
        estr += f",dedup={repetidos}"
    if erros:
        estr += f",errors={len(erros)}"
    return resultado, estr + ")"


def _percentil(ordenados: list[float], q: float) -> float:
    n = len(ordenados)
    if n == 0:
        return 0.0
    if n == 1:
        return ordenados[0]
    pos = q * (n - 1)
    lo = int(pos)
    hi = lo + 1 if lo + 1 < n else lo
    frac = pos - lo
    return ordenados[lo] * (1.0 - frac) + ordenados[hi] * frac


def _finitos(vals):
    return [f for f in (as_f64(v) for v in vals) if f is not None and math.isfinite(f)]


def crush_number_array(items: list, config, bias: float):
    n = len(items)
    if n <= 8:
        return list(items), "number:passthrough"
    if config.lossless_only:
        return list(items), "number:lossless_only"
    finitos = _finitos(items)
    if not finitos:
        return list(items), "number:no_finite"
    k_total, k_first, k_last, _ = compute_k_split([dumps(v) for v in items], config, bias)
    media = mean(finitos) or 0.0
    mediana = median(finitos) or 0.0
    dp = (sample_stdev(finitos) or 0.0) if len(finitos) > 1 else 0.0
    ordenados = sorted(finitos)
    p25, p75 = _percentil(ordenados, 0.25), _percentil(ordenados, 0.75)
    fora = set()
    if dp > 0.0:
        lim = config.variance_threshold * dp
        for i, v in enumerate(items):
            f = as_f64(v)
            if f is not None and math.isfinite(f) and abs(f - media) > lim:
                fora.add(i)
    mudancas = set()
    if config.preserve_change_points and n > 10:
        for i in range(5, max(0, n - 5)):
            esq, dir_ = _finitos(items[i - 5:i]), _finitos(items[i:i + 5])
            if esq and dir_:
                if dp > 0.0 and abs((mean(dir_) or 0.0) - (mean(esq) or 0.0)) > config.variance_threshold * dp:
                    mudancas.add(i)
    manter = fora | mudancas | set(range(min(k_first, n))) | set(range(max(0, n - k_last), n))
    resto = max(0, k_total - len(manter))
    if resto > 0:
        passo = max(max(0, n - 1) // (resto + 1), 1)
        teto = k_total + len(fora)
        i = 0
        while i < n:
            if len(manter) >= teto:
                break
            manter.add(i)
            i += passo
    mantidos = [items[i] for i in sorted(manter)]
    estr = (f"number:adaptive({n}->{len(mantidos)},min={_repr_numero(min(finitos))},max={_repr_numero(max(finitos))},"
            f"mean={format_g(media)},median={format_g(mediana)},stddev={format_g(dp)},p25={format_g(p25)},p75={format_g(p75)}")
    if fora:
        estr += f",outliers={len(fora)}"
    if mudancas:
        estr += f",change_points={len(mudancas)}"
    return mantidos, estr + ")"


# ── constraints.rs ──────────────────────────────────────────────────────────

def default_oss_constraints():
    return [lambda items, strs: detect_error_items_for_preservation(items, strs),
            lambda items, strs: detect_structural_outliers(items)]


# ── orchestration.rs ────────────────────────────────────────────────────────

def item_content_hash(item, idx: int) -> str:
    if isinstance(item, (dict, list)):
        return compute_item_hash(item)
    if isinstance(item, str):
        c = item
    elif isinstance(item, Num):
        c = item.raw
    elif item is True or item is False:
        c = "true" if item else "false"
    elif item is None:
        c = "None"
    else:
        c = f"__idx_{idx}__"
    return hashlib.md5(c.encode("utf-8")).hexdigest()[:16]


def deduplicate_indices_by_content(manter: set[int], items: list) -> set[int]:
    vistos: dict[str, int] = {}
    for idx in sorted(manter):
        if idx < len(items):
            vistos.setdefault(item_content_hash(items[idx], idx), idx)
    return set(vistos.values())


def fill_remaining_slots(manter: set[int], items: list, n: int, efetivo: int) -> set[int]:
    resto = max(0, efetivo - len(manter))
    if resto == 0:
        return set(manter)
    vistos = {item_content_hash(items[i], i) for i in manter if i < n}
    cand = [i for i in range(n) if i not in manter]
    if not cand:
        return set(manter)
    res = set(manter)
    passo = max(len(cand) // (resto + 1), 1)
    add = 0
    for ini in range(passo):
        if add >= resto:
            break
        i = ini
        while i < len(cand):
            if add >= resto:
                return res
            idx = cand[i]
            h = item_content_hash(items[idx], idx)
            if h not in vistos:
                res.add(idx)
                vistos.add(h)
                add += 1
            i += passo
    return res


def _anomalias_numericas(config, items, analise) -> set[int]:
    saida = set()
    if analise is None or not analise.field_stats:
        return saida
    for nome, st in analise.field_stats.items():
        if not (st.field_type == "numeric" and st.mean_val is not None and (st.variance or 0.0) > 0.0):
            continue
        if st.variance <= 0.0:
            continue
        dp = math.sqrt(st.variance)
        if dp <= 0.0:
            continue
        lim = config.variance_threshold * dp
        for i, it in enumerate(items):
            if not isinstance(it, dict) or nome not in it:
                continue
            f = as_f64(it[nome])
            if f is not None and not math.isnan(f) and abs(f - st.mean_val) > lim:
                saida.add(i)
    return saida


def prioritize_indices(config, manter: set[int], items: list, n: int, analise, efetivo: int) -> set[int]:
    atual = deduplicate_indices_by_content(manter, items) if config.dedup_identical_items else set(manter)
    if len(atual) < efetivo and len(atual) < n:
        atual = fill_remaining_slots(atual, items, n, efetivo)
    if len(atual) <= efetivo:
        return atual
    prior = set(detect_error_items_for_preservation(items, None)) | set(detect_structural_outliers(items)) \
        | _anomalias_numericas(config, items, analise)
    resto = max(0, efetivo - len(prior))
    if resto > 0:
        for i in range(min(3, n)):
            if i not in prior and resto > 0:
                prior.add(i)
                resto -= 1
        for i in range(max(0, n - 2), n):
            if i not in prior and resto > 0:
                prior.add(i)
                resto -= 1
    if resto > 0:
        for i in sorted(atual - prior):
            if resto == 0:
                break
            prior.add(i)
            resto -= 1
    return prior
