"""Porte de analyzer.rs do SmartCrusher (Headroom, Apache 2.0).

`field_stats` e um BTreeMap no Rust: aqui um dict montado em ordem de chave
(bytes UTF-8), porque varias decisoes pegam o PRIMEIRO campo que satisfaz algo.
"""

from __future__ import annotations

import math

from .base import (ArrayAnalysis, CrushabilityAnalysis, Estrategia, FieldStats, detect_id_field_statistically,
                   detect_score_field_statistically, mean, sample_stdev, sample_variance)
from .itens import detect_error_items_for_preservation, detect_structural_outliers
from .jsonv import Num, as_f64, dumps


def _b(s: str) -> bytes:
    return s.encode("utf-8")


def python_repr(v) -> str:
    if v is None:
        return "None"
    if v is True:
        return "True"
    if v is False:
        return "False"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return v
    return dumps(v)


def top_n_by_count(strs: list[str], n: int) -> list[tuple[str, int]]:
    ordem, cont = [], {}
    for s in strs:
        if s not in cont:
            ordem.append(s)
        cont[s] = cont.get(s, 0) + 1
    pares = sorted(((k, cont[k]) for k in ordem), key=lambda p: -p[1])
    return pares[:n]


def _dig(c: int) -> bool:
    return 48 <= c <= 57


def is_iso_datetime(s: str) -> bool:
    b = s.encode("utf-8")
    if len(b) < 19:
        return False
    return (all(_dig(b[i]) for i in (0, 1, 2, 3, 5, 6, 8, 9, 11, 12, 14, 15, 17, 18))
            and b[4] == 45 and b[7] == 45 and b[10] in (84, 32) and b[13] == 58 and b[16] == 58)


def is_iso_date(s: str) -> bool:
    b = s.encode("utf-8")
    return len(b) == 10 and all(_dig(b[i]) for i in (0, 1, 2, 3, 5, 6, 8, 9)) and b[4] == 45 and b[7] == 45


class SmartAnalyzer:
    def __init__(self, config):
        self.config = config

    def analyze_array(self, items: list) -> ArrayAnalysis:
        if not (items and isinstance(items[0], dict)):
            return ArrayAnalysis(len(items), {}, "generic", Estrategia.NONE, {}, 0.0, None)
        chaves = set()
        for it in items:
            if isinstance(it, dict):
                chaves.update(it)
        stats = {k: self.analyze_field(k, items) for k in sorted(chaves, key=_b)}
        padrao = self.detect_pattern(stats, items)
        constantes = {k: v.constant_value for k, v in stats.items() if v.is_constant and v.constant_value is not None}
        crush = self.analyze_crushability(items, stats)
        estrategia = self.select_strategy(stats, padrao, len(items), crush)
        reducao = 0.0 if estrategia == Estrategia.SKIP else self.estimate_reduction(stats, estrategia, len(items))
        return ArrayAnalysis(len(items), stats, padrao, estrategia, constantes, reducao, crush)

    def analyze_field(self, key: str, items: list) -> FieldStats:
        valores = [it.get(key) for it in items if isinstance(it, dict)]
        nao_nulos = [v for v in valores if v is not None]
        if not nao_nulos:
            return FieldStats(key, "null", len(valores), 0, 0.0, True, None)
        p = nao_nulos[0]
        if p is True or p is False:
            tipo = "boolean"
        elif isinstance(p, Num):
            tipo = "numeric"
        elif isinstance(p, str):
            tipo = "string"
        elif isinstance(p, dict):
            tipo = "object"
        elif isinstance(p, list):
            tipo = "array"
        else:
            tipo = "unknown"
        unicos = len({python_repr(v) for v in valores})
        razao = unicos / len(valores) if valores else 0.0
        constante = unicos == 1
        st = FieldStats(key, tipo, len(valores), unicos, razao, constante, nao_nulos[0] if constante else None)
        if tipo == "numeric":
            nums = [f for f in (as_f64(v) for v in nao_nulos) if f is not None and math.isfinite(f)]
            if nums:
                mn, mx = min(nums), max(nums)
                m = mean(nums)
                var = sample_variance(nums) if len(nums) > 1 else 0.0
                if all(x is not None and math.isfinite(x) for x in (m, var, mn, mx)):
                    st.min_val, st.max_val, st.mean_val, st.variance = mn, mx, m, var
                    st.change_points = self.detect_change_points(nums, 5)
                else:
                    st.variance, st.change_points = 0.0, []
        elif tipo == "string":
            strs = [v for v in nao_nulos if isinstance(v, str)]
            if strs:
                st.avg_length = mean([float(len(s)) for s in strs])
                st.top_values = top_n_by_count(strs, 5)
        return st

    def detect_change_points(self, valores: list[float], janela: int) -> list[int]:
        if len(valores) < janela * 2:
            return []
        dp = sample_stdev(valores)
        if dp is None or not dp > 0.0:
            return []
        lim = self.config.variance_threshold * dp
        pontos = []
        for i in range(janela, max(0, len(valores) - janela)):
            antes = mean(valores[i - janela:i]) or 0.0
            depois = mean(valores[i:i + janela]) or 0.0
            if abs(depois - antes) > lim:
                pontos.append(i)
        if not pontos:
            return []
        saida = [pontos[0]]
        for cp in pontos[1:]:
            if cp - saida[-1] > janela:
                saida.append(cp)
        return saida

    def detect_pattern(self, stats: dict, items: list) -> str:
        tempo = self.detect_temporal_field(stats, items)
        variancia = any((v.variance or 0.0) > 0.0 for v in stats.values() if v.field_type == "numeric")
        if tempo and variancia:
            return "time_series"
        msg = nivel = False
        for s in stats.values():
            if s.field_type != "string":
                continue
            media = s.avg_length or 0.0
            if s.unique_ratio > 0.5 and media > 20.0:
                msg = True
            elif s.unique_ratio < 0.1 and 2 <= s.unique_count <= 10:
                nivel = True
        if msg and nivel:
            return "logs"
        for s in stats.values():
            e, conf = detect_score_field_statistically(s, items)
            if e and conf >= 0.5:
                return "search_results"
        return "generic"

    def detect_temporal_field(self, stats: dict, items: list) -> bool:
        for nome, s in stats.items():
            if s.field_type == "string":
                amostra = [it[nome] for it in items[:10] if isinstance(it, dict) and nome in it and isinstance(it[nome], str)]
                if not amostra:
                    continue
                if sum(1 for x in amostra if is_iso_datetime(x) or is_iso_date(x)) / len(amostra) > 0.5:
                    return True
            elif s.field_type == "numeric":
                if s.min_val is not None and s.max_val is not None:
                    mn = s.min_val
                    if 1_000_000_000.0 <= mn <= 2_000_000_000.0 or 1_000_000_000_000.0 <= mn <= 2_000_000_000_000.0:
                        return True
        return False

    def analyze_crushability(self, items: list, stats: dict) -> CrushabilityAnalysis:
        presentes, ausentes = [], []
        id_nome, id_unic, id_conf = None, 0.0, 0.0
        for nome, s in stats.items():
            valores = [it.get(nome) for it in items if isinstance(it, dict)]
            e, conf = detect_id_field_statistically(s, valores)
            if e and conf > id_conf:
                id_nome, id_unic, id_conf = nome, s.unique_ratio, conf
        tem_id = id_nome is not None and id_conf >= 0.7
        tem_score = False
        for nome, s in stats.items():
            e, conf = detect_score_field_statistically(s, items)
            if e:
                tem_score = True
                presentes.append(f"score_field:{nome}(conf={conf:.2f})")
                break
        if not tem_score:
            ausentes.append("score_field")
        fora = detect_structural_outliers(items)
        if fora:
            presentes.append(f"structural_outliers:{len(fora)}")
        else:
            ausentes.append("structural_outliers")
        erros_kw = detect_error_items_for_preservation(items, None)
        if erros_kw and not fora:
            presentes.append(f"error_keywords:{len(erros_kw)}")
        n_erros = max(len(fora), len(erros_kw))
        anomalias = set()
        for s in stats.values():
            if s.field_type != "numeric" or s.mean_val is None or s.variance is None or s.variance <= 0.0:
                continue
            dp = math.sqrt(s.variance)
            if dp <= 0.0:
                continue
            lim = self.config.variance_threshold * dp
            for i, it in enumerate(items):
                if not isinstance(it, dict) or s.name not in it:
                    continue
                f = as_f64(it[s.name])
                if f is not None and not math.isnan(f) and abs(f - s.mean_val) > lim:
                    anomalias.add(i)
        if anomalias:
            presentes.append(f"anomalies:{len(anomalias)}")
        else:
            ausentes.append("anomalies")
        razoes_str = [s.unique_ratio for s in stats.values() if s.field_type == "string" and s.name != id_nome]
        media_str = (mean(razoes_str) or 0.0) if razoes_str else 0.0
        razoes_num = [s.unique_ratio for s in stats.values() if s.field_type == "numeric" and s.name != id_nome]
        media_num = (mean(razoes_num) or 0.0) if razoes_num else 0.0
        max_unic = max(media_str, id_unic, 0.0)
        conteudo = max(media_str, media_num)
        if any(s.change_points for s in stats.values() if s.field_type == "numeric"):
            presentes.append("change_points")
        tem_sinal = bool(presentes)

        def fazer(crush, conf, motivo, pres, aus):
            return CrushabilityAnalysis(crush, conf, motivo, pres, aus, tem_id, id_unic, media_str, tem_score,
                                        n_erros, len(anomalias))
        if conteudo < 0.1 and tem_id:
            return fazer(True, 0.85, "repetitive_content_with_ids", presentes + ["repetitive_content"], ausentes)
        if max_unic < 0.3:
            return fazer(True, 0.9, "low_uniqueness_safe_to_sample", presentes, ausentes)
        if tem_id and max_unic > 0.8 and not tem_sinal:
            return fazer(False, 0.85, "unique_entities_no_signal", presentes, ausentes)
        if max_unic > 0.8 and tem_sinal:
            return fazer(True, 0.7, "unique_entities_with_signal", presentes, ausentes)
        if not tem_sinal:
            return fazer(False, 0.6, "medium_uniqueness_no_signal", presentes, ausentes)
        return fazer(True, 0.5, "medium_uniqueness_with_signal", presentes, ausentes)

    def select_strategy(self, stats: dict, padrao: str, n: int, crush) -> str:
        if n < self.config.min_items_to_analyze:
            return Estrategia.NONE
        if crush is not None and not crush.crushable:
            return Estrategia.SKIP
        if padrao == "time_series" and any(f.change_points for f in stats.values() if f.field_type == "numeric"):
            return Estrategia.TIME_SERIES
        if padrao == "logs":
            campo = next((v for k, v in stats.items() if "message" in k.lower()), None)
            if campo is not None and campo.unique_ratio < 0.5:
                return Estrategia.CLUSTER_SAMPLE
        if padrao == "search_results":
            return Estrategia.TOP_N
        return Estrategia.SMART_SAMPLE

    def estimate_reduction(self, stats: dict, estrategia: str, _n: int) -> float:
        if estrategia == Estrategia.NONE or not stats:
            return 0.0
        razao = sum(1 for v in stats.values() if v.is_constant) / len(stats)
        base = {Estrategia.TIME_SERIES: 0.7, Estrategia.CLUSTER_SAMPLE: 0.8, Estrategia.TOP_N: 0.6,
                Estrategia.SMART_SAMPLE: 0.5}.get(estrategia, 0.3)
        return min(base + razao * 0.2, 0.95)
