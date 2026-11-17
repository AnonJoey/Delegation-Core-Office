"""Porte de `crates/headroom-core/src/transforms/adaptive_sizer.rs` (Headroom, Apache 2.0)."""

from __future__ import annotations

import hashlib
import zlib


def compute_optimal_k(items: list[str], bias: float = 1.0, min_k: int = 3, max_k: int | None = None) -> int:
    n = len(items)
    efetivo = n if max_k is None else max_k
    if n <= 8:
        return n
    unicos = count_unique_simhash(items, 3)
    if unicos <= 3:
        return min(max(min_k, unicos), efetivo)
    joelho = find_knee(compute_unique_bigram_curve(items))
    diversidade = unicos / n
    if joelho is None:
        joelho = max(min_k, int(n * (0.3 + 0.7 * diversidade)))
    elif diversidade > 0.7:
        joelho = max(joelho, max(min_k, int(n * (0.3 + 0.7 * diversidade))))
    k = max(min_k, int(joelho * bias))
    k = min(k, efetivo)
    k = validate_with_zlib(items, k, efetivo, 0.15)
    return max(min_k, min(k, efetivo))


def find_knee(curva: list[int]) -> int | None:
    n = len(curva)
    if n < 3:
        return None
    y_min, y_max = float(curva[0]), float(curva[-1])
    if abs(y_max - y_min) < 2.220446049250313e-16:
        return 1
    x_range, y_range = float(n - 1), y_max - y_min
    maior, idx = -1.0, None
    for i, y in enumerate(curva):
        diff = (y - y_min) / y_range - i / x_range
        if diff > maior:
            maior, idx = diff, i
    if maior < 0.05:
        return None
    return None if idx is None else idx + 1


def _cjk(c: str) -> bool:
    o = ord(c)
    return (0x3040 <= o <= 0x30FF or 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF
            or 0xAC00 <= o <= 0xD7AF or 0xF900 <= o <= 0xFAFF)


def compute_unique_bigram_curve(items: list[str]) -> list[int]:
    vistos: set = set()
    curva = []
    for item in items:
        palavras = item.lower().split()
        if len(palavras) >= 2:
            for j in range(len(palavras) - 1):
                vistos.add((palavras[j], palavras[j + 1]))
        elif palavras:
            w = palavras[0]
            if len(w) >= 2 and any(_cjk(c) for c in w):
                for j in range(len(w) - 1):
                    vistos.add((w[j], w[j + 1]))
            else:
                vistos.add((w, ""))
        else:
            vistos.add(("", ""))
        curva.append(len(vistos))
    return curva


def simhash(texto: str) -> int:
    s = texto.lower()
    n = len(s)
    votos = [0] * 64
    for i in range(1 if n <= 3 else n - 3):
        h = int.from_bytes(hashlib.md5(s[i:i + 4].encode("utf-8")).digest()[:8], "big")
        for j in range(64):
            votos[j] += 1 if (h >> j) & 1 else -1
    fp = 0
    for j, v in enumerate(votos):
        if v > 0:
            fp |= 1 << j
    return fp


def count_unique_simhash(items: list[str], limiar: int = 3) -> int:
    grupos: list[int] = []
    for fp in (simhash(s) for s in items):
        if not any(bin(fp ^ r).count("1") <= limiar for r in grupos):
            grupos.append(fp)
    return len(grupos)


def validate_with_zlib(items: list[str], k: int, max_k: int, tolerancia: float) -> int:
    if k >= len(items) or k >= max_k:
        return k
    cheio = "\n".join(items).encode("utf-8")
    parte = "\n".join(items[:k]).encode("utf-8")
    if len(cheio) < 200:
        return k
    r_cheio = len(zlib.compress(cheio, 1)) / len(cheio) if cheio else 1.0
    r_parte = len(zlib.compress(parte, 1)) / len(parte) if parte else 1.0
    if abs(r_cheio - r_parte) > tolerancia:
        return min(int(k * 1.2), max_k)
    return k
