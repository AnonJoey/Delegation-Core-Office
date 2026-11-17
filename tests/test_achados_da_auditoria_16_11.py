"""Achados da auditoria de 16/11/2026, cada um com o que foi medido.

A auditoria rodou o `master` num clone limpo, numa instalacao do zero e num
daemon isolado com vault sintetico (e depois com 206 notas reais num servidor
Ubuntu). O que segue sao os defeitos que apareceram em execucao e nao tinham
teste. Os de Windows estao no fim: um deles roda de verdade no runner Windows
do CI, porque flag de `CreateProcess` conferido so por valor ja enganou uma vez.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pytest

from delegation_core import notewriter
from delegation_core import vault as vault_mod
from delegation_core.auth import LocalTokenAuth
from delegation_core.config import Config
from delegation_core.engine import DelegationEngine
from delegation_core.hooks import entrada, session_export, session_start_brief
from delegation_core.vault import VaultManager

DIM = 64


class _Embedder:
    def __call__(self, input):
        out = []
        for texto in input:
            v = np.zeros(DIM, dtype=np.float32)
            for w in re.findall(r"\w+", texto.lower()):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out

    def embed_documents(self, input):
        return self(input)

    def embed_query(self, input):
        return self([input])[0] if isinstance(input, str) else self(list(input))

    def name(self):
        return "falso"


@pytest.fixture
def vm(tmp_path, monkeypatch):
    raiz = tmp_path / "v"
    (raiz / "Decisions").mkdir(parents=True)
    cfg = Config(vault_path=str(raiz), vault_folders=["Decisions"],
                 index_backend="sqlite", embed_device="cpu")
    monkeypatch.setattr(vault_mod, "make_bge_embedding_function", lambda *a, **k: _Embedder())
    v = VaultManager(cfg)
    v.reindex_vault(force=True)
    return v


def _linhas(vm, rel):
    achado = vm.collection.get(where={"path": rel}, include=["documents"])
    return dict(zip(achado["ids"], achado["documents"]))


# -- 1. a nota nao some do indice quando a regravacao cai no meio ---------------

def test_regravacao_que_falha_deixa_a_nota_no_indice(vm, monkeypatch):
    """Medido com `kill -9` no meio de uma carga: uma nota gravada e confirmada
    ficou sem linha nenhuma, porque `index_note` apagava tudo antes de regravar e
    a queda caiu entre os dois passos. Aqui a queda e um upsert que levanta."""
    rel = "Decisions/nota.md"
    meta = {"title": "nota", "path": rel, "folder": "Decisions"}
    assert vm.index_note("a primeira versao fala de fermento", meta)
    assert _linhas(vm, rel)

    def cai(*a, **k):
        raise RuntimeError("queda no meio da regravacao")

    monkeypatch.setattr(type(vm.collection), "upsert", cai)
    assert vm.index_note("a segunda versao fala de outra coisa", meta) is False
    monkeypatch.undo()

    sobrou = _linhas(vm, rel)
    assert sobrou, "a regravacao que falhou tirou a nota do indice"
    assert "fermento" in " ".join(sobrou.values())


def test_nota_que_encolhe_nao_deixa_trecho_antigo(vm):
    """A outra metade do contrato: gravar primeiro nao pode trazer de volta o
    defeito que o delete resolvia (trechos da revisao antiga respondendo busca)."""
    rel = "Decisions/longa.md"
    meta = {"title": "longa", "path": rel, "folder": "Decisions"}
    longa = "\n\n".join(f"## parte {i}\n\n" + (f"paragrafo {i} " * 400) for i in range(8))
    assert vm.index_note(longa, meta)
    antes = _linhas(vm, rel)
    assert len(antes) > 1
    assert vm.index_note("agora e curta", meta)
    depois = _linhas(vm, rel)
    assert list(depois) == [f"{rel}::chunk_0"]
    assert "paragrafo" not in " ".join(depois.values())


# -- 2. token que nao e ASCII e recusado, nao derruba o pedido ------------------

@pytest.mark.parametrize("apresentado", ["café", "日本", "s3cret-tokené"])
def test_token_nao_ascii_e_recusado_sem_excecao(apresentado):
    """Medido: `Authorization: Bearer cafe` com acento devolvia 500 na porta MCP,
    porque `hmac.compare_digest` levanta TypeError para str nao ASCII."""
    assert asyncio.run(LocalTokenAuth("s3cret-token").verify_token(apresentado)) is None


def test_token_nao_ascii_configurado_ainda_autentica():
    token = "segredo-com-ç"
    assert asyncio.run(LocalTokenAuth(token).verify_token(token)) is not None


@pytest.mark.parametrize("apresentado", ["café", "日本", "token-do-cliente-é"])
def test_token_nao_ascii_contra_tokens_por_cliente_e_recusado_sem_excecao(apresentado):
    """O porte do TEST (17/11) trouxe tokens por cliente; a comparacao deles tambem e em bytes."""
    nomeados = {"codex": {"token": "token-do-cliente", "scope": "read"}}
    auth = LocalTokenAuth("M" * 30, tokens_nomeados=lambda: nomeados)
    assert asyncio.run(auth.verify_token(apresentado)) is None


def test_token_por_cliente_nao_ascii_configurado_ainda_autentica():
    nomeados = {"codex": {"token": "cliente-com-ç", "scope": "read"}}
    auth = LocalTokenAuth("M" * 30, tokens_nomeados=lambda: nomeados)
    r = asyncio.run(auth.verify_token("cliente-com-ç"))
    assert r is not None and r.client_id == "client:codex"


# -- 3. (rota da nota no dashboard com NUL: em test_dashboard_api_vault_note.py)


# -- 4. o arquivo da nota nao leva NUL ------------------------------------------

def test_write_note_nao_grava_nul_no_arquivo(vm):
    r = notewriter.create_note(vm, "Decisions", "com nul", "antes\x00depois")
    assert r.get("status") == "ok", r
    arquivo = next((vm.cfg.vault / "Decisions").glob("*com nul.md"))
    assert b"\x00" not in arquivo.read_bytes()
    assert "antes depois" in arquivo.read_text(encoding="utf-8")


def test_update_e_save_tambem_nao_gravam_nul(vm):
    notewriter.create_note(vm, "Decisions", "alvo", "corpo")
    arquivo = next((vm.cfg.vault / "Decisions").glob("*alvo.md"))
    assert vm.update_note(arquivo.stem, "acrescimo\x00com nul").get("status") == "ok"
    assert b"\x00" not in arquivo.read_bytes()
    rel = arquivo.relative_to(vm.cfg.vault).as_posix()
    notewriter.save_note(vm, rel, "texto\x00inteiro")
    assert b"\x00" not in arquivo.read_bytes()


# -- 5. modo local: modelo dormindo nao e servidor degradado --------------------

def test_pode_subir_separa_modelo_dormindo_de_modelo_ausente(tmp_path):
    """Medido: um daemon recem-iniciado em modo local dizia "degraded" ate o
    primeiro uso do modelo, que sobe sob demanda."""
    binario = tmp_path / "llama-server"
    modelo = tmp_path / "m.gguf"
    cfg = Config(vault_path=str(tmp_path), engine_mode="local",
                 llama_binary=str(binario), llama_model=str(modelo))
    motor = DelegationEngine(cfg)
    assert motor.pode_subir() is False          # nada existe
    binario.write_text("x")
    assert motor.pode_subir() is False          # falta o modelo
    modelo.write_text("x")
    assert motor.pode_subir() is True
    cfg.llama_binary = ""
    assert motor.pode_subir() is False


# -- 6. parada limpa nao deixa o indice dividido entre o .db e o WAL ------------

def test_checkpoint_zera_o_wal(vm):
    """Medido depois de um SIGTERM: `indice.db` de 7,7 MB com `-wal` de 4,7 MB."""
    for i in range(30):
        vm.index_note(f"nota numero {i} " * 50, {"title": f"n{i}", "path": f"Decisions/n{i}.md",
                                                  "folder": "Decisions"})
    cliente = vm._client
    wal = Path(str(cliente.arquivo) + "-wal")
    assert wal.exists() and wal.stat().st_size > 0
    cliente.checkpoint()
    assert not wal.exists() or wal.stat().st_size == 0
    so_o_db = sqlite3.connect(f"file:{cliente.arquivo}?mode=ro&immutable=1", uri=True)
    try:
        assert so_o_db.execute("SELECT count(*) FROM chunks").fetchone()[0] >= 30
    finally:
        so_o_db.close()


# -- 7. a checagem de atualizacao do fastmcp e desligada pela opcao que existe --

def test_a_opcao_do_fastmcp_que_o_cli_desliga_existe():
    """`FASTMCP_DISABLE_UPDATE_CHECK` nao e lida pelo fastmcp 3.x; o daemon
    consultava o PyPI na partida. Se o fastmcp renomear a opcao de novo, este
    teste avisa antes de a consulta voltar em silencio."""
    import fastmcp

    assert hasattr(fastmcp.settings, "check_for_updates")
    fonte = (Path(__file__).resolve().parents[1] / "src" / "delegation_core" / "cli.py").read_text(
        encoding="utf-8")
    assert 'setdefault("FASTMCP_CHECK_FOR_UPDATES", "off")' in fonte
    assert 'setdefault("FASTMCP_DISABLE_UPDATE_CHECK"' not in fonte


# -- 8. Windows: os processos que os hooks lancam nao abrem janela --------------

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


def test_nenhum_hook_combina_detached_com_no_window(monkeypatch):
    """`CREATE_NO_WINDOW` e ignorado quando vem com `DETACHED_PROCESS`. Os tres
    hooks lancam um LANCADOR (python.exe do venv ou o .exe do console-script), e
    o interpretador que o lancador cria precisa herdar um console oculto."""
    monkeypatch.setattr(entrada, "_is_windows", lambda: True)
    monkeypatch.setattr(session_export.platform, "system", lambda: "Windows")
    monkeypatch.setattr(session_start_brief.platform, "system", lambda: "Windows")
    for modulo in (entrada, session_export, session_start_brief):
        flags = modulo._detached_popen_kwargs().get("creationflags", 0)
        assert flags & CREATE_NO_WINDOW, modulo.__name__
        assert not flags & DETACHED_PROCESS, modulo.__name__
        assert flags & CREATE_NEW_PROCESS_GROUP, modulo.__name__


_FILHO = (
    "import ctypes,json,sys;"
    "k=ctypes.windll.kernel32;u=ctypes.windll.user32;"
    "h=k.GetConsoleWindow();"
    "json.dump({'console':bool(h),'visivel':bool(h and u.IsWindowVisible(h))},open(sys.argv[1],'w'))"
)


def _janela_do_neto(python_do_venv: Path, flags: int, saida: Path) -> dict:
    subprocess.Popen([str(python_do_venv), "-c", _FILHO, str(saida)], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    limite = time.time() + 30
    while time.time() < limite:
        if saida.exists() and saida.stat().st_size:
            return json.loads(saida.read_text(encoding="utf-8"))
        time.sleep(0.1)
    raise AssertionError("o processo lancado nao respondeu em 30 s")


@pytest.mark.skipif(os.name != "nt", reason="mede o console de verdade, so existe no Windows")
def test_no_windows_o_lancador_do_venv_nao_abre_janela_com_os_flags_dos_hooks(tmp_path, monkeypatch):
    """Roda no runner Windows do CI. O `python.exe` de um venv e um lancador: ele
    cria o interpretador de base como filho. O teste lanca esse lancador com os
    flags que os hooks usam e pergunta ao proprio interpretador se ele tem uma
    janela de console visivel."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True, timeout=300)
    python_do_venv = venv / "Scripts" / "python.exe"

    monkeypatch.setattr(entrada, "_is_windows", lambda: True)
    flags = entrada._detached_popen_kwargs()["creationflags"]
    novo = _janela_do_neto(python_do_venv, flags, tmp_path / "novo.json")
    assert not novo["visivel"], f"os flags dos hooks abriram janela visivel: {novo}"

    # A combinacao antiga, so para ficar registrada no log do CI: nao decide o teste.
    antigo = _janela_do_neto(python_do_venv,
                             DETACHED_PROCESS | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP,
                             tmp_path / "antigo.json")
    warnings.warn(f"medicao no Windows: flags novos {novo}; DETACHED|NO_WINDOW (antigos) {antigo}",
                  stacklevel=1)


# -- 9. o llama-server baixado e conferido contra o SHA-256 da release ----------

@pytest.fixture
def servidor_de_arquivo():
    import http.server
    import threading as _th

    corpo = b"binario do llama-server " * 1000

    class _H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(corpo)))
            self.end_headers()
            self.wfile.write(corpo)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _H)
    _th.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/llama.zip", corpo
    srv.shutdown()
    srv.server_close()


def test_download_com_hash_diferente_do_declarado_e_recusado(servidor_de_arquivo, tmp_path, monkeypatch):
    from delegation_core import downloader

    url, corpo = servidor_de_arquivo
    destino = tmp_path / "llama.zip"
    monkeypatch.setitem(downloader._DIGESTS, url, "0" * 64)
    assert downloader._download_file(url, destino, "teste") is False
    assert not destino.exists()

    monkeypatch.setitem(downloader._DIGESTS, url, hashlib.sha256(corpo).hexdigest())
    assert downloader._download_file(url, destino, "teste") is True
    assert destino.read_bytes() == corpo


def test_a_escolha_do_ativo_guarda_o_digest_que_a_api_declara(monkeypatch):
    from delegation_core import downloader

    class _R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"assets": [
                {"name": "llama-b1-bin-ubuntu-x64.tar.gz", "browser_download_url": "https://exemplo/a.tar.gz",
                 "digest": "sha256:" + "AB" * 32},
                {"name": "llama-b1-bin-macos-arm64.tar.gz", "browser_download_url": "https://exemplo/m.tar.gz"},
            ]}

    monkeypatch.setattr(downloader.requests, "get", lambda *a, **k: _R())
    url, _ = downloader._get_release_asset("Linux", "x86_64")
    assert downloader._DIGESTS[url] == "ab" * 32
    assert "https://exemplo/m.tar.gz" not in downloader._DIGESTS   # sem digest: sem conferencia


# -- 10. o repositorio publico so distribui skill de licenca aberta -------------

def test_nenhuma_skill_empacotada_proibe_a_distribuicao():
    """`skills/docx`, `pdf`, `pptx` e `xlsx` traziam a licenca proprietaria da
    Anthropic ("users may not ... Distribute, sublicense, or transfer these
    materials") num repositorio publico cujo instalador as copia para
    `~/.claude/skills`. Sairam; este teste impede que voltem por uma copia em lote."""
    raiz = Path(__file__).resolve().parents[1] / "skills"
    proibidas = []
    for licenca in list(raiz.glob("*/LICENSE*")) + list(raiz.glob("*/license*")):
        texto = licenca.read_text(encoding="utf-8", errors="replace")
        if "All rights reserved" in texto and "Distribute" in texto:
            proibidas.append(licenca.parent.name)
    assert not proibidas, f"skills com licenca que proibe distribuir: {sorted(set(proibidas))}"


# -- 11. o guia completo cita toda ferramenta que o servidor registra -----------

def test_o_agent_guide_cita_todas_as_ferramentas_do_servidor():
    """Medido: 20 das 55 ferramentas nao apareciam no AGENT_GUIDE.md."""
    import ast

    raiz = Path(__file__).resolve().parents[1]
    arvore = ast.parse((raiz / "src" / "delegation_core" / "server.py").read_text(encoding="utf-8"))
    ferramentas = {
        n.name for n in ast.walk(arvore)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(re.search(r"\btool\b", ast.unparse(d)) for d in n.decorator_list)
    }
    assert len(ferramentas) >= 50
    guia = (raiz / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    faltam = sorted(f for f in ferramentas if not re.search(rf"\b{re.escape(f)}\b", guia))
    assert not faltam, f"ferramentas fora do AGENT_GUIDE.md: {faltam}"
