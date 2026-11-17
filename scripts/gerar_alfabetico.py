"""Gera `src/delegation_core/texto_alfabetico.py`: o que `char::is_alphabetic` do Rust chama de letra e `str.isalpha` do Python nao.

Uso: python scripts/gerar_alfabetico.py   (precisa do oraculo compilado, ver paridade_ai_memory.py)

A propriedade Unicode `Alphabetic` do Rust inclui os numeros-letra (Nl, como Ⅶ e 〇) e as marcas de
`Other_Alphabetic` (vogais combinantes de escritas indicas), que `isalpha` deixa de fora. O arquivo
gerado guarda so a diferenca: as faixas que o Rust diz serem letra e o Python nao.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORACULO = RAIZ / "scripts/oraculo_ai_memory/target/release/oraculo-ai-memory"
SAIDA = RAIZ / "src/delegation_core/texto_alfabetico.py"


def main() -> int:
    r = subprocess.run([str(ORACULO)], input='{"op":"alfabeticos"}\n', capture_output=True, text=True, check=True)
    faixas = json.loads(r.stdout.strip())["faixas"]
    rust = set()
    for lo, hi in faixas:
        rust.update(range(lo, hi + 1))
    so_python = [cp for cp in range(0x110000) if chr(cp).isalpha() and cp not in rust and not (0xD800 <= cp <= 0xDFFF)]
    so_rust = sorted(rust - {cp for cp in range(0x110000) if chr(cp).isalpha()})
    diferenca: list[list[int]] = []
    for cp in so_rust:
        if diferenca and diferenca[-1][1] + 1 == cp:
            diferenca[-1][1] = cp
        else:
            diferenca.append([cp, cp])
    por_categoria: dict[str, int] = {}
    for cp in so_rust:
        c = unicodedata.category(chr(cp))
        por_categoria[c] = por_categoria.get(c, 0) + 1
    linhas = ", ".join(f"({a:#x}, {b:#x})" for a, b in diferenca)
    SAIDA.write_text(
        '"""Letras que o Rust conta e o Python nao. GERADO por `scripts/gerar_alfabetico.py`; nao edite a mao.\n\n'
        "`char::is_alphabetic` (propriedade Unicode Alphabetic) aceita os numeros-letra e as marcas Other_Alphabetic;\n"
        "`str.isalpha` nao. Aqui estao so as faixas da diferenca, em pontos de codigo, inclusivas.\n"
        f"Gerado com o oraculo do ai-memory 584ab792: {len(so_rust)} pontos de codigo em {len(diferenca)} faixas.\n"
        '"""\n\n'
        f"FAIXAS = ({linhas})\n", encoding="utf-8")
    print(f"{len(so_rust)} pontos de codigo em {len(diferenca)} faixas; categorias: {por_categoria}; so no Python: {len(so_python)}")
    return 1 if so_python else 0


if __name__ == "__main__":
    sys.exit(main())
