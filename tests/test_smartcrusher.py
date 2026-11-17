"""SmartCrusher portado do Rust, contra saidas gravadas do headroom-core real.

`fixtures/smartcrusher/oraculo.json.gz` foi gravado pelo `_core` compilado do
fonte do Headroom (nao por este codigo): 114 entradas, cada uma rodada em oito
configuracoes. O porte tem que reproduzir texto, estrategia e `was_modified`
byte a byte. Para regravar com o oraculo, `scripts/paridade_smartcrusher.py --gravar`.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import re
from pathlib import Path

import pytest

from delegation_core.compressao import roteador
from delegation_core.compressao.smartcrusher import MemoriaCcr, SmartCrusher, SmartCrusherConfig
from delegation_core.compressao.smartcrusher.crusher import swap_remove

FIXTURE = Path(__file__).parent / "fixtures" / "smartcrusher" / "oraculo.json.gz"


def _gravado():
    with gzip.open(FIXTURE, "rt", encoding="utf-8") as f:
        return json.load(f)


_DADOS = _gravado()


def _crusher(kw, comp):
    return SmartCrusher(SmartCrusherConfig(**kw), compaction=comp)


@pytest.mark.parametrize("variante", sorted(_DADOS["variantes"]))
def test_igual_ao_oraculo(variante):
    kw, comp = _DADOS["variantes"][variante]
    sc = _crusher(kw, comp)
    erradas = []
    for i, caso in enumerate(_DADOS["casos"]):
        r = sc.crush(caso["content"], caso["query"], caso["bias"])
        if [r.compressed, r.strategy, r.was_modified] != caso["out"][variante]:
            erradas.append(i)
    assert erradas == [], f"{len(erradas)} casos divergem do oraculo em {variante}"


def test_fixture_cobre_os_caminhos():
    estrategias = " ".join(o[1] for c in _DADOS["casos"] for o in c["out"].values())
    for marca in ("lossless:table", "lossless:buckets", "smart_sample", "top_n", "skip:",
                  "string_ccr:base64", "string_ccr:html", "number:adaptive", "mixed:adaptive",
                  "none:adaptive_at_limit", "lossless_only:uncompacted", "passthrough"):
        assert marca in estrategias, marca


def test_string_null_vai_entre_aspas_na_tabela():
    d = json.dumps([{"id": i, "v": ["null", "", None, "a,b"][i % 4], "w": "x" * 20} for i in range(40)])
    out = json.loads(SmartCrusher().crush(d).compressed)
    linhas = out.split("\n")
    assert linhas[0] == "[40]{id:int,v:string?,w:string}"
    assert linhas[1:5] == ['0,"null",' + "x" * 20, '1,"",' + "x" * 20, "2,null," + "x" * 20, '3,"a,b",' + "x" * 20]


def test_swap_remove_do_indexmap():
    assert list(swap_remove({"ts": 1, "level": 2, "msg": 3, "line": 4}, "level")) == ["ts", "line", "msg"]
    assert list(swap_remove({"a": 1, "b": 2}, "b")) == ["a"]


def test_cortado_volta_inteiro_pelo_store():
    store = MemoriaCcr()
    itens = [{"id": i, "nome": f"item {i}", "valor": i * 3, "nota": "texto " * (i % 5)} for i in range(60)]
    sc = SmartCrusher(compaction=False, store=store)
    r = sc.crush(json.dumps(itens))
    h = re.search(r"<<ccr:([0-9a-f]{12}) (\d+)_rows_offloaded>>", r.compressed)
    assert h, r.strategy
    assert json.loads(store.get(h.group(1))) == itens


def test_nao_json_passa_igual():
    r = SmartCrusher().crush("isso nao e json")
    assert (r.compressed, r.was_modified, r.strategy) == ("isso nao e json", False, "passthrough")


def test_roteador_e_recall_output():
    import delegation_core.server as server
    itens = [{"id": i, "nivel": "ERRO" if i % 13 == 0 else "INFO", "msg": f"evento {i} " + "x" * (i % 7)}
             for i in range(120)]
    r = roteador.comprimir(json.dumps(itens, indent=2), tipo="json")
    assert r["compressor"] == "smartcrusher" and r["shown_tokens"] < r["raw_tokens"]
    sc = SmartCrusher(compaction=False, store=roteador.Guarda())
    cortado = sc.crush(json.dumps(itens))
    h = re.search(r"<<ccr:([0-9a-f]{12})", cortado.compressed).group(1)
    volta = json.loads(server.recall_output(hash=h))
    assert json.loads(volta["output"]) == itens


def test_walker_igual_ao_oraculo():
    """`DocumentCompactor` contra `compact_document_json` do oraculo: compacta todo
    array de objetos sem o limite adaptativo, o que alcanca o discriminador de baldes."""
    from delegation_core.compressao.smartcrusher import compactacao as cp, jsonv
    erradas = [i for i, (entrada, esperado) in enumerate(_DADOS["walker"])
               if jsonv.dumps(cp.DocumentCompactor().compact(jsonv.loads(entrada))) != esperado]
    assert erradas == []
