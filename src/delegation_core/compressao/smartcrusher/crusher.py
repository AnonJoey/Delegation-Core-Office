"""SmartCrusher: `smart_crusher/crusher.rs` e `builder.rs`.

Comprime JSON de saida de ferramenta. Arrays de objetos passam primeiro pela
compactacao sem perda (tabela CSV com esquema); se ela nao economizar o
bastante, o analisador escolhe uma estrategia com perda e o planejador decide
que itens ficam. O que sai vai para o store CCR com um marcador
`<<ccr:hash N_rows_offloaded>>`, recuperavel por `recall_output`.

O store e qualquer objeto com `put(chave, conteudo)`; o padrao e um dict em
memoria, como o `InMemoryCcrStore` do Rust. No delegation-core o roteador
passa a `Guarda` do `ccr.py`.
"""

from __future__ import annotations

import hashlib

from ..adaptativo import compute_optimal_k
from . import compactacao as cp
from .analise import SmartAnalyzer
from .base import CrushResult, Estrategia, SmartCrusherConfig, classify_array, mean, sample_stdev
from .compactacao import CompactConfig, CompactionStage, ClassifyConfig, _ESPACOS, nbytes
from .jsonv import as_f64, dumps, loads, python_json_dumps_sort_keys, python_safe_json_dumps
from .plano import SmartCrusherPlanner
from .podas import compute_k_split, crush_number_array, crush_string_array, default_oss_constraints
from .selecao import AnchorConfig, AnchorSelector, HybridScorer

MAX_PROCESS_DEPTH = 50


class MemoriaCcr:
    def __init__(self):
        self.dados: dict[str, str] = {}

    def put(self, chave: str, conteudo: str) -> None:
        self.dados[chave] = conteudo

    def get(self, chave: str):
        return self.dados.get(chave)


def _trim(s: str) -> str:
    i, j = 0, len(s)
    while i < j and s[i] in _ESPACOS:
        i += 1
    while j > i and s[j - 1] in _ESPACOS:
        j -= 1
    return s[i:j]


def has_json_insignificant_whitespace(s: str) -> bool:
    dentro = escape = False
    for ch in _trim(s):
        if dentro:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                dentro = False
            continue
        if ch == '"':
            dentro = True
            continue
        if ch in _ESPACOS:
            return True
    return False


def hash_canonical(canonico: str) -> str:
    return hashlib.sha256(canonico.encode("utf-8")).digest()[:6].hex()


def _group_key(v) -> str:
    if isinstance(v, dict):
        return "dict"
    if isinstance(v, str):
        return "str"
    if v is True or v is False:
        return "bool"
    if v is None:
        return "none"
    if isinstance(v, list):
        return "list"
    return "number"


def _kind_compactacao(c) -> str:
    if isinstance(c, cp.Table):
        return "table"
    if isinstance(c, cp.Buckets):
        return "buckets"
    if isinstance(c, cp.OpaqueRef):
        return "ccr"
    return "untouched"


def swap_remove(d: dict, chave: str) -> dict:
    """`Map::remove` do serde_json com preserve_order e o `swap_remove` do
    IndexMap: a ultima chave ocupa a posicao da removida."""
    chaves = list(d)
    i = chaves.index(chave)
    ultima = chaves[-1]
    if ultima != chave:
        chaves[i] = ultima
    chaves.pop()
    return {k: d[k] for k in chaves}


class _ResultadoArray:
    __slots__ = ("items", "strategy_info", "ccr_hash", "dropped_summary", "compacted", "compaction_kind")

    def __init__(self, items, info, ccr_hash=None, dropped="", compacted=None, kind=None):
        self.items = items
        self.strategy_info = info
        self.ccr_hash = ccr_hash
        self.dropped_summary = dropped
        self.compacted = compacted
        self.compaction_kind = kind


class SmartCrusher:
    def __init__(self, config: SmartCrusherConfig | None = None, *, store=None,
                 compaction: bool | str = True, anchor_config: AnchorConfig | None = None):
        """`SmartCrusher::new` com `compaction=True`; `without_compaction` com
        False; `with_compaction_format(nome)` com o nome do formatador."""
        self.config = config or SmartCrusherConfig()
        c = self.config
        if compaction is True:
            cfg = CompactConfig(
                classify=ClassifyConfig(emit_opaque_markers=c.opaque_markers_enabled()),
                core_field_fraction=c.compaction_core_field_fraction,
                heterogeneous_core_ratio=c.compaction_heterogeneous_core_ratio,
                max_flatten_inner_keys=c.compaction_max_flatten_inner_keys,
                min_buckets=c.compaction_min_buckets,
                max_buckets=c.compaction_max_buckets,
            )
            self.compaction = CompactionStage(cfg)
        elif compaction:
            self.compaction = CompactionStage.from_format_name(compaction)
            if self.compaction is None:
                raise ValueError(f"formato de compactacao desconhecido: {compaction}")
            self.compaction.config.classify.emit_opaque_markers = c.opaque_markers_enabled()
        else:
            self.compaction = None
        self.anchor_selector = AnchorSelector(anchor_config or AnchorConfig())
        self.scorer = HybridScorer()
        self.analyzer = SmartAnalyzer(self.config)
        self.constraints = default_oss_constraints()
        self.ccr_store = store if store is not None else MemoriaCcr()

    def _planner(self) -> SmartCrusherPlanner:
        return SmartCrusherPlanner(self.config, self.anchor_selector, self.scorer,
                                   self.analyzer, self.constraints)

    # --- entrada ------------------------------------------------------------

    def crush(self, content: str, query: str = "", bias: float = 1.0) -> CrushResult:
        comprimido, mudou, info = self.smart_crush_content(content, query, bias)
        return CrushResult(comprimido, content, mudou, info or "passthrough")

    def smart_crush_content(self, content: str, query: str, bias: float):
        try:
            parsed = loads(content)
        except (ValueError, RecursionError):
            return content, False, ""
        crushed, info = self.process_value(parsed, 0, query, bias)
        if (crushed == parsed and not info and isinstance(parsed, dict)
                and not has_json_insignificant_whitespace(content)):
            return content, False, ""
        resultado = python_safe_json_dumps(crushed)
        return resultado, resultado != _trim(content), info

    # --- percurso -----------------------------------------------------------

    def process_value(self, value, depth: int, query: str, bias: float):
        if depth >= MAX_PROCESS_DEPTH:
            return value, ""
        partes: list[str] = []
        if isinstance(value, list):
            n = len(value)
            if n >= self.config.min_items_to_analyze:
                tipo = classify_array(value)
                if tipo == "dict_array":
                    rows = list(value)
                    r = self._crush_array(rows, value, query, bias)
                    if r.strategy_info == "none:adaptive_at_limit":
                        partes.append(f"{r.strategy_info}({n}->{len(r.items)})")
                        proc = []
                        for item in value:
                            p, pi = self.process_value(item, depth + 1, query, bias)
                            proc.append(p)
                            if pi:
                                partes.append(pi)
                        return proc, ",".join(partes)
                    if r.compacted is not None:
                        partes.append(f"{r.strategy_info}({n}->len={nbytes(r.compacted)})")
                        return r.compacted, ",".join(partes)
                    partes.append(f"{r.strategy_info}({n}->{len(r.items)})")
                    items = list(r.items)
                    if r.dropped_summary:
                        items.append({"_ccr_dropped": r.dropped_summary})
                    return items, ",".join(partes)
                if tipo == "string_array":
                    strs = [v for v in value if isinstance(v, str)]
                    crushed, estr = crush_string_array(strs, self.config, bias)
                    partes.append(f"{estr}({n}->{len(crushed)})")
                    vals = list(crushed)
                    self._sentinela_escalar(vals, value)
                    return vals, ",".join(partes)
                if tipo == "number_array":
                    crushed, estr = crush_number_array(value, self.config, bias)
                    partes.append(f"{estr}({n}->{len(crushed)})")
                    vals = list(crushed)
                    self._sentinela_escalar(vals, value)
                    return vals, ",".join(partes)
                if tipo == "mixed_array":
                    crushed, estr = self.crush_mixed_array(value, query, bias)
                    partes.append(f"{estr}({n}->{len(crushed)})")
                    vals = list(crushed)
                    self._sentinela_escalar(vals, value)
                    return vals, ",".join(partes)
            proc = []
            for item in value:
                p, pi = self.process_value(item, depth + 1, query, bias)
                proc.append(p)
                if pi:
                    partes.append(pi)
            return proc, ",".join(partes)
        if isinstance(value, dict):
            proc = {}
            for k, v in value.items():
                p, pi = self.process_value(v, depth + 1, query, bias)
                proc[k] = p
                if pi:
                    partes.append(pi)
            return proc, ",".join(partes)
        if isinstance(value, str):
            return self._process_string(value, depth, query, bias)
        return value, ""

    def _process_string(self, s: str, depth: int, query: str, bias: float):
        parsed = cp.try_parse_json_container(s)
        if parsed is not None:
            proc, sub = self.process_value(parsed, depth + 1, query, bias)
            if proc != parsed:
                rendered = proc if isinstance(proc, str) else dumps(proc)
                return rendered, (f"string_json[{sub}]" if sub else "string_json")
        cfg = ClassifyConfig(emit_opaque_markers=self.config.opaque_markers_enabled())
        cls = cp.classify_cell(s, cfg)
        if cls[0] == "opaque":
            # Sem gancho de prosa, base64/html e texto longo caem no mesmo marcador.
            return cp.emit_opaque_ccr_marker(s, cls[1], self.ccr_store), f"string_ccr:{cls[1]}"
        return s, ""

    # --- arrays -------------------------------------------------------------

    def crush_array(self, items: list, query: str = "", bias: float = 1.0):
        return self._crush_array(items, items, query, bias)

    def _crush_array(self, items, fonte, query, bias) -> _ResultadoArray:
        strs = [dumps(i) for i in items]
        max_k = self.config.max_items_after_crush if self.config.max_items_after_crush > 0 else None
        k = compute_optimal_k(strs, bias, 3, max_k)
        if len(items) <= k:
            return _ResultadoArray(list(items), "none:adaptive_at_limit")
        if self.compaction is not None:
            c, rendered = self.compaction.run(items, self.ccr_store)
            if cp.was_compacted(c):
                entrada = sum(nbytes(s) for s in strs) + max(0, len(strs) - 1) + 2
                economia = 1.0 - (nbytes(rendered) / entrada) if entrada > 0 else 0.0
                if economia >= self.config.lossless_min_savings_ratio:
                    kind = _kind_compactacao(c)
                    return _ResultadoArray(list(items), f"lossless:{kind}", compacted=rendered, kind=kind)
        if self.config.lossless_only:
            return _ResultadoArray(list(items), "lossless_only:uncompacted")
        analise = self.analyzer.analyze_array(items)
        if analise.recommended_strategy == Estrategia.SKIP:
            motivo = f"skip:{analise.crushability.reason}" if analise.crushability is not None else ""
            return _ResultadoArray(list(items), motivo)
        plano = self._planner().create_plan(analise, items, query, None, k, strs)
        resultado = self.execute_plan(plano, items)
        caidos = max(0, len(items) - len(resultado))
        if caidos > 0 and self.config.enable_ccr_marker:
            canonico = dumps(list(fonte))
            h = hash_canonical(canonico)
            self.ccr_store.put(h, canonico)
            return _ResultadoArray(resultado, analise.recommended_strategy, h,
                                   f"<<ccr:{h} {caidos}_rows_offloaded>>")
        return _ResultadoArray(resultado, analise.recommended_strategy)

    def execute_plan(self, plano, items: list) -> list:
        kept = [items[i] for i in sorted(plano.keep_indices) if i < len(items)]
        if self.config.factor_out_constants and plano.constant_fields and len(kept) >= 2:
            tirou = False
            novos = []
            for item in kept:
                if isinstance(item, dict):
                    for k, const in plano.constant_fields.items():
                        if k in item and item[k] == const:
                            item = swap_remove(item, k)
                            tirou = True
                novos.append(item)
            kept = novos
            if tirou:
                kept.insert(0, {"_constant_fields": dict(plano.constant_fields)})
        return kept

    def crush_mixed_array(self, items: list, query: str, bias: float):
        n = len(items)
        if n <= 8:
            return list(items), "mixed:passthrough"
        if self.config.lossless_only:
            return list(items), "mixed:lossless_only"
        grupos: dict[str, tuple[list, list]] = {}
        for i, it in enumerate(items):
            idx, vals = grupos.setdefault(_group_key(it), ([], []))
            idx.append(i)
            vals.append(it)
        manter: set[int] = set()
        partes: list[str] = []
        for tipo, (indices, valores) in grupos.items():
            if len(valores) < self.config.min_items_to_analyze:
                manter.update(indices)
                continue
            if tipo == "dict":
                crushed = self.crush_array(valores, query, bias).items
                chaves = {python_json_dumps_sort_keys(v) for v in crushed}
                for i, idx in enumerate(indices):
                    if python_json_dumps_sort_keys(valores[i]) in chaves:
                        manter.add(idx)
                partes.append(f"dict:{len(valores)}->{len(crushed)}")
            elif tipo == "str":
                crushed, _ = crush_string_array(valores, self.config, bias)
                conj = set(crushed)
                for i, idx in enumerate(indices):
                    if valores[i] in conj:
                        manter.add(idx)
                partes.append(f"str:{len(valores)}->{len(crushed)}")
            elif tipo == "number":
                _, kf, kl, _ = compute_k_split([dumps(v) for v in valores], self.config, bias)
                kf = min(kf, len(valores))
                kl = min(kl, max(0, len(valores) - kf))
                manter.update(indices[:kf])
                if kl:
                    manter.update(indices[-kl:])
                finitos = [f for f in (as_f64(v) for v in valores) if f is not None and f == f and abs(f) != float("inf")]
                if len(finitos) > 1:
                    m = mean(finitos)
                    dp = sample_stdev(finitos)
                    if m is not None and dp is not None and dp > 0.0:
                        lim = self.config.variance_threshold * dp
                        for i, v in enumerate(valores):
                            f = as_f64(v)
                            if f is not None and f == f and abs(f) != float("inf") and abs(f - m) > lim:
                                manter.add(indices[i])
                partes.append(f"num:{len(valores)}")
            else:
                manter.update(indices)
        resultado = [items[i] for i in sorted(manter)]
        return resultado, f"mixed:adaptive({n}->{len(resultado)},{','.join(partes)})"

    def _sentinela_escalar(self, kept: list, original: list) -> None:
        caidos = max(0, len(original) - len(kept))
        if caidos == 0 or not self.config.enable_ccr_marker:
            return
        canonico = dumps(list(original))
        h = hash_canonical(canonico)
        self.ccr_store.put(h, canonico)
        kept.append(f"… {caidos} more items <<ccr:{h} {caidos}_items_offloaded>>")
