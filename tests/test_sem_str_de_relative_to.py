"""Nenhum modulo monta caminho relativo com `str(x.relative_to(y))`.

No Windows isso sai com barra invertida, e caminho de nota do vault e sempre POSIX
(`test_caminhos_posix.py` mede o comportamento, mas so no Windows). O porte do
delegation-core-TEST em 17/11/2026 trouxe 23 desses de uma vez, e a CI do Windows achou
103 falhas antes da correcao. Esta guarda e estatica: roda em qualquer sistema e aponta o
arquivo e a linha antes de a CI do Windows precisar achar.

Limite: so ve a forma direta. `rel = p.relative_to(r)` seguido de `str(rel)` passa por ela
(era o caso do `codigo_vault`); esse continua por conta da CI do Windows.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "delegation_core"

#: Usos que nao sao caminho de nota do vault, cada um com o motivo.
PERMITIDOS = {
    ("installer.py", "CONFIG_DIR"),       # so para mostrar o que foi removido ou sobrou
    ("graph/extractors/resolution.py", "root"),   # caminho de codigo no grafo, anterior ao porte
    ("graph/detect.py", "anchor"),                 # idem
    ("installer.py", "base"),             # seguido de .replace("\\", "/") na mesma expressao
}


def _achados():
    for arq in sorted(RAIZ.rglob("*.py")):
        rel = arq.relative_to(RAIZ).as_posix()
        arvore = ast.parse(arq.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "str"
                    and len(no.args) == 1):
                continue
            dentro = no.args[0]
            if (isinstance(dentro, ast.Call) and isinstance(dentro.func, ast.Attribute)
                    and dentro.func.attr == "relative_to"):
                base = ast.unparse(dentro.args[0]) if dentro.args else ""
                if any(rel == a and b in base for a, b in PERMITIDOS):
                    continue
                yield f"{rel}:{no.lineno}: {ast.unparse(no)}"


def test_nenhum_str_de_relative_to():
    achados = list(_achados())
    assert not achados, "use .as_posix():\n" + "\n".join(achados)
