"""Compactacao sem perda do SmartCrusher: `smart_crusher/compaction/*.rs`.

Um array de objetos vira uma tabela (`[N]{campo:tipo,...}` seguida de linhas
CSV) ou, quando os objetos sao heterogeneos e ha um campo discriminador,
baldes de tabelas. Strings opacas grandes (base64, HTML, texto longo) viram
marcadores `<<ccr:hash,tipo,tamanho>>` e o original vai para o store CCR.

Os tipos do `ir.rs` sao dataclasses; `OpaqueKind` e so a string do rotulo.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from . import jsonv
from .jsonv import Num

CCR_MARKER_PREFIX = "<<ccr:"

# `char::is_whitespace` do Rust (propriedade White_Space). O `str.isspace`
# do Python inclui tambem U+001C..U+001F, que o Rust nao considera.
_ESPACOS = frozenset(
    "\t\n\x0b\x0c\r \x85\xa0        "
    "        　"
)


def trim_start(s: str) -> str:
    i = 0
    while i < len(s) and s[i] in _ESPACOS:
        i += 1
    return s[i:]


def nbytes(s: str) -> int:
    return len(s.encode("utf-8"))


# --- ir.rs -------------------------------------------------------------------

@dataclass
class FieldSpec:
    name: str
    type_tag: str
    nullable: bool


@dataclass
class Schema:
    fields: list


@dataclass
class Scalar:
    value: object


@dataclass
class Nested:
    compaction: object


@dataclass
class OpaqueCell:
    ccr_hash: str
    byte_size: int
    kind: str


class _Missing:
    __slots__ = ()

    def __repr__(self):
        return "Missing"


MISSING = _Missing()


@dataclass
class Bucket:
    key: object
    schema: Schema
    rows: list


@dataclass
class Table:
    schema: Schema
    rows: list
    original_count: int


@dataclass
class Buckets:
    discriminator: str
    buckets: list
    original_count: int


@dataclass
class OpaqueRef:
    ccr_hash: str
    byte_size: int
    kind: str


@dataclass
class Untouched:
    value: object


def was_compacted(c) -> bool:
    return isinstance(c, (Table, Buckets, OpaqueRef))


def kept_row_count(c) -> int:
    if isinstance(c, Table):
        return len(c.rows)
    if isinstance(c, Buckets):
        return sum(len(b.rows) for b in c.buckets)
    return 0


# --- classifier.rs -----------------------------------------------------------

@dataclass
class ClassifyConfig:
    opaque_min_bytes: int = 256
    base64_alphabet_ratio: float = 0.95
    html_min_open_brackets: int = 3
    emit_opaque_markers: bool = True


# Classes de celula: ("scalar",), ("object",), ("array",),
# ("stringified", valor), ("opaque", tipo).

def _parse_container(s: str):
    try:
        v = jsonv.loads(s)
    except (ValueError, RecursionError):
        return None
    return v if isinstance(v, (dict, list)) else None


def classify_cell(value, cfg: ClassifyConfig):
    if isinstance(value, dict):
        return ("object",)
    if isinstance(value, list):
        return ("array",)
    if isinstance(value, str):
        return _classify_string(value, cfg)
    return ("scalar",)


def _classify_string(s: str, cfg: ClassifyConfig):
    if CCR_MARKER_PREFIX in s:
        return ("scalar",)
    t = trim_start(s)
    if t[:1] in ("{", "["):
        parsed = _parse_container(s)
        if parsed is not None:
            return ("stringified", parsed)
    if nbytes(s) <= cfg.opaque_min_bytes or not cfg.emit_opaque_markers:
        return ("scalar",)
    if looks_like_base64(s, cfg.base64_alphabet_ratio):
        return ("opaque", "base64")
    if looks_like_html(s, cfg.html_min_open_brackets):
        return ("opaque", "html")
    return ("opaque", "string")


def _b64_char(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z") or ("0" <= c <= "9") or c in "+/=_-"


def looks_like_base64(s: str, ratio_threshold: float) -> bool:
    total = nbytes(s)
    if total < 64:
        return False
    if "<" in s or ">" in s:
        return False
    if any(c in _ESPACOS for c in s):
        return False
    # O Rust divide contagem de caracteres por contagem de bytes.
    alphabet = sum(1 for c in s if _b64_char(c))
    if alphabet / total < ratio_threshold:
        return False
    unicos = set()
    for c in s:
        unicos.add(c)
        if len(unicos) >= 16:
            return True
    return False


def looks_like_html(s: str, min_open_brackets: int) -> bool:
    if s.count("<") < min_open_brackets:
        return False
    b = s.encode("utf-8")
    tags = 0
    for i in range(len(b) - 1):
        if b[i] == 0x3C:
            n = b[i + 1]
            if (0x41 <= n <= 0x5A) or (0x61 <= n <= 0x7A) or n in (0x2F, 0x21):
                tags += 1
    return tags >= min_open_brackets


# --- compactor.rs ------------------------------------------------------------

@dataclass
class CompactConfig:
    classify: ClassifyConfig = field(default_factory=ClassifyConfig)
    min_items: int = 2
    core_field_fraction: float = 0.8
    heterogeneous_core_ratio: float = 0.6
    max_flatten_inner_keys: int = 6
    min_buckets: int = 2
    max_buckets: int = 8


def _hash6(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).digest()[:6].hex()


def compact(items: list, cfg: CompactConfig, store=None):
    """`compact_with_store`. `store` tem `put(hash, payload)`."""
    if len(items) < cfg.min_items:
        return Untouched(list(items))
    if not all(isinstance(v, dict) for v in items):
        return Untouched(list(items))
    freqs = _key_freqs(items)
    total = len(items)
    core_threshold = _ceil(total * cfg.core_field_fraction)
    core_count = sum(1 for f in freqs.values() if f >= core_threshold)
    core_ratio = 1.0 if not freqs else core_count / len(freqs)
    if core_ratio < cfg.heterogeneous_core_ratio:
        disc = _detect_discriminator(items, freqs, cfg)
        if disc is not None:
            return _bucket_by(items, disc, cfg, store)
    return _homogeneous_table(items, freqs, cfg, store)


def _ceil(x: float) -> int:
    i = int(x)
    return i + 1 if i < x else i


def _btree_items(d: dict):
    """Ordem do BTreeMap<String, _>: bytes UTF-8."""
    return sorted(d.items(), key=lambda kv: kv[0].encode("utf-8"))


def _key_freqs(items) -> dict:
    freqs: dict = {}
    for it in items:
        for k in it:
            freqs[k] = freqs.get(k, 0) + 1
    return dict(_btree_items(freqs))


def _homogeneous_table(items, freqs, cfg, store):
    # sort estavel por frequencia decrescente e nome crescente
    ordered = [k for k, _ in sorted(freqs.items(), key=lambda kv: (-kv[1], kv[0].encode("utf-8")))]
    total = len(items)
    specs = [
        FieldSpec(k, _infer_type_tag(items, k),
                  freqs[k] < total or any(k in o and o[k] is None for o in items))
        for k in ordered
    ]
    rows = [_build_row(it, ordered, cfg, store) for it in items]
    _flatten_uniform_nested(specs, rows, cfg)
    return Table(Schema(specs), rows, len(items))


def _build_row(item, ordered, cfg, store):
    return [(_cell_from_value(item[k], cfg, store) if k in item else MISSING) for k in ordered]


def _all_objects_2plus(v) -> bool:
    return isinstance(v, list) and len(v) >= 2 and all(isinstance(i, dict) for i in v)


def _cell_from_value(v, cfg: CompactConfig, store):
    cls = classify_cell(v, cfg.classify)
    tag = cls[0]
    if tag in ("scalar", "object"):
        return Scalar(v)
    if tag == "array":
        if _all_objects_2plus(v):
            return Nested(compact(v, cfg, store))
        return Scalar(v)
    if tag == "stringified":
        parsed = cls[1]
        if _all_objects_2plus(parsed):
            return Nested(compact(parsed, cfg, store))
        return Scalar(parsed)
    # opaque
    if not isinstance(v, str):
        return Scalar(v)
    h = _hash6(v)
    if store is not None:
        store.put(h, v)
    return OpaqueCell(h, nbytes(v), cls[1])


def _flatten_uniform_nested(specs: list, rows: list, cfg: CompactConfig):
    i = 0
    while i < len(specs):
        inner = _uniform_object_keys(specs, rows, i)
        if not inner or len(inner) > cfg.max_flatten_inner_keys:
            i += 1
            continue
        parent = specs[i].name
        novos = [FieldSpec(f"{parent}.{k}", "string", False) for k in inner]
        n = len(novos)
        specs[i:i + 1] = novos
        for row in rows:
            original = row.pop(i)
            obj = original.value if isinstance(original, Scalar) else None
            expandido = [
                MISSING if obj is None or k not in obj else Scalar(obj[k])
                for k in inner
            ]
            row[i:i] = expandido
        for off in range(n):
            col = i + off
            tag, nullable = _infer_type_tag_from_cells(rows, col)
            specs[col].type_tag = tag
            specs[col].nullable = nullable
        i += n


def _infer_type_tag_from_cells(rows, col):
    tag = "string"
    saw = False
    nullable = False
    for row in rows:
        if col >= len(row):
            continue
        cell = row[col]
        if cell is MISSING:
            nullable = True
        elif isinstance(cell, Scalar):
            if cell.value is None:
                nullable = True
            elif not saw:
                tag = type_tag_for(cell.value)
                saw = True
            elif type_tag_for(cell.value) != tag:
                tag = "json"
        else:
            tag = "json"
    return tag, nullable


def _uniform_object_keys(specs, rows, col):
    if "." in specs[col].name:
        return None
    canonical = None
    saw = False
    for row in rows:
        if col >= len(row):
            return None
        cell = row[col]
        if cell is MISSING:
            continue
        if isinstance(cell, Scalar) and isinstance(cell.value, dict):
            keys = list(cell.value)
            saw = True
            if canonical is None:
                canonical = keys
            elif canonical != keys:
                return None
        else:
            return None
    if not saw:
        return None
    return canonical


def _infer_type_tag(items, key):
    tag = None
    for it in items:
        if key not in it:
            continue
        v = it[key]
        if v is None:
            continue
        t = type_tag_for(v)
        if tag is None:
            tag = t
        elif tag != t:
            tag = "json"
            break
    return tag or "string"


_I64 = (-(1 << 63), (1 << 63) - 1)
_U64_MAX = (1 << 64) - 1


def num_is_integer(n: Num) -> bool:
    """`is_i64() || is_u64()` com arbitrary_precision: o texto cabe num inteiro."""
    raw = n.raw
    corpo = raw[1:] if raw.startswith("-") else raw
    if not corpo.isdigit() or not corpo.isascii():
        return False
    v = int(raw)
    return _I64[0] <= v <= _U64_MAX


def type_tag_for(v) -> str:
    if v is None:
        return "null"
    if v is True or v is False:
        return "bool"
    if isinstance(v, Num):
        return "int" if num_is_integer(v) else "float"
    if isinstance(v, str):
        return "string"
    return "json"


def _detect_discriminator(items, freqs, cfg):
    total = len(items)
    best = None
    best_score = 0
    for k, f in freqs.items():
        if f < total:
            continue
        valores = []
        ok = True
        for it in items:
            v = it.get(k)
            if not isinstance(v, str):
                ok = False
                break
            valores.append(v)
        if not ok:
            continue
        n = len(set(valores))
        if n < cfg.min_buckets or n > cfg.max_buckets:
            continue
        if n / total > 0.7:
            continue
        if best is None or n > best_score:
            best, best_score = k, n
    return best


def _bucket_by(items, disc, cfg, store):
    grupos: dict = {}
    for it in items:
        v = it.get(disc)
        chave = v if isinstance(v, str) else "__missing__"
        grupos.setdefault(chave, []).append(it)
    buckets = []
    for chave, grupo in _btree_items(grupos):
        inner = compact(grupo, cfg, store)
        if isinstance(inner, Table):
            buckets.append(Bucket(chave, inner.schema, inner.rows))
        else:
            buckets.append(Bucket(chave, Schema([FieldSpec("value", "json", False)]),
                                  [[Scalar(v)] for v in grupo]))
    return Buckets(disc, buckets, len(items))


# --- formatter.rs ------------------------------------------------------------

def humanize_bytes(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    kb = n / 1024.0
    if kb < 1024.0:
        return f"{kb:.1f}KB"
    return f"{kb / 1024.0:.1f}MB"


def format_ccr_marker(h: str, size: int, kind: str) -> str:
    return f"<<ccr:{h},{kind},{humanize_bytes(size)}>>"


def _schema_json(s: Schema) -> list:
    out = []
    for f in s.fields:
        o = {"name": f.name, "type": f.type_tag}
        if f.nullable:
            o["nullable"] = True
        out.append(o)
    return out


def _cell_json(c):
    if isinstance(c, Scalar):
        return c.value
    if c is MISSING:
        return None
    if isinstance(c, Nested):
        return compaction_to_json(c.compaction)
    return {"_ccr": c.ccr_hash, "_size": Num(str(c.byte_size)), "_kind": c.kind}


def compaction_to_json(c):
    # `json!` sem preserve_order desligado: o crate usa preserve_order, entao
    # as chaves saem na ordem escrita.
    if isinstance(c, Table):
        return {"_compaction": "table", "_schema": _schema_json(c.schema),
                "_kept": Num(str(len(c.rows))), "_total": Num(str(c.original_count)),
                "_rows": [[_cell_json(x) for x in r] for r in c.rows]}
    if isinstance(c, Buckets):
        return {"_compaction": "buckets", "_discriminator": c.discriminator,
                "_total": Num(str(c.original_count)),
                "_buckets": [{"_key": b.key, "_schema": _schema_json(b.schema),
                              "_rows": [[_cell_json(x) for x in r] for r in b.rows]}
                             for b in c.buckets]}
    if isinstance(c, OpaqueRef):
        return {"_compaction": "ccr", "_hash": c.ccr_hash,
                "_size": Num(str(c.byte_size)), "_kind": c.kind}
    return c.value


class JsonFormatter:
    name = "json"

    def format(self, c) -> str:
        return jsonv.dumps(compaction_to_json(c))


def _csv_quote(s: str) -> str:
    return '"' + s.replace('"', '""') + '"'


def _needs_csv_quote(s: str) -> bool:
    return "," in s or '"' in s or "\n" in s or "\r" in s


def _csv_scalar(v) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        if v == "" or v == "null" or _needs_csv_quote(v):
            return _csv_quote(v)
        return v
    return _csv_quote(jsonv.dumps(v))


class CsvSchemaFormatter:
    name = "csv-schema"

    def __init__(self, include_drop_summary: bool = False):
        self.include_drop_summary = include_drop_summary

    def format(self, c) -> str:
        out: list = []
        self._compaction(out, c)
        return "".join(out)

    def _compaction(self, out, c):
        if isinstance(c, Table):
            self._table(out, c.schema, c.rows, c.original_count)
        elif isinstance(c, Buckets):
            out.append("__buckets:" + c.discriminator)
            if self.include_drop_summary:
                kept = sum(len(b.rows) for b in c.buckets)
                if kept < c.original_count:
                    out.append(f" __dropped:{c.original_count - kept}")
            out.append("\n")
            for b in c.buckets:
                out.append(f"__key:{_csv_scalar(b.key)}\n")
                self._table(out, b.schema, b.rows, len(b.rows))
        elif isinstance(c, OpaqueRef):
            out.append(format_ccr_marker(c.ccr_hash, c.byte_size, c.kind))
        else:
            out.append(jsonv.dumps(c.value))

    def _table(self, out, schema, rows, original_count):
        decl = ",".join(f"{f.name}:{f.type_tag}?" if f.nullable else f"{f.name}:{f.type_tag}"
                        for f in schema.fields)
        out.append(f"[{len(rows)}]{{{decl}}}")
        if self.include_drop_summary and len(rows) < original_count:
            out.append(f" __dropped:{original_count - len(rows)}")
        out.append("\n")
        for row in rows:
            out.append(",".join(self._cell(x) for x in row))
            out.append("\n")

    @staticmethod
    def _cell(c) -> str:
        if c is MISSING:
            return ""
        if isinstance(c, Scalar):
            return _csv_scalar(c.value)
        if isinstance(c, Nested):
            return _csv_quote(JsonFormatter().format(c.compaction))
        return format_ccr_marker(c.ccr_hash, c.byte_size, c.kind)


def _needs_kv_quote(s: str) -> bool:
    return (s == "" or "\n" in s or "\r" in s
            or s[0] in _ESPACOS or s[-1] in _ESPACOS)


def _kv_scalar(v) -> str:
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return jsonv.dumps(v) if _needs_kv_quote(v) else v
    return jsonv.dumps(v)


def _kv_field_name(name: str) -> str:
    return jsonv.dumps(name) if _needs_kv_quote(name) or ": " in name else name


class MarkdownKvFormatter:
    name = "markdown-kv"

    def __init__(self, include_drop_summary: bool = False):
        self.include_drop_summary = include_drop_summary

    def format(self, c) -> str:
        out: list = []
        if isinstance(c, Table):
            self._table(out, c.schema, c.rows, c.original_count)
        elif isinstance(c, Buckets):
            out.append("__buckets:" + c.discriminator)
            if self.include_drop_summary:
                kept = sum(len(b.rows) for b in c.buckets)
                if kept < c.original_count:
                    out.append(f" __dropped:{c.original_count - kept}")
            out.append("\n")
            for b in c.buckets:
                out.append(f"__key:{_kv_scalar(b.key)}\n")
                self._table(out, b.schema, b.rows, len(b.rows))
        elif isinstance(c, OpaqueRef):
            out.append(format_ccr_marker(c.ccr_hash, c.byte_size, c.kind))
        else:
            out.append(jsonv.dumps(c.value))
        return "".join(out)

    def _table(self, out, schema, rows, original_count):
        decl = ",".join(
            f"{_kv_field_name(f.name)}:{f.type_tag}?" if f.nullable
            else f"{_kv_field_name(f.name)}:{f.type_tag}"
            for f in schema.fields)
        out.append(f"[{len(rows)}]{{{decl}}}")
        if self.include_drop_summary and len(rows) < original_count:
            out.append(f" __dropped:{original_count - len(rows)}")
        out.append("\n")
        for row in rows:
            primeiro = False
            for f, cell in zip(schema.fields, row):
                if cell is MISSING:
                    continue
                if isinstance(cell, Scalar):
                    r = _kv_scalar(cell.value)
                elif isinstance(cell, Nested):
                    r = JsonFormatter().format(cell.compaction)
                else:
                    r = format_ccr_marker(cell.ccr_hash, cell.byte_size, cell.kind)
                out.append("  " if primeiro else "- ")
                out.append(_kv_field_name(f.name) + ": " + r + "\n")
                primeiro = True
            if not primeiro:
                out.append("-\n")


FORMATADORES = {"csv-schema": CsvSchemaFormatter, "json": JsonFormatter,
                "markdown-kv": MarkdownKvFormatter}


# --- mod.rs: CompactionStage -------------------------------------------------

class CompactionStage:
    def __init__(self, config: CompactConfig | None = None, formatter=None):
        self.config = config or CompactConfig()
        self.formatter = formatter or CsvSchemaFormatter()

    @classmethod
    def from_format_name(cls, name: str):
        f = FORMATADORES.get(name)
        return None if f is None else cls(CompactConfig(), f())

    def run(self, items: list, store=None):
        c = compact(items, self.config, store)
        return c, self.formatter.format(c)


# --- walker.rs ---------------------------------------------------------------

def try_parse_json_container(s: str):
    if trim_start(s)[:1] not in ("{", "["):
        return None
    return _parse_container(s)


def emit_opaque_ccr_marker(payload: str, kind: str, store=None) -> str:
    h = _hash6(payload)
    if store is not None:
        store.put(h, payload)
    return f"<<ccr:{h},{kind},{humanize_bytes(nbytes(payload))}>>"


class DocumentCompactor:
    def __init__(self, config: CompactConfig | None = None, formatter=None, store=None):
        self.config = config or CompactConfig()
        self.formatter = formatter or CsvSchemaFormatter()
        self.store = store

    def compact(self, doc):
        return self._walk(doc)

    def _walk(self, v):
        if isinstance(v, dict):
            return {k: self._walk(x) for k, x in v.items()}
        if isinstance(v, list):
            inner = [self._walk(i) for i in v]
            c = compact(inner, self.config, self.store)
            return self.formatter.format(c) if was_compacted(c) else inner
        if isinstance(v, str):
            parsed = try_parse_json_container(v)
            if parsed is not None:
                r = self._walk(parsed)
                return r if isinstance(r, str) else jsonv.dumps(r)
            cls = classify_cell(v, self.config.classify)
            if cls[0] == "opaque":
                return emit_opaque_ccr_marker(v, cls[1], self.store)
            return v
        return v


def compact_document(doc):
    return DocumentCompactor().compact(doc)
