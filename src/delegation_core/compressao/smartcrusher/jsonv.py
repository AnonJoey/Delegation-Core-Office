"""JSON com a semantica do serde_json do Headroom (`preserve_order` + `arbitrary_precision`).

- Objeto: `dict` (ordem de insercao; chave repetida fica na posicao da
  primeira com o valor da ultima, como o IndexMap). Igualdade sem ordem.
- Numero: `Num`, que guarda o texto original. `1.0` e `1.00` sao diferentes e
  voltam escritos como vieram; `as_f64` da o valor.
- `loads` recusa NaN e Infinity, como o serde.
- `dumps` e o `serde_json::to_string`: compacto, sem escapar o que nao e
  controle. `python_json_dumps*` sao as tres imitacoes do `json.dumps` do
  Python que o anchor_selector.rs escreve a mao.
"""

from __future__ import annotations

import json


class Num:
    __slots__ = ("raw",)

    def __init__(self, raw: str):
        self.raw = raw

    def __eq__(self, outro):
        return isinstance(outro, Num) and outro.raw == self.raw

    def __hash__(self):
        return hash(("Num", self.raw))

    def __repr__(self):
        return f"Num({self.raw})"

    def as_f64(self) -> float:
        return float(self.raw)


def _recusa(c):
    raise ValueError(f"invalid JSON constant {c}")


def loads(texto: str):
    return json.loads(texto, parse_float=Num, parse_int=Num, parse_constant=_recusa,
                      object_pairs_hook=dict)


def is_num(v) -> bool:
    return isinstance(v, Num)


def as_f64(v):
    """`Value::as_f64`: so numero; bool e texto dao None."""
    return v.as_f64() if isinstance(v, Num) else None


_CURTO = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _str_serde(s: str) -> str:
    out = ['"']
    for c in s:
        e = _CURTO.get(c)
        if e is not None:
            out.append(e)
        elif ord(c) < 0x20:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    out.append('"')
    return "".join(out)


def dumps(v) -> str:
    """`serde_json::to_string`."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return _str_serde(v)
    if isinstance(v, list):
        return "[" + ",".join(dumps(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ",".join(_str_serde(k) + ":" + dumps(x) for k, x in v.items()) + "}"
    raise TypeError(f"not a JSON value: {type(v).__name__}")


def _str_python(s: str, ensure_ascii: bool) -> str:
    out = ['"']
    for c in s:
        o = ord(c)
        if c == '"':
            out.append('\\"')
        elif c == "\\":
            out.append("\\\\")
        elif c in "\b\t\n\f\r":
            out.append({"\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}[c])
        elif o < 0x20:
            out.append(f"\\u{o:04x}")
        elif o <= 0x7E or not ensure_ascii:
            out.append(c)
        elif o <= 0xFFFF:
            out.append(f"\\u{o:04x}")
        else:
            cp = o - 0x10000
            out.append(f"\\u{0xD800 + (cp >> 10):04x}\\u{0xDC00 + (cp & 0x3FF):04x}")
    out.append('"')
    return "".join(out)


def _python(v, sort_keys: bool, compact: bool, ensure_ascii: bool) -> str:
    sep_item, sep_kv = (",", ":") if compact else (", ", ": ")
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, Num):
        return v.raw
    if isinstance(v, str):
        return _str_python(v, ensure_ascii)
    if isinstance(v, list):
        return "[" + sep_item.join(_python(x, sort_keys, compact, ensure_ascii) for x in v) + "]"
    if isinstance(v, dict):
        chaves = sorted(v, key=lambda k: k.encode("utf-8")) if sort_keys else list(v)
        return "{" + sep_item.join(_str_python(k, ensure_ascii) + sep_kv + _python(v[k], sort_keys, compact, ensure_ascii)
                                   for k in chaves) + "}"
    raise TypeError(f"not a JSON value: {type(v).__name__}")


def python_json_dumps_sort_keys(v) -> str:
    return _python(v, True, False, True)


def python_json_dumps(v) -> str:
    return _python(v, False, False, True)


def python_safe_json_dumps(v) -> str:
    return _python(v, False, True, False)
