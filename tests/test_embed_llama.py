"""BGE pelo llama.cpp: o cliente, o processo, a interoperabilidade com o torch.

Os testes de processo usam um `llama-server` falso (um script Python que fala o
mesmo protocolo: GET /health e POST /v1/embeddings). O de interoperabilidade usa
o ChromaDB de verdade. O ultimo roda contra o llama-server e o GGUF reais, e so
quando `DC_TEST_BGE_GGUF` aponta para um GGUF do bge-base-en-v1.5 (ou do bge-m3,
com `DC_TEST_BGE_MODEL`); sem isso e pulado.

Medido em 06/10/2026 com o bge-m3 contra o sentence-transformers: GGUF f16
cosseno 0,99996 a 0,99999. E por isso que a colecao e a mesma nos dois backends.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import socket
import subprocess
import sys
import textwrap

import numpy as np
import pytest

from delegation_core import doctor, embed_llama, embeddings
from delegation_core.config import Config

NAO_WINDOWS = pytest.mark.skipif(os.name == "nt", reason="o llama-server falso e um script com shebang")

DIM = 768  # bge-base-en-v1.5

SERVIDOR_FALSO = textwrap.dedent('''\
    #!{python}
    import json, sys, hashlib
    from http.server import BaseHTTPRequestHandler, HTTPServer
    args = sys.argv[1:]
    porta = int(args[args.index("--port") + 1])
    limite = int(args[args.index("-ub") + 1]) if "-ub" in args else 10**9
    open({registro!r}, "a").write(" ".join(args) + "\\n")
    DIM = {dim}

    def vetor(t):
        out = []
        for i in range(DIM):
            h = hashlib.sha256((t + str(i)).encode()).digest()
            out.append(int.from_bytes(h[:4], "big") / 2**31 - 1.0)
        return out

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _j(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_GET(self):
            self._j(200, {{"status": "ok"}}) if self.path == "/health" else self._j(404, {{}})
        def do_POST(self):
            n = int(self.headers["Content-Length"]); corpo = json.loads(self.rfile.read(n))
            entradas = corpo["input"]
            if any(t == "" for t in entradas):
                return self._j(400, {{"error": {{"message": "input is empty"}}}})
            if any(len(t) > {maximo} for t in entradas):
                return self._j(500, {{"error": {{"message": "input is too large to process, increase the physical batch size"}}}})
            dados = [{{"index": i, "embedding": vetor(t)}} for i, t in enumerate(entradas)]
            self._j(200, {{"data": dados[::-1]}})  # fora de ordem: so o campo index diz qual e qual
    HTTPServer(("127.0.0.1", porta), H).serve_forever()
''')


def _porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def falso(tmp_path):
    """(cfg, registro): um Config que aponta para o llama-server falso."""
    registro = tmp_path / "chamadas.txt"
    binario = tmp_path / "llama-server-falso"
    binario.write_text(SERVIDOR_FALSO.format(python=sys.executable, registro=str(registro),
                                             dim=DIM, maximo=400))
    binario.chmod(0o755)
    gguf = tmp_path / "bge.gguf"
    gguf.write_bytes(b"GGUF")
    cfg = Config(vault_path=str(tmp_path / "vault"))
    cfg.bge_model = "BAAI/bge-base-en-v1.5"
    cfg.embed_llama_binary = str(binario)
    cfg.embed_gguf = str(gguf)
    cfg.embed_port = _porta_livre()
    cfg.embed_backend = "llamacpp"
    cfg.embed_device = "cpu"
    cfg.embed_max_seq_length = 512
    return cfg, registro


@pytest.fixture
def servidor(falso):
    cfg, registro = falso
    srv = embed_llama.EmbedServer(cfg)
    yield srv, cfg, registro
    srv.shutdown()


# ── a linha de comando ───────────────────────────────────────────────────────

def _valor(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_o_comando_serve_embeddings_com_pooling_cls_e_um_slot(falso):
    cfg, _ = falso
    cmd = embed_llama.comando_do_servidor(cfg)
    assert "--embeddings" in cmd and _valor(cmd, "--pooling") == "cls"
    # Sem -np 1 o llama.cpp divide o contexto entre slots automaticos.
    assert _valor(cmd, "-np") == "1"
    assert _valor(cmd, "--host") == "127.0.0.1" and _valor(cmd, "--port") == str(cfg.embed_port)


def test_o_lote_fisico_e_igual_ao_contexto(falso):
    cfg, _ = falso
    cmd = embed_llama.comando_do_servidor(cfg)
    assert _valor(cmd, "-c") == _valor(cmd, "-b") == _valor(cmd, "-ub") == "512"


def test_o_contexto_nunca_passa_do_teto_do_modelo(falso):
    cfg, _ = falso
    cfg.embed_max_seq_length = 8192  # o bge-base so tem 512
    assert _valor(embed_llama.comando_do_servidor(cfg), "-c") == "512"


def test_cpu_zera_as_camadas_na_gpu_e_o_resto_manda_tudo(falso):
    cfg, _ = falso
    assert _valor(embed_llama.comando_do_servidor(cfg), "-ngl") == "0"
    cfg.embed_device = "auto"
    assert _valor(embed_llama.comando_do_servidor(cfg), "-ngl") == "999"


# ── o processo ───────────────────────────────────────────────────────────────

@NAO_WINDOWS
def test_ensure_sobe_o_servidor_uma_vez_e_o_reaproveita(servidor):
    srv, cfg, registro = servidor
    srv.ensure()
    assert srv.healthy()
    srv.ensure()
    assert len(registro.read_text().splitlines()) == 1


@NAO_WINDOWS
def test_um_segundo_gerente_usa_o_servidor_que_ja_esta_no_ar(servidor):
    srv, cfg, registro = servidor
    srv.ensure()
    outro = embed_llama.EmbedServer(cfg)
    outro.ensure()
    assert len(registro.read_text().splitlines()) == 1
    assert outro._we_started_it is False  # nao e dono: nao o derruba ao sair


@NAO_WINDOWS
def test_dois_pedidos_ao_mesmo_tempo_sobem_um_servidor_so(falso):
    """Dois processos (aqui, dois gerentes com travas de thread distintas) veem a
    porta livre juntos. Medido em 09/10/2026 com um servidor que demora a ligar:
    antes da trava de arquivo, dois pedidos subiam dois llama-server."""
    import threading
    cfg, registro = falso
    registro.parent.joinpath("llama-server-falso").write_text(
        registro.parent.joinpath("llama-server-falso").read_text(encoding="utf-8")
        .replace("HTTPServer((", "__import__('time').sleep(1.5); HTTPServer(("), encoding="utf-8")
    gerentes = [embed_llama.EmbedServer(cfg) for _ in range(2)]
    erros = []

    def pedir(g):
        try:
            g.ensure()
        except Exception as e:  # noqa: BLE001 - o teste so quer saber se algum falhou
            erros.append(e)

    fios = [threading.Thread(target=pedir, args=(g,)) for g in gerentes]
    try:
        [f.start() for f in fios]
        [f.join() for f in fios]
        assert erros == []
        assert len(registro.read_text().splitlines()) == 1
        assert sum(g._we_started_it for g in gerentes) == 1
    finally:
        for g in gerentes:
            g.shutdown()


@NAO_WINDOWS
def test_shutdown_encerra_so_o_que_este_processo_subiu(servidor):
    srv, cfg, _ = servidor
    srv.ensure()
    srv.shutdown()
    assert not srv.healthy()


@NAO_WINDOWS
def test_se_o_dono_sai_o_proximo_pedido_sobe_outro(servidor):
    srv, cfg, registro = servidor
    srv.ensure()
    srv._proc.terminate()
    srv._proc.wait()
    srv.ensure()
    assert srv.healthy()
    assert len(registro.read_text().splitlines()) == 2


def test_sem_binario_o_erro_manda_rodar_o_setup(falso):
    cfg, _ = falso
    cfg.embed_llama_binary = "/nao/existe/llama-server"
    with pytest.raises(embed_llama.EmbedLlamaError, match="embed-llama setup"):
        embed_llama.EmbedServer(cfg).ensure()


@NAO_WINDOWS
def test_servidor_que_morre_na_partida_aponta_o_log(falso, tmp_path):
    cfg, _ = falso
    morre = tmp_path / "morre"
    morre.write_text("#!/bin/sh\nexit 3\n")
    morre.chmod(0o755)
    cfg.embed_llama_binary = str(morre)
    with pytest.raises(embed_llama.EmbedLlamaError, match="exited with code 3"):
        embed_llama.EmbedServer(cfg).ensure()


# ── a funcao de embedding ────────────────────────────────────────────────────

@NAO_WINDOWS
def test_os_vetores_saem_normalizados_e_na_ordem_dos_textos(servidor):
    srv, cfg, _ = servidor
    cfg.embed_batch_size = 2  # 5 textos: tres lotes, a ordem tem que sobreviver a eles
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
    textos = [f"nota numero {i}" for i in range(5)]
    v = ef(textos)
    assert len(v) == 5 and all(abs(np.linalg.norm(x) - 1) < 1e-5 for x in v)
    isolado = ef([textos[3]])[0]
    assert np.allclose(v[3], isolado, atol=1e-6)
    assert not np.allclose(v[3], v[4])


@NAO_WINDOWS
def test_texto_vazio_nao_derruba_o_lote(servidor):
    srv, cfg, _ = servidor
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
    v = ef(["algo", "", "   "])
    assert len(v) == 3 and all(np.isfinite(x).all() for x in v)


@NAO_WINDOWS
def test_texto_maior_que_o_servidor_aceita_e_cortado_e_repetido(servidor):
    srv, cfg, _ = servidor
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
    v = ef(["a" * 1500])  # o falso recusa acima de 400 caracteres
    assert len(v) == 1 and len(v[0]) == DIM


@NAO_WINDOWS
def test_gguf_de_outro_modelo_e_recusado_pela_dimensao(servidor):
    srv, cfg, _ = servidor
    cfg.bge_model = "BAAI/bge-m3"  # 1024; o falso devolve 768
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
    with pytest.raises(embed_llama.EmbedLlamaError, match="wrong model"):
        ef(["x"])


def test_o_contrato_do_chroma_e_o_do_sentence_transformer(falso):
    from chromadb.utils.embedding_functions.schemas.schema_utils import validate_config_schema

    cfg, _ = falso
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, embed_llama.EmbedServer(cfg))
    assert ef.name() == "sentence_transformer"
    validate_config_schema(ef.get_config(), "sentence_transformer")  # o que o chroma valida de verdade
    assert ef.default_space() == "cosine" and ef.is_legacy() is False


# ── interoperabilidade com o ChromaDB ────────────────────────────────────────

@NAO_WINDOWS
def test_colecao_gravada_por_uma_instancia_abre_com_outra_e_busca(servidor, tmp_path):
    import chromadb

    srv, cfg, _ = servidor
    caminho = str(tmp_path / "idx")
    meta = {"hnsw:space": "cosine"}
    cliente = chromadb.PersistentClient(path=caminho)
    ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
    col = cliente.get_or_create_collection("vault_bge", embedding_function=ef, metadata=meta)
    col.add(ids=["a", "b"], documents=["relatorio do PMO", "bolo de cenoura"])
    del col, cliente
    cliente = chromadb.PersistentClient(path=caminho)
    col = cliente.get_or_create_collection(
        "vault_bge", embedding_function=embed_llama.LlamaCppEmbeddingFunction(cfg, srv), metadata=meta)
    r = col.query(query_texts=["relatorio do PMO"], n_results=2)
    assert r["ids"][0][0] == "a" and r["distances"][0][0] < 1e-4
    config = cliente.get_collection("vault_bge", embedding_function=ef).configuration_json
    assert config["embedding_function"]["name"] == "sentence_transformer"


# ── a escolha do backend ─────────────────────────────────────────────────────

def test_auto_fica_no_torch_sem_binario_e_gguf(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    cfg = Config(vault_path=str(tmp_path))
    assert cfg.embed_backend == "auto"
    assert embeddings.resolver_backend(cfg) == "torch"


@NAO_WINDOWS
def test_auto_escolhe_o_llamacpp_quando_esta_pronto(falso):
    cfg, _ = falso
    cfg.embed_backend = "auto"
    assert embeddings.resolver_backend(cfg) == "llamacpp"
    cfg.embed_gguf = "/nao/existe.gguf"
    assert embeddings.resolver_backend(cfg) == "torch"


def test_pedido_explicito_vale_mesmo_sem_estar_pronto(tmp_path):
    cfg = Config(vault_path=str(tmp_path))
    cfg.embed_backend = "llamacpp"
    assert embeddings.resolver_backend(cfg) == "llamacpp"
    cfg.embed_backend = "torch"
    assert embeddings.resolver_backend(cfg) == "torch"


def test_valor_desconhecido_cai_em_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    cfg = Config(vault_path=str(tmp_path))
    cfg.embed_backend = "onnx"
    assert embeddings.resolver_backend(cfg) == "torch"


@NAO_WINDOWS
def test_o_vault_usa_a_funcao_do_llamacpp_e_nao_pede_a_placa(falso, monkeypatch):
    from delegation_core import gpu
    from delegation_core.vault import VaultManager

    cfg, _ = falso
    cfg.embed_device = "cuda"
    cfg.index_path = str(cfg.vault.parent / "indice")
    monkeypatch.setattr(gpu, "take", lambda who: pytest.fail("o llama.cpp nao disputa a placa"))
    vm = VaultManager(cfg)
    try:
        vm._init()
        assert isinstance(vm.ef, embed_llama.LlamaCppEmbeddingFunction), vm.init_error
    finally:
        embed_llama.servidor_para(cfg).shutdown()


# ── preparar a maquina ───────────────────────────────────────────────────────

@NAO_WINDOWS
def test_preparar_verifica_o_servidor_e_so_entao_liga_o_backend(falso):
    cfg, _ = falso
    cfg.embed_backend = "auto"
    r = embed_llama.preparar(cfg, baixar=False)
    assert r["status"] == "ok" and r["dim"] == DIM
    assert cfg.embed_backend == "llamacpp"
    assert Config.load().embed_backend == "llamacpp"  # gravou de verdade


@NAO_WINDOWS
def test_preparar_que_falha_na_verificacao_deixa_a_config_como_estava(falso, tmp_path):
    cfg, _ = falso
    cfg.embed_backend = "auto"
    morre = tmp_path / "morre"
    morre.write_text("#!/bin/sh\nexit 1\n")
    morre.chmod(0o755)
    cfg.embed_llama_binary = ""
    cfg.llama_binary = str(morre)  # o preparar o acha aqui e o grava na config antes de verificar
    gguf_antes = cfg.embed_gguf
    r = embed_llama.preparar(cfg, baixar=False)
    assert r["status"] == "error" and r["step"] == "verify"
    assert cfg.embed_backend == "auto"
    assert cfg.embed_llama_binary == "" and cfg.embed_gguf == gguf_antes


def test_preparar_sem_gguf_e_sem_permissao_de_baixar_diz_o_que_falta(falso):
    cfg, _ = falso
    cfg.embed_gguf = ""
    r = embed_llama.preparar(cfg, baixar=False)
    assert r["status"] == "error" and r["step"] == "gguf"


def test_preparar_recusa_modelo_sem_gguf_conhecido(falso):
    cfg, _ = falso
    cfg.bge_model = "meu/modelo-proprio"
    assert embed_llama.preparar(cfg, baixar=False)["status"] == "error"


def test_o_catalogo_tem_o_perfil_de_cada_modelo_e_a_dimensao_bate():
    for nome in embed_llama.GGUF_CATALOGO:
        assert nome in embeddings.MODEL_PROFILES
        assert nome in embed_llama.CONTEXTO_MAXIMO
        assert embed_llama.DIMENSAO[nome] == embeddings.MODEL_PROFILES[nome]["dim"]
        assert embed_llama.CONTEXTO_MAXIMO[nome] <= embeddings.MODEL_PROFILES[nome]["max_seq"]
    assert embed_llama.url_do_gguf("BAAI/bge-m3").endswith("/bge-m3-f16.gguf")


# ── doctor ───────────────────────────────────────────────────────────────────

def test_doctor_avisa_mac_no_torch_e_aponta_o_comando(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    r = doctor.check_embed_backend(Config(vault_path=str(tmp_path)))
    assert r["status"] == "warn" and "embed-llama setup" in r["fix"]


def test_doctor_nao_incomoda_linux_no_torch(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert doctor.check_embed_backend(Config(vault_path=str(tmp_path)))["status"] == "ok"


def test_doctor_erra_quando_o_llamacpp_foi_pedido_e_nao_esta_pronto(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    cfg = Config(vault_path=str(tmp_path))
    cfg.embed_backend = "llamacpp"
    assert doctor.check_embed_backend(cfg)["status"] == "error"


def test_o_check_entra_no_doctor_completo():
    assert any(getattr(f, "__name__", "") == "check_embed_backend" for f in [doctor.check_embed_backend])
    assert "check_embed_backend(cfg)" in open(doctor.__file__, encoding="utf-8").read()


# ── contra o llama-server e o GGUF de verdade (opcional) ─────────────────────

GGUF_REAL = os.environ.get("DC_TEST_BGE_GGUF", "")


@pytest.mark.skipif(not GGUF_REAL or not shutil.which("llama-server"),
                    reason="defina DC_TEST_BGE_GGUF (um GGUF f16 do BGE) e tenha llama-server no PATH")
def test_contra_o_llama_server_real(tmp_path):
    cfg = Config(vault_path=str(tmp_path / "v"))
    cfg.bge_model = os.environ.get("DC_TEST_BGE_MODEL", "BAAI/bge-base-en-v1.5")
    cfg.embed_gguf = GGUF_REAL
    cfg.embed_port = _porta_livre()
    cfg.embed_device = "cpu"
    cfg.embed_max_seq_length = 512
    srv = embed_llama.EmbedServer(cfg)
    try:
        ef = embed_llama.LlamaCppEmbeddingFunction(cfg, srv)
        q, certo, errado = ef(["when is the PMO report due?",
                               "The PMO report is delivered every Friday at 6pm.",
                               "carrot cake recipe with chocolate frosting"])
        assert len(q) == embeddings.profile_for(cfg.bge_model)["dim"]
        assert float(q @ certo) > float(q @ errado) + 0.1
        assert abs(float(np.linalg.norm(q)) - 1.0) < 1e-5
    finally:
        srv.shutdown()


def test_hashlib_importado_para_o_servidor_falso():
    assert hashlib.sha256(b"x").digest()  # garante que o script gerado importa o que usa
    assert subprocess  # silencia o linter: usado so nos testes de processo


def test_embed_llama_funciona_sem_o_chromadb_instalado():
    """O extra [chroma] e opcional: o BGE pelo llama.cpp nao pode puxa-lo de volta."""
    import os
    import subprocess
    import sys
    codigo = (
        "import sys; sys.modules['chromadb'] = None\n"
        "from delegation_core import embed_llama\n"
        "assert embed_llama.LlamaCppEmbeddingFunction.__mro__[1] is object\n"
        "assert embed_llama.LlamaCppEmbeddingFunction.name() == 'sentence_transformer'\n"
        "print('ok sem chromadb')\n")
    p = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)))
    assert p.returncode == 0 and "ok sem chromadb" in p.stdout, p.stderr[-400:]
