"""Porte de transforms/anchor_selector.rs e relevance/{base,bm25,hybrid}.rs (Headroom, Apache 2.0).

O pontuador hibrido do Rust tem o lado semantico (embeddings) desligado de
fabrica, entao ele e sempre BM25 com o reforco de "so BM25"; o porte e isso.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field

from .base import soma
from .jsonv import dumps, python_json_dumps_sort_keys


# ── anchor_selector.rs ──────────────────────────────────────────────────────

@dataclass
class AnchorConfig:
    anchor_budget_pct: float = 0.25
    min_anchor_slots: int = 3
    max_anchor_slots: int = 12
    default_front_weight: float = 0.5
    default_back_weight: float = 0.4
    default_middle_weight: float = 0.1
    search_front_weight: float = 0.75
    search_back_weight: float = 0.15
    logs_front_weight: float = 0.15
    logs_back_weight: float = 0.75
    recency_keywords: tuple = ("latest", "recent", "last", "newest", "current", "now")
    historical_keywords: tuple = ("first", "oldest", "earliest", "original", "initial", "beginning")
    use_information_density: bool = True
    candidate_multiplier: int = 3
    dedup_identical_items: bool = True


@dataclass
class Pesos:
    front: float = 0.5
    middle: float = 0.1
    back: float = 0.4

    def normalize(self) -> "Pesos":
        total = self.front + self.middle + self.back
        if total == 0.0:
            return Pesos()
        return Pesos(self.front / total, self.middle / total, self.back / total)


def compute_item_hash(item) -> str:
    return hashlib.md5(python_json_dumps_sort_keys(item).encode("utf-8")).hexdigest()[:16]


def _unicidade_de_valor(item, todos) -> float:
    if len(todos) < 2:
        return 0.5
    contagem: dict[str, dict[str, int]] = {}
    for o in todos:
        if not isinstance(o, dict):
            continue
        for k, v in o.items():
            s = v if isinstance(v, str) else python_json_dumps_sort_keys(v)
            d = contagem.setdefault(k, {})
            d[s] = d.get(s, 0) + 1
    if not isinstance(item, dict):
        return 0.5
    n = len(todos)
    raridade = []
    for k, v in item.items():
        if k not in contagem:
            continue
        c = contagem[k].get(v if isinstance(v, str) else python_json_dumps_sort_keys(v), 0)
        if c > 0:
            raridade.append(1.0 - c / n)
    return soma(raridade) / len(raridade) if raridade else 0.5


def _comprimento(item, todos) -> float:
    if len(todos) < 2:
        return 0.5
    tam = len(dumps(item).encode("utf-8"))
    tams = [len(dumps(i).encode("utf-8")) for i in todos if isinstance(i, dict)]
    if not tams:
        return 0.5
    mx, mn = max(tams), min(tams)
    if mx == mn:
        return 0.5
    return (tam - mn) / (mx - mn)


def _estrutural(item, todos) -> float:
    validos = [v for v in todos if isinstance(v, dict)]
    n = len(validos)
    if n < 2:
        return 0.5
    contagem: dict[str, int] = {}
    for o in validos:
        for k in o:
            contagem[k] = contagem.get(k, 0) + 1
    comuns = {k for k, c in contagem.items() if c >= n * 0.8}
    raros = {k for k, c in contagem.items() if c < n * 0.2}
    campos = set(item) if isinstance(item, dict) else set()
    u = 0.0
    if raros:
        u += 0.5 * (len(campos & raros) / max(len(raros), 1))
    if comuns:
        u += 0.5 * (len(comuns - campos) / max(len(comuns), 1))
    return min(u, 1.0)


def calculate_information_score(item, todos) -> float:
    if not todos or not isinstance(item, dict):
        return 0.0
    s = _unicidade_de_valor(item, todos) * 0.4 + _comprimento(item, todos) * 0.3 + _estrutural(item, todos) * 0.3
    return min(max(s, 0.0), 1.0)


class AnchorSelector:
    def __init__(self, config: AnchorConfig | None = None):
        self.config = config or AnchorConfig()

    def calculate_anchor_budget(self, tamanho: int, max_items: int) -> int:
        if tamanho <= max_items:
            return 0
        bruto = int(max_items * self.config.anchor_budget_pct)
        orc = min(self.config.max_anchor_slots, max(self.config.min_anchor_slots, bruto))
        return min(orc, tamanho)

    def _pesos_base(self, padrao: str) -> Pesos:
        c = self.config
        if padrao == "search_results":
            return Pesos(c.search_front_weight, 1.0 - c.search_front_weight - c.search_back_weight, c.search_back_weight)
        if padrao == "logs":
            return Pesos(c.logs_front_weight, 1.0 - c.logs_front_weight - c.logs_back_weight, c.logs_back_weight)
        if padrao == "time_series":
            return Pesos(0.45, 0.1, 0.45)
        return Pesos(c.default_front_weight, c.default_middle_weight, c.default_back_weight)

    def adjust_weights_for_query(self, base: Pesos, query: str | None) -> Pesos:
        if not query:
            return base
        q = query.lower()
        recente = any(k in q for k in self.config.recency_keywords)
        antigo = any(k in q for k in self.config.historical_keywords)
        if recente and not antigo:
            return Pesos(max(0.1, base.front - 0.15), base.middle, min(0.8, base.back + 0.15)).normalize()
        if antigo and not recente:
            return Pesos(min(0.8, base.front + 0.15), base.middle, max(0.1, base.back - 0.15)).normalize()
        return base

    def select_anchors(self, items: list, max_items: int, padrao: str, query: str | None) -> set[int]:
        n = len(items)
        if n == 0:
            return set()
        if n <= max_items:
            return set(range(n))
        orc = self.calculate_anchor_budget(n, max_items)
        if orc == 0:
            return set()
        p = self.adjust_weights_for_query(self._pesos_base(padrao), query).normalize()
        frente = max(1, int(orc * p.front))
        tras = max(1, int(orc * p.back))
        meio = max(0, orc - (frente + tras))
        total = frente + meio + tras
        if total > orc:
            excesso = total - orc
            reducao = min(meio, excesso)
            meio -= reducao
            excesso -= reducao
            if excesso > 0:
                tras = max(1, max(0, tras - excesso))
        ancoras: set[int] = set()
        vistos: set[str] = set()
        fim_frente = min(frente * 2, n // 3)
        a_frente = self._regiao(items, 0, fim_frente, frente, vistos, False)
        ancoras |= a_frente
        inicio_tras = max(max(0, n - tras * 2), (2 * n) // 3)
        a_tras = self._regiao(items, inicio_tras, n, tras, vistos, False)
        ancoras |= a_tras
        if meio > 0:
            ini, fim = len(a_frente), max(0, n - len(a_tras))
            if fim > ini:
                ancoras |= self._regiao(items, ini, fim, meio, vistos, self.config.use_information_density)
        return ancoras

    def _regiao(self, items, ini, fim, vagas, vistos, densidade) -> set[int]:
        sel: set[int] = set()
        if vagas == 0 or ini >= fim:
            return sel
        tam = fim - ini
        if densidade:
            return self._por_densidade(items, ini, fim, vagas, vistos)
        if vagas >= tam:
            for idx in range(ini, fim):
                if self._incluir(items, idx, vistos, False):
                    sel.add(idx)
            return sel
        passo = tam / (vagas + 1)
        for i in range(vagas):
            idx = min(ini + int((i + 1) * passo), fim - 1)
            if self._incluir(items, idx, vistos, False):
                sel.add(idx)
            else:
                for off in (1, -1, 2, -2):
                    alt = idx + off
                    if alt < ini or alt >= fim:
                        continue
                    if self._incluir(items, alt, vistos, False):
                        sel.add(alt)
                        break
        return sel

    def _por_densidade(self, items, ini, fim, vagas, vistos) -> set[int]:
        tam = fim - ini
        n_cand = min(vagas * self.config.candidate_multiplier, tam)
        passo = tam / (n_cand + 1) if n_cand > 0 else 1.0
        regiao = items[ini:fim]
        cand = []
        for i in range(n_cand):
            idx = min(ini + int((i + 1) * passo), fim - 1)
            if not self._incluir(items, idx, vistos, True):
                continue
            it = items[idx]
            cand.append((idx, calculate_information_score(it, regiao) if isinstance(it, dict) else 0.5))
        cand.sort(key=lambda x: -x[1])
        sel: set[int] = set()
        for idx, _ in cand[:vagas]:
            if self._incluir(items, idx, vistos, False):
                sel.add(idx)
        return sel

    def _incluir(self, items, idx, vistos, so_conferir) -> bool:
        if not self.config.dedup_identical_items:
            return True
        if idx >= len(items):
            return False
        it = items[idx]
        if not isinstance(it, dict):
            return True
        h = compute_item_hash(it)
        if h in vistos:
            return False
        if not so_conferir:
            vistos.add(h)
        return True


# ── relevance: base, bm25, hybrid ───────────────────────────────────────────

@dataclass
class RelevanceScore:
    score: float
    reason: str = ""
    matched_terms: list = field(default_factory=list)

    def __post_init__(self):
        self.score = min(max(self.score, 0.0), 1.0)


_TOKEN = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\b\d{4,}\b|[a-zA-Z0-9_]+")


class BM25Scorer:
    def __init__(self, k1=1.5, b=0.75, normalize_score=True, max_score=10.0):
        self.k1, self.b, self.normalize_score, self.max_score = k1, b, normalize_score, max_score

    def tokenize(self, texto: str) -> list[str]:
        return [m.group(0) for m in _TOKEN.finditer(texto.lower())] if texto else []

    def _bm25(self, doc, consulta: dict[str, int], media: float):
        if not doc or not consulta:
            return 0.0, []
        n = float(len(doc))
        avgdl = media if media > 0.0 else (n if n > 0.0 else 1.0)
        freq: dict[str, int] = {}
        for t in doc:
            freq[t] = freq.get(t, 0) + 1
        s, casou = 0.0, []
        idf = math.log(2.0)
        for termo in sorted(consulta, key=lambda t: t.encode("utf-8")):
            f = freq.get(termo)
            if f is None:
                continue
            casou.append(termo)
            s += idf * (f * (self.k1 + 1.0)) / (f + self.k1 * (1.0 - self.b + self.b * n / avgdl)) * consulta[termo]
        return s, casou

    def _final(self, bruto, casou) -> float:
        v = min(bruto / self.max_score, 1.0) if self.normalize_score else bruto
        if any(len(t.encode("utf-8")) >= 8 for t in casou):
            v = min(v + 0.3, 1.0)
        return v

    def score_batch(self, items: list[str], contexto: str) -> list[RelevanceScore]:
        ctx = self.tokenize(contexto)
        if not ctx:
            return [RelevanceScore(0.0, "BM25: empty context") for _ in items]
        consulta: dict[str, int] = {}
        for t in ctx:
            consulta[t] = consulta.get(t, 0) + 1
        todos = [self.tokenize(i) for i in items]
        media = sum(len(t) for t in todos) / max(len(items), 1)
        saida = []
        for toks in todos:
            bruto, casou = self._bm25(toks, consulta, media)
            saida.append(RelevanceScore(self._final(bruto, casou), "BM25", casou[:5]))
        return saida


class HybridScorer:
    """Sempre o caminho "so BM25, reforcado": o lado de embeddings do Rust esta desligado."""

    def __init__(self):
        self.bm25 = BM25Scorer()

    @staticmethod
    def _reforco(r: RelevanceScore) -> RelevanceScore:
        s = r.score
        if r.matched_terms:
            s = max(s, 0.3)
            if len(r.matched_terms) >= 2:
                s = min(s + 0.2, 1.0)
        return RelevanceScore(s, "Hybrid (BM25 only, boosted)", list(r.matched_terms))

    def score_batch(self, items: list[str], contexto: str) -> list[RelevanceScore]:
        if not items:
            return []
        return [self._reforco(r) for r in self.bm25.score_batch(items, contexto)]
