"""Porte de planning.rs do SmartCrusher (Headroom, Apache 2.0)."""

from __future__ import annotations

import hashlib
import math

from .base import CompressionPlan, Estrategia, detect_score_field_statistically, hash_field_name
from .itens import extract_query_anchors, item_matches_anchors
from .jsonv import as_f64, dumps
from .podas import prioritize_indices


def map_to_anchor_pattern(estrategia: str) -> str:
    return {Estrategia.TIME_SERIES: "time_series", Estrategia.TOP_N: "search_results",
            Estrategia.CLUSTER_SAMPLE: "logs"}.get(estrategia, "generic")


def item_has_preserve_field_match(item, hashes: list[str], consulta: str) -> bool:
    if not consulta or not isinstance(item, dict):
        return False
    q = consulta.lower()
    for nome, v in item.items():
        if hash_field_name(nome) not in hashes or v is None:
            continue
        s = (v if isinstance(v, str) else dumps(v)).lower()
        if s in q or q in s:
            return True
    return False


def _anomalias(nome, st, items, limiar_var, manter: set[int]):
    if st.field_type != "numeric" or st.mean_val is None or st.variance is None or st.variance <= 0.0:
        return
    dp = math.sqrt(st.variance)
    if dp <= 0.0:
        return
    lim = limiar_var * dp
    for i, it in enumerate(items):
        if isinstance(it, dict) and nome in it:
            f = as_f64(it[nome])
            if f is not None and not math.isnan(f) and abs(f - st.mean_val) > lim:
                manter.add(i)


class SmartCrusherPlanner:
    def __init__(self, config, anchor_selector, scorer, analyzer, constraints):
        self.config, self.anchor_selector, self.scorer = config, anchor_selector, scorer
        self.analyzer, self.constraints = analyzer, constraints

    def _restricoes(self, items, strs, manter: set[int]):
        for c in self.constraints:
            manter.update(c(items, strs))

    def create_plan(self, analise, items, consulta, preserve_fields=None, max_efetivo=None, strs=None) -> CompressionPlan:
        maximo = max_efetivo if max_efetivo is not None else self.config.max_items_after_crush
        plano = CompressionPlan(strategy=analise.recommended_strategy,
                                constant_fields=dict(analise.constant_fields) if self.config.factor_out_constants else {})
        if analise.recommended_strategy == Estrategia.SKIP:
            plano.keep_indices = list(range(len(items)))
            return plano
        f = {Estrategia.TIME_SERIES: self.plan_time_series, Estrategia.CLUSTER_SAMPLE: self.plan_cluster_sample,
             Estrategia.TOP_N: self.plan_top_n}.get(analise.recommended_strategy, self.plan_smart_sample)
        return f(analise, items, plano, consulta, preserve_fields, maximo, strs)

    def plan_smart_sample(self, analise, items, plano, consulta, preserve, maximo, strs):
        n = len(items)
        manter = set(self.anchor_selector.select_anchors(items, maximo, map_to_anchor_pattern(Estrategia.SMART_SAMPLE),
                                                         consulta or None))
        self._restricoes(items, strs, manter)
        for nome, st in analise.field_stats.items():
            _anomalias(nome, st, items, self.config.variance_threshold, manter)
        if self.config.preserve_change_points:
            for st in analise.field_stats.values():
                for cp in st.change_points:
                    for off in (-1, 0, 1):
                        if 0 <= cp + off < n:
                            manter.add(cp + off)
        self._sinais_da_consulta(items, consulta, strs, manter, False)
        self._preserve(items, consulta, preserve, manter)
        plano.keep_indices = sorted(prioritize_indices(self.config, manter, items, n, analise, maximo))
        return plano

    def plan_top_n(self, analise, items, plano, consulta, preserve, maximo, strs):
        campo, conf_max = None, 0.0
        for nome, st in analise.field_stats.items():
            e, conf = detect_score_field_statistically(st, items)
            if e and conf > conf_max:
                campo, conf_max = nome, conf
        if campo is None:
            return self.plan_smart_sample(analise, items, plano, consulta, preserve, maximo, strs)
        plano.sort_field = campo
        pontuados = []
        for i, it in enumerate(items):
            f = as_f64(it.get(campo)) if isinstance(it, dict) else None
            pontuados.append((i, f if f is not None else 0.0))
        pontuados.sort(key=lambda p: -p[1])
        manter = {i for i, _ in pontuados[:max(0, maximo - 3)]}
        self._restricoes(items, strs, manter)
        if consulta:
            ancoras = extract_query_anchors(consulta)
            for i, it in enumerate(items):
                if i not in manter and item_matches_anchors(it, ancoras):
                    manter.add(i)
            textos = strs if strs is not None else [dumps(i) for i in items]
            notas = self.scorer.score_batch(textos, consulta)
            alto = max(self.config.relevance_threshold * 2.0, 0.5)
            add = 0
            for i, sc in enumerate(notas):
                if i not in manter and sc.score >= alto:
                    manter.add(i)
                    add += 1
                    if add >= 3:
                        break
        self._preserve(items, consulta, preserve, manter)
        plano.keep_count = len(manter)
        plano.keep_indices = sorted(manter)
        return plano

    def plan_cluster_sample(self, analise, items, plano, consulta, preserve, maximo, strs):
        n = len(items)
        manter = set(self.anchor_selector.select_anchors(items, maximo, map_to_anchor_pattern(Estrategia.CLUSTER_SAMPLE),
                                                         consulta or None))
        self._restricoes(items, strs, manter)
        campo, unic = None, 0.0
        for nome, st in analise.field_stats.items():
            if st.field_type == "string" and st.unique_ratio > unic and st.unique_ratio > 0.3:
                campo, unic = nome, st.unique_ratio
        if campo is not None:
            plano.cluster_field = campo
            grupos: dict[str, list[int]] = {}
            for i, it in enumerate(items):
                msg = it.get(campo) if isinstance(it, dict) else None
                msg = msg if isinstance(msg, str) else ""
                h = hashlib.md5(msg[:50].encode("utf-8")).hexdigest()[:8]
                grupos.setdefault(h, []).append(i)
            for idxs in grupos.values():
                manter.update(idxs[:2])
        self._sinais_da_consulta(items, consulta, strs, manter, False)
        self._preserve(items, consulta, preserve, manter)
        plano.keep_indices = sorted(prioritize_indices(self.config, manter, items, n, analise, maximo))
        return plano

    def plan_time_series(self, analise, items, plano, consulta, preserve, maximo, strs):
        n = len(items)
        manter = set(self.anchor_selector.select_anchors(items, maximo, map_to_anchor_pattern(Estrategia.TIME_SERIES),
                                                         consulta or None))
        for st in analise.field_stats.values():
            for cp in st.change_points:
                for off in (-2, -1, 0, 1, 2):
                    if 0 <= cp + off < n:
                        manter.add(cp + off)
        self._restricoes(items, strs, manter)
        self._sinais_da_consulta(items, consulta, strs, manter, False)
        self._preserve(items, consulta, preserve, manter)
        plano.keep_indices = sorted(prioritize_indices(self.config, manter, items, n, analise, maximo))
        return plano

    def _sinais_da_consulta(self, items, consulta, strs, manter: set[int], so_existentes: bool):
        if not consulta:
            return
        ancoras = extract_query_anchors(consulta)
        for i, it in enumerate(items):
            if so_existentes and i in manter:
                continue
            if item_matches_anchors(it, ancoras):
                manter.add(i)
        textos = strs if strs is not None else [dumps(i) for i in items]
        for i, sc in enumerate(self.scorer.score_batch(textos, consulta)):
            if so_existentes and i in manter:
                continue
            if sc.score >= self.config.relevance_threshold:
                manter.add(i)

    def _preserve(self, items, consulta, campos, manter: set[int]):
        if not campos or not consulta:
            return
        for i, it in enumerate(items):
            if item_has_preserve_field_match(it, campos, consulta):
                manter.add(i)
