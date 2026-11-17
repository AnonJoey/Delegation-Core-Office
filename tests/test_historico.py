"""Pacote historico: versao por conteudo, varredura incremental, diff, renomeacao e poda."""

from __future__ import annotations

import ast
import os
import time
from pathlib import Path

import pytest

from delegation_core.historico import Historico

PACOTE = Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "historico"


@pytest.fixture
def h(tmp_path):
    x = Historico(tmp_path / "hist")
    yield x
    x.fechar()


def test_registrar_e_ler_de_volta(h):
    r = h.registrar("a.md", "ola\n", origem="teste")
    assert r["origem"] == "teste" and h.texto("a.md") == "ola\n"


def test_versao_igual_a_ultima_nao_e_registrada(h):
    assert h.registrar("a.md", "x") is not None
    assert h.registrar("a.md", "x") is None
    assert len(h.versoes("a.md")) == 1


def test_voltar_a_um_texto_antigo_e_versao_nova_mas_blob_repetido(h):
    h.registrar("a.md", "um")
    h.registrar("a.md", "dois")
    h.registrar("a.md", "um")
    assert [h.texto("a.md", n) for n in (1, 2, 3)] == ["um", "dois", "um"]
    blobs = [f for f in (h.raiz / "objetos").rglob("*") if f.is_file()]
    assert len(blobs) == 2


def test_blob_e_comprimido(h):
    h.registrar("a.md", "abc " * 5000)
    blob = next(f for f in (h.raiz / "objetos").rglob("*") if f.is_file())
    assert blob.stat().st_size < 1000


def test_versoes_da_mais_nova_para_a_mais_antiga(h):
    for t in ("v1", "v2", "v3"):
        h.registrar("a.md", t)
    assert [v["n"] for v in h.versoes("a.md")] == [1, 2, 3]
    assert h.texto("a.md", 1) == "v3" and h.texto("a.md", 3) == "v1"
    assert h.texto("a.md", 4) is None


def test_diff_entre_versoes(h):
    h.registrar("a.md", "linha 1\nlinha 2\n")
    h.registrar("a.md", "linha 1\nlinha dois\nlinha 3\n")
    d = h.diff("a.md")
    assert d["ok"] and d["linhas_mais"] == 2 and d["linhas_menos"] == 1
    assert "-linha 2" in d["diff"] and "+linha dois" in d["diff"]


def test_diff_de_versao_inexistente(h):
    h.registrar("a.md", "so uma")
    d = h.diff("a.md")
    assert d == {"ok": False, "motivo": "versao inexistente", "versoes": 1}


def _vault(tmp_path, arquivos):
    raiz = tmp_path / "vault"
    for rel, texto in arquivos.items():
        (raiz / rel).parent.mkdir(parents=True, exist_ok=True)
        (raiz / rel).write_text(texto)
    return raiz


def test_varrer_registra_tudo_na_primeira_vez_e_nada_na_segunda(h, tmp_path):
    v = _vault(tmp_path, {"A/a.md": "a", "B/b.md": "b"})
    assert h.varrer(v, ["A/a.md", "B/b.md"]) == {"lidas": 2, "novas": 2, "alteradas": 0}
    assert h.varrer(v, ["A/a.md", "B/b.md"]) == {"lidas": 0, "novas": 0, "alteradas": 0}


def test_varrer_so_le_o_que_mudou(h, tmp_path):
    v = _vault(tmp_path, {"a.md": "a", "b.md": "b"})
    h.varrer(v, ["a.md", "b.md"])
    (v / "b.md").write_text("b mudou")
    r = h.varrer(v, ["a.md", "b.md"])
    assert r == {"lidas": 1, "novas": 0, "alteradas": 1}
    assert h.texto("b.md", 2) == "b" and h.texto("b.md") == "b mudou"


def test_varrer_toque_sem_mudanca_le_mas_nao_versiona(h, tmp_path):
    v = _vault(tmp_path, {"a.md": "a"})
    h.varrer(v, ["a.md"])
    novo = time.time() + 5
    os.utime(v / "a.md", (novo, novo))
    assert h.varrer(v, ["a.md"]) == {"lidas": 1, "novas": 0, "alteradas": 0}
    assert len(h.versoes("a.md")) == 1


def test_varrer_ignora_arquivo_que_sumiu_e_mantem_o_historico(h, tmp_path):
    v = _vault(tmp_path, {"a.md": "a"})
    h.varrer(v, ["a.md"])
    (v / "a.md").unlink()
    assert h.varrer(v, ["a.md"])["lidas"] == 0
    assert h.texto("a.md") == "a"


def test_renomear_leva_o_historico_junto(h, tmp_path):
    h.registrar("velho.md", "v1")
    h.registrar("velho.md", "v2")
    assert h.renomear("velho.md", "novo.md") == 2
    assert h.versoes("velho.md") == [] and h.texto("novo.md", 2) == "v1"


def test_renomear_esquece_a_marca_do_caminho_velho(h, tmp_path):
    """Se o caminho velho voltar a existir, e outra nota: tem que ser lida."""
    v = _vault(tmp_path, {"x.md": "primeira"})
    h.varrer(v, ["x.md"])
    h.renomear("x.md", "y.md")
    (v / "x.md").write_text("outra nota")
    os.utime(v / "x.md", ns=(os.stat(v / "x.md").st_mtime_ns,) * 2)
    assert h.varrer(v, ["x.md"])["novas"] == 1


def test_mudancas_desde(h):
    h.registrar("a.md", "1")
    corte = time.time()
    time.sleep(0.01)
    h.registrar("b.md", "1", origem="relink")
    h.registrar("b.md", "2", origem="relink")
    r = h.mudancas_desde(corte)
    assert [(x["caminho"], x["versoes"], x["origens"]) for x in r] == [("b.md", 2, ["relink"])]


def test_podar_mantem_as_mais_novas_e_apaga_blob_orfao(h):
    for i in range(5):
        h.registrar("a.md", f"versao {i}")
    r = h.podar(manter_por_nota=2)
    assert r == {"versoes_apagadas": 3, "blobs_apagados": 3}
    assert [h.texto("a.md", n) for n in (1, 2)] == ["versao 4", "versao 3"]


def test_podar_nao_apaga_blob_compartilhado(h):
    h.registrar("a.md", "comum")
    h.registrar("a.md", "a2")
    h.registrar("b.md", "comum")
    h.podar(manter_por_nota=1)
    assert h.texto("b.md") == "comum"


def test_estatisticas(h):
    h.registrar("a.md", "x" * 1000)
    h.registrar("b.md", "x" * 1000)
    e = h.estatisticas()
    assert e["versoes"] == 2 and e["notas"] == 2 and e["bytes_versionados"] == 2000
    assert 0 < e["bytes_em_disco"] < 200


def test_caminhos_com_prefixo(h):
    for c in ("Fixes/a.md", "Fixes/b.md", "Decisions/c.md"):
        h.registrar(c, c)
    assert h.caminhos("Fixes/") == ["Fixes/a.md", "Fixes/b.md"]


def test_pacote_nao_importa_o_nucleo():
    proibidos = []
    for arq in PACOTE.glob("*.py"):
        for no in ast.walk(ast.parse(arq.read_text())):
            if isinstance(no, ast.ImportFrom) and (no.level >= 2 or (no.module or "").startswith("delegation_core")):
                proibidos.append(f"{arq.name}: {no.module}")
    assert proibidos == []


def test_versao_zero_ou_negativa_nao_existe(h):
    """Sem a guarda, vs[0 - 1] do Python devolveria a versao MAIS ANTIGA para n=0."""
    h.registrar("a.md", "antiga")
    h.registrar("a.md", "nova")
    assert h.texto("a.md", 0) is None and h.texto("a.md", -1) is None


def test_diff_de_texto_sem_quebra_final_nao_cola_linhas(h):
    """Visto no painel: '-...e acabou+texto novo' numa linha so."""
    h.registrar("a.md", "linha velha")
    h.registrar("a.md", "linha nova")
    d = h.diff("a.md")["diff"]
    assert "-linha velha\n" in d and "+linha nova\n" in d
