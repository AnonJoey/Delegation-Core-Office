"""O catalogo de erros visiveis e gerado do codigo e nao pode ficar velho."""

from __future__ import annotations

import re

from delegation_core import catalogo_erros


def test_csv_em_dia_com_o_codigo():
    assert catalogo_erros.DOC.read_text(encoding="utf-8") == catalogo_erros.gerar_csv(), (
        "docs/erros-visiveis.csv esta velho: delegation-core errors-catalog --write")


def test_erro_consertavel_diz_como():
    """A regra do erros.dependencia_ausente: dizer que da para consertar e esconder como e o pior caso."""
    ruins = [(l["function"], l["message"]) for l in catalogo_erros.linhas()
             if l["error_type"] in ("missing_dependency", "disabled") and not l["has_remedy"]]
    assert ruins == []


def test_nenhum_erro_cru_na_fronteira_mcp():
    texto = catalogo_erros.SERVER.read_text(encoding="utf-8")
    assert not re.search(r'return json\.dumps\(\{"error":', texto)


def test_ordem_por_dano():
    ls = catalogo_erros.linhas()
    assert [l["harm_rank"] for l in ls] == list(range(1, len(ls) + 1))
    assert ls[0]["error_type"] == "failure" or not ls[0]["has_remedy"]
