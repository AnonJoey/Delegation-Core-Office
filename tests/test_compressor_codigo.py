"""Compressor de codigo por AST (6.3.1): porte do CodeAwareCompressor do Headroom.

A paridade roda o ORIGINAL (`~/Projects/headroom`) num subprocesso, com as MESMAS gramaticas: um
calco de `tree_sitter_language_pack` aponta para os pacotes `tree_sitter_<linguagem>` instalados.
Assim a comparacao mede a logica portada, nao diferenca de versao de gramatica. O corpus e codigo
de verdade desta maquina, sorteado por linguagem.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from pathlib import Path

import pytest

from delegation_core.compressao import roteador
from delegation_core.compressao.ccr import Guarda
from delegation_core.compressao.headroom_py.transforms import code_compressor as cc

HEADROOM = Path.home() / "Projects" / "headroom"
RAIZ = Path(__file__).resolve().parent.parent

FONTES = {
    "python": [RAIZ / "src" / "delegation_core"],
    "javascript": [RAIZ / "dashboard" / "src", Path.home() / "Projects" / "openclaw", Path.home() / "Projects" / "grafana" / "public"],
    "typescript": [Path.home() / "Projects" / "openclaw" / "src"],
    "go": [Path.home() / "Projects" / "grafana" / "pkg"],
    "rust": [Path.home() / "Projects" / "rtk" / "src"],
    "java": [Path.home() / "Projects"],
}
EXT = {"python": ".py", "javascript": ".js", "typescript": ".ts", "go": ".go", "rust": ".rs", "java": ".java"}


def _corpus(rnd: random.Random, por_lingua: int = 12) -> list[dict]:
    casos = []
    for lingua, pastas in FONTES.items():
        arquivos = []
        for pasta in pastas:
            if not pasta.exists():
                continue
            for p in pasta.rglob(f"*{EXT[lingua]}"):
                if ("node_modules" in p.parts or ".venv" in p.parts or "headroom_py" in p.parts
                        or "dist" in p.parts or p.name.endswith(".min.js")):
                    continue
                try:
                    if 1500 < p.stat().st_size < 40000:
                        arquivos.append(p)
                except OSError:
                    continue
                if len(arquivos) > 400:
                    break
        rnd.shuffle(arquivos)
        for p in arquivos[:por_lingua]:
            codigo = p.read_text(encoding="utf-8", errors="replace")
            nomes = re.findall(r"(?:def|function|func|fn|class)\s+([A-Za-z_]\w*)", codigo)
            contexto = rnd.choice(["", " ".join(rnd.sample(nomes, min(2, len(nomes))))]) if nomes else ""
            casos.append({"codigo": codigo, "lingua": rnd.choice([lingua, None]), "contexto": contexto,
                          "arquivo": str(p)})
    return casos


ORACULO = r'''
import importlib, json, sys, tempfile, os
calco = tempfile.mkdtemp()
with open(os.path.join(calco, "tree_sitter_language_pack.py"), "w") as f:
    f.write("""
import importlib
from tree_sitter import Language
_G = {"python": ("tree_sitter_python", "language"), "javascript": ("tree_sitter_javascript", "language"),
      "typescript": ("tree_sitter_typescript", "language_typescript"), "tsx": ("tree_sitter_typescript", "language_tsx"),
      "go": ("tree_sitter_go", "language"), "rust": ("tree_sitter_rust", "language"), "java": ("tree_sitter_java", "language")}
def get_language(nome):
    if nome not in _G:
        raise LookupError(nome)
    m, f = _G[nome]
    return Language(getattr(importlib.import_module(m), f)())
""")
sys.path.insert(0, calco)
sys.path.insert(0, sys.argv[1])
from headroom.transforms.code_compressor import CodeAwareCompressor, CodeCompressorConfig
# A reserva do compressor (linguagem desconhecida) e o Kompress, um modelo de ML cujo arquivo cada
# lado acha num lugar diferente: fora da paridade, que mede a logica portada. Desligado nos dois.
import headroom.transforms.kompress_compressor as _k
_k.is_kompress_available = lambda *a, **k: False
saida = []
for caso in json.load(sys.stdin):
    r = CodeAwareCompressor(CodeCompressorConfig(enable_ccr=False)).compress(
        caso["codigo"], language=caso["lingua"], context=caso["contexto"])
    saida.append({"compressed": r.compressed, "valid": r.syntax_valid, "language": r.language.value})
json.dump(saida, sys.stdout)
'''


@pytest.mark.skipif(not (HEADROOM / "headroom").exists(), reason="copia do Headroom nao esta nesta maquina")
def test_igual_ao_headroom_original_em_codigo_de_verdade(monkeypatch):
    from delegation_core.compressao.headroom_py.transforms import kompress_compressor as k
    monkeypatch.setattr(k, "is_kompress_available", lambda *a, **kw: False)
    casos = _corpus(random.Random(20261123))
    linguas = {c["arquivo"].rsplit(".", 1)[-1] for c in casos}
    assert "py" in linguas, "o corpus minimo (o Python do proprio repositorio) sumiu"
    p = subprocess.run([sys.executable, "-c", ORACULO, str(HEADROOM)], input=json.dumps(casos),
                       capture_output=True, text=True, timeout=600)
    assert p.returncode == 0, p.stderr[-1500:]
    esperado = json.loads(p.stdout)
    mudou = sum(e["compressed"] != c["codigo"] for c, e in zip(casos, esperado))
    assert mudou > len(casos) // 3, f"o original quase nao comprimiu ({mudou} de {len(casos)}): oraculo montado errado"
    for c, e in zip(casos, esperado):
        r = cc.CodeAwareCompressor(cc.CodeCompressorConfig(enable_ccr=False)).compress(
            c["codigo"], language=c["lingua"], context=c["contexto"])
        assert (r.compressed, r.syntax_valid, r.language.value) == (e["compressed"], e["valid"], e["language"]), c["arquivo"]


# ── roteador ──────────────────────────────────────────────────────────────────

CODIGO = (RAIZ / "src" / "delegation_core" / "compressao" / "pool.py").read_text(encoding="utf-8")


def test_kind_code_comprime_mantendo_sintaxe_e_guardando_o_original():
    r = roteador.comprimir(CODIGO, "comprimir", "code", 1.0, True, False)
    assert r["compressor"] == "code" and r["shown_tokens"] < r["raw_tokens"] * 0.8
    compile(r["output"], "pool.py", "exec")
    assert r["cache_key"] and Guarda().get(r["cache_key"]) == CODIGO


def test_deteccao_automatica_nao_usa_o_ast_sem_a_opcao(monkeypatch):
    monkeypatch.setattr(roteador, "_codigo_ast_ligado", lambda: False)
    r = roteador.comprimir(CODIGO, "", "auto", 1.0, False, False)
    assert r["content_type"] == "source_code" and r["compressor"] != "code"


def test_deteccao_automatica_usa_o_ast_com_a_opcao(monkeypatch):
    monkeypatch.setattr(roteador, "_codigo_ast_ligado", lambda: True)
    r = roteador.comprimir(CODIGO, "", "auto", 1.0, False, False)
    assert r["compressor"] == "code"


def test_a_opcao_vem_do_config_e_e_desligada_por_padrao(tmp_path, monkeypatch):
    from delegation_core import config
    assert config.Config().compress_code_ast is False
    assert roteador._codigo_ast_ligado() is False


def test_linguagem_sem_gramatica_cai_no_kompress_sem_quebrar(monkeypatch):
    pedidos = []
    monkeypatch.setattr(roteador, "_kompress", lambda texto, guarda: pedidos.append(1) or ("x", None))
    c = "#include <stdio.h>\n" + "".join(f"int f{i}(int a) {{\n  int b = a * {i};\n  return b + {i};\n}}\n" for i in range(80))
    r = roteador.comprimir(c, "", "code", 1.0, False, True)
    assert pedidos == [1] and r["compressor"] == "kompress"


def test_o_recuo_para_o_kompress_nunca_baixa_o_modelo(monkeypatch):
    """O modelo do Kompress so vem por `delegation-core kompress setup` (config.py). O recuo do
    compressor de codigo roda dentro de uma chamada do daemon e chamava o Kompress com o download
    ligado: linguagem sem gramatica, sem modelo em cache, e o daemon ia buscar 264 MB."""
    from delegation_core.compressao.headroom_py.transforms import kompress_compressor as kc

    pedidos = []

    class Falso:
        def compress(self, conteudo, **nomeados):
            pedidos.append(nomeados)
            return type("R", (), {"compressed": conteudo, "original_tokens": 3, "compressed_tokens": 3,
                                  "compression_ratio": 1.0})()

    monkeypatch.setattr(kc, "KompressCompressor", Falso)
    monkeypatch.setattr(kc, "is_kompress_available", lambda: True)
    r = cc.CodeAwareCompressor(cc.CodeCompressorConfig(enable_ccr=False))._fallback_compress("int a;", 3)
    assert pedidos == [{"allow_download": False}] and r.compressed == "int a;"


def test_linguagem_sem_gramatica_nao_pede_nada_ao_hugging_face(monkeypatch):
    """De ponta a ponta, com o Kompress de verdade e sem o modelo: toda leitura do Hub fica no cache."""
    hub = pytest.importorskip("huggingface_hub")
    pytest.importorskip("onnxruntime")
    from delegation_core.compressao.headroom_py import onnx_runtime

    fora_do_cache = []
    real = hub.hf_hub_download

    def vigiado(*args, **nomeados):
        if not nomeados.get("local_files_only"):
            fora_do_cache.append((args, nomeados))
            raise OSError("o teste nao baixa modelo")
        return real(*args, **nomeados)

    monkeypatch.setattr(hub, "hf_hub_download", vigiado)
    monkeypatch.setattr(onnx_runtime, "hf_hub_download_local_first", onnx_runtime.hf_hub_download_local_first)
    monkeypatch.setattr(roteador, "_kompress", lambda texto, guarda: None)
    c = "#include <stdio.h>\n" + "".join(f"int f{i}(int a) {{\n  int b = a * {i};\n  return b + {i};\n}}\n" for i in range(80))
    r = roteador.comprimir(c, "", "code", 1.0, False, True)
    assert fora_do_cache == [], fora_do_cache
    assert r["compressor"] != "code"


def test_saida_que_nao_passa_na_propria_validacao_e_descartada(monkeypatch):
    class Falso:
        def __init__(self, *a, **k):
            pass

        def compress(self, codigo, context=""):
            return type("R", (), {"syntax_valid": False, "compressed": "def MARCA_XYZ_INVALIDA(:", "cache_key": None})()

    monkeypatch.setattr(cc, "CodeAwareCompressor", Falso)
    r = roteador.comprimir(CODIGO, "", "code", 1.0, False, False)
    assert r["compressor"] != "code" and "MARCA_XYZ_INVALIDA" not in r["output"]


@pytest.mark.parametrize("lingua", ["python", "javascript", "typescript", "go", "rust", "java"])
def test_as_seis_gramaticas_carregam(lingua):
    assert cc._get_parser(lingua) is not None


def test_gramatica_ausente_da_o_erro_que_o_original_espera():
    with pytest.raises(ValueError):
        cc._get_parser("php")
