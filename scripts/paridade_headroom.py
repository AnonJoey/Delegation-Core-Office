"""Paridade dos compressores portados (compressao/) com o nucleo Rust do Headroom.

Uso:
  1. Compile o binding do mesmo codigo que foi portado:
       maturin build --release -m <headroom>/crates/headroom-py/Cargo.toml -o /tmp/hr
     e extraia `headroom/_core*.so` do wheel.
  2. HEADROOM_CORE=/caminho/_core.abi3.so python scripts/paridade_headroom.py

Compara LogCompressor, DiffCompressor e SearchCompressor em logs sinteticos,
diffs do historico git deste repositorio e saidas de rg/grep neste repositorio.
Usar o pacote publicado (headroom-ai no PyPI) como oraculo mede contra outra
versao: em 05/10/2026 a 0.39.1 publicada divergia do main em 104 de 1029 logs.
"""

from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))


def _core():
    spec = importlib.util.spec_from_file_location("headroom._core", os.environ["HEADROOM_CORE"])
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class _G:
    def put(self, k, v):
        pass


def main() -> int:
    from delegation_core.compressao.busca import SearchCompressor
    from delegation_core.compressao.diff import DiffCompressor
    from delegation_core.compressao.logs import LogCompressor
    core = _core()
    rnd = random.Random(7)
    shas = subprocess.run(["git", "-C", str(RAIZ), "rev-list", "--max-count=200", "HEAD"],
                          capture_output=True, text=True).stdout.split()
    diffs = [subprocess.run(["git", "-C", str(RAIZ), "diff", shas[i + 1], shas[i]], capture_output=True,
                            text=True, errors="replace").stdout for i in range(0, len(shas) - 1, 2)]
    buscas = [subprocess.run(["rg", "-n"] + (["-C", "2"] if i % 2 else []) + [t, str(RAIZ / "src")],
                             capture_output=True, text=True).stdout
              for i, t in enumerate(["def ", "import", "error", "config", "return", "self\\.", "json", "Path"])]
    logs = []
    for _ in range(150):
        n = rnd.randint(60, 600)
        logs.append("\n".join(rnd.choice([f"INFO item {i}", f"WARNING slow {i}", f"ERROR failed {i % 7}",
                                          "Traceback (most recent call last):", f'  File "/a/b{i}.py", line {i}',
                                          f"tests/t.py::test_{i} PASSED", "", f"{i} passed, 1 failed"])
                              for i in range(n)))
    placar = {}
    for nome, itens, rust, py in (
        ("diff", diffs, lambda x: core.DiffCompressor(core.DiffCompressorConfig()).compress(x, ""),
         lambda x: DiffCompressor().compress(x, "", _G())),
        ("search", buscas, lambda x: core.SearchCompressor(core.SearchCompressorConfig()).compress(x, "", 1.0),
         lambda x: SearchCompressor().compress(x, "", 1.0, _G())),
        ("log", logs, lambda x: core.LogCompressor(core.LogCompressorConfig()).compress(x, 1.0),
         lambda x: LogCompressor().compress(x, 1.0, _G())),
    ):
        iguais = sum(rust(x).compressed == py(x).compressed for x in itens)
        placar[nome] = (iguais, len(itens))
        print(f"{nome:7} {iguais}/{len(itens)} identical")
    # O de logs pode divergir no tamanho do corte: o Rust mede com miniz_oxide, o porte com zlib.
    exatos = all(placar[k][0] == placar[k][1] for k in ("diff", "search"))
    return 0 if exatos and placar["log"][0] >= 0.95 * placar["log"][1] else 1


if __name__ == "__main__":
    raise SystemExit(main())
