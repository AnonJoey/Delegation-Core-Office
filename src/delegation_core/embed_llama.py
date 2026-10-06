"""BGE servido pelo llama.cpp, em vez de sentence-transformers (torch).

Existe para o Mac Apple Silicon: la o modelo de geracao roda no MLX
(`mlx_lm.server`) e o BGE precisa rodar ao lado, sem torch/MPS, que e o caminho
que ja derrubou o daemon por alocacao de buffer na memoria unificada (DC-47).
O `llama-server` com `--embeddings` serve o BGE em GGUF pela porta propria
`embed_port`, e este modulo e o cliente dele.

## Os vetores sao os mesmos

Medido em 06/10/2026 com o bge-m3 contra o sentence-transformers (CPU), em seis
textos (portugues, ingles, codigo, texto de 5 mil caracteres, uma letra):

    GGUF f16   cosseno 0,99996 a 0,99999
    GGUF q8_0  cosseno 0,99862 a 0,99949

Por isso o padrao e o f16 e a colecao do ChromaDB e a mesma do backend torch: um
indice feito pelo torch continua valido, e o inverso tambem. Nao ha reindexacao
ao trocar de backend.

## O ChromaDB e a configuracao gravada

O ChromaDB grava o nome e a configuracao da funcao de embedding na colecao e
recusa abrir com uma funcao de nome diferente. A funcao daqui se declara
`sentence_transformer` e devolve a mesma configuracao que a do torch: sem isso,
um Mac com indice feito pelo torch nao abriria a colecao depois da troca.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import numpy as np
import requests
from chromadb.api.types import EmbeddingFunction

logger = logging.getLogger("embed_llama")

#: Modelo de busca -> (repositorio GGUF no Hugging Face, arquivo, tamanho em bytes).
#: f16: ver "Os vetores sao os mesmos". Tamanhos medidos nos arquivos baixados.
GGUF_CATALOGO: dict[str, tuple[str, str, int]] = {
    "BAAI/bge-base-en-v1.5": ("CompendiumLabs/bge-base-en-v1.5-gguf",
                              "bge-base-en-v1.5-f16.gguf", 218_789_984),
    "BAAI/bge-m3": ("CompendiumLabs/bge-m3-gguf", "bge-m3-f16.gguf", 1_157_671_200),
}

#: Dimensao do vetor de cada modelo. Fica aqui, e nao em `embeddings.MODEL_PROFILES`,
#: porque este modulo nao pode importar `embeddings` (que o importa); um teste
#: prende que os dois concordam.
DIMENSAO = {"BAAI/bge-base-en-v1.5": 768, "BAAI/bge-m3": 1024}

#: Teto de contexto do servidor. O bge-m3 anuncia 8192; o do bge-base e 512.
CONTEXTO_MAXIMO = {"BAAI/bge-base-en-v1.5": 512, "BAAI/bge-m3": 8192}

ESPERA_DE_PARTIDA_S = 180
#: Quantas vezes um texto grande demais e cortado ao meio antes de desistir.
CORTES_MAXIMOS = 4


class EmbedLlamaError(RuntimeError):
    pass


def url_do_gguf(model_name: str) -> str | None:
    item = GGUF_CATALOGO.get(model_name)
    if item is None:
        return None
    repo, arquivo, _ = item
    return f"https://huggingface.co/{repo}/resolve/main/{arquivo}"


def gguf_padrao(cfg) -> Path | None:
    """Onde o GGUF do modelo configurado fica, se o catalogo o conhece."""
    item = GGUF_CATALOGO.get(cfg.bge_model)
    return cfg.models_dir / item[1] if item else None


def achar_llama_server(cfg) -> str:
    """O binario do llama.cpp que serve embeddings: o configurado, senao o do PATH."""
    explicito = (getattr(cfg, "embed_llama_binary", "") or "").strip()
    if explicito:
        return str(Path(explicito).expanduser())
    return shutil.which("llama-server") or ""


def configurado(cfg) -> bool:
    """Ha binario e GGUF de verdade, prontos para subir."""
    binario = achar_llama_server(cfg)
    gguf = (getattr(cfg, "embed_gguf", "") or "").strip()
    return bool(binario and Path(binario).exists() and gguf and Path(gguf).expanduser().is_file())


def comando_do_servidor(cfg) -> list[str]:
    """A linha de comando do llama-server de embeddings.

    `-np 1` e obrigatorio: sem ele o llama.cpp divide o contexto entre os slots
    automaticos e cada pedido ve uma fracao de `-c`. `-b` e `-ub` iguais ao
    contexto, porque um modelo de embedding nao-causal precisa da sequencia
    inteira num unico lote fisico. `--pooling cls` e o pooling do BGE, e fica
    explicito para nao depender do que o GGUF declara.
    """
    contexto = int(getattr(cfg, "embed_max_seq_length", 0) or 0) or CONTEXTO_MAXIMO.get(cfg.bge_model, 2048)
    contexto = min(contexto, CONTEXTO_MAXIMO.get(cfg.bge_model, contexto))
    cmd = [achar_llama_server(cfg),
           "--model", str(Path(cfg.embed_gguf).expanduser()),
           "--embeddings", "--pooling", "cls",
           "--host", "127.0.0.1", "--port", str(cfg.embed_port),
           "-c", str(contexto), "-b", str(contexto), "-ub", str(contexto),
           "-np", "1"]
    if (getattr(cfg, "embed_device", "auto") or "auto").strip().lower() == "cpu":
        cmd += ["-ngl", "0"]
    else:
        cmd += ["-ngl", "999"]
    return cmd


def _detached() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


class EmbedServer:
    """O processo `llama-server --embeddings`, compartilhado por quem o pedir.

    Varios processos do delegation-core abrem o indice (o daemon, o `reindex` do
    hook de sessao, a CLI). O primeiro sobe o servidor; os outros acham a porta
    saudavel e usam o mesmo. Quem subiu o encerra ao sair, e quem usou o de
    outro confere a saude a cada chamada: se o dono saiu, sobe de novo.
    """

    def __init__(self, cfg):
        self.cfg = cfg
        self._proc: subprocess.Popen | None = None
        self._we_started_it = False
        self._lock = threading.Lock()
        self._log_fh = None
        atexit.register(self.shutdown)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.cfg.embed_port}"

    def healthy(self) -> bool:
        try:
            return requests.get(f"{self.base}/health", timeout=3).status_code == 200
        except requests.RequestException:
            return False

    def ensure(self) -> None:
        if self.healthy():
            return
        with self._lock:
            if self.healthy():
                return
            self._start()

    def _start(self) -> None:
        cfg = self.cfg
        if not configurado(cfg):
            raise EmbedLlamaError(
                "embeddings via llama.cpp are not set up: need a llama-server binary "
                "(embed_llama_binary, or llama-server on PATH) and a GGUF file (embed_gguf). "
                "Run `delegation-core embed-llama setup`.")
        cmd = comando_do_servidor(cfg)
        logger.info("Starting llama.cpp embeddings: %s", " ".join(cmd))
        log_path = cfg.embed_log_path
        try:
            if log_path.exists() and log_path.stat().st_size > 10 * 1024 * 1024:
                log_path.replace(log_path.with_suffix(log_path.suffix + ".1"))
            self._log_fh = open(log_path, "a", encoding="utf-8")
            env = dict(os.environ)
            if (getattr(cfg, "embed_device", "auto") or "auto").strip().lower() == "cpu":
                env["CUDA_VISIBLE_DEVICES"] = ""
            self._proc = subprocess.Popen(cmd, stdout=self._log_fh, stderr=self._log_fh,
                                          env=env, **_detached())
            self._we_started_it = True
        except OSError as e:
            raise EmbedLlamaError(f"could not start llama-server for embeddings: {e}") from e
        limite = time.monotonic() + ESPERA_DE_PARTIDA_S
        while time.monotonic() < limite:
            if self.healthy():
                logger.info("llama.cpp embeddings ready on port %s", cfg.embed_port)
                return
            if self._proc.poll() is not None:
                raise EmbedLlamaError(
                    f"llama-server for embeddings exited with code {self._proc.returncode}: "
                    f"see {log_path}")
            time.sleep(0.5)
        raise EmbedLlamaError(f"llama-server for embeddings did not answer within "
                              f"{ESPERA_DE_PARTIDA_S}s: see {log_path}")

    def shutdown(self) -> None:
        if self._we_started_it and self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._we_started_it = False
        if self._log_fh:
            self._log_fh.close()
            self._log_fh = None


#: Um servidor por porta no processo: duas VaultManager nao sobem dois.
_SERVIDORES: dict[int, EmbedServer] = {}
_SERVIDORES_LOCK = threading.Lock()


def servidor_para(cfg) -> EmbedServer:
    with _SERVIDORES_LOCK:
        srv = _SERVIDORES.get(cfg.embed_port)
        if srv is None:
            srv = _SERVIDORES[cfg.embed_port] = EmbedServer(cfg)
        return srv


def _normalizar(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (v / n).astype(np.float32)


class LlamaCppEmbeddingFunction(EmbeddingFunction):
    """Funcao de embedding do ChromaDB que consulta o llama-server de embeddings."""

    def __init__(self, cfg, server: EmbedServer | None = None):
        self.cfg = cfg
        self.model_name = cfg.bge_model
        self.server = server or servidor_para(cfg)
        self.batch_size = int(getattr(cfg, "embed_batch_size", 0) or 0) or 8
        self._dim: int | None = None

    # -- o contrato do ChromaDB: identico ao do sentence_transformer, ver o docstring do modulo

    @staticmethod
    def name() -> str:
        return "sentence_transformer"

    def get_config(self) -> dict:
        return {"model_name": self.model_name, "device": "cpu",
                "normalize_embeddings": True, "kwargs": {}}

    @staticmethod
    def build_from_config(config: dict):  # pragma: no cover - o chroma nao reidrata a nossa
        raise NotImplementedError("LlamaCppEmbeddingFunction is built from Config, not from "
                                  "the stored collection config")

    @staticmethod
    def default_space() -> str:
        return "cosine"

    @staticmethod
    def supported_spaces() -> list[str]:
        return ["cosine", "l2", "ip"]

    def is_legacy(self) -> bool:
        return False

    # -- a chamada

    def _pedir(self, textos: list[str]) -> np.ndarray:
        r = requests.post(f"{self.server.base}/v1/embeddings",
                          json={"input": textos, "model": "embed"}, timeout=600)
        if r.status_code != 200:
            raise EmbedLlamaError(f"llama-server answered {r.status_code}: {r.text[:300]}")
        dados = sorted(r.json()["data"], key=lambda d: d["index"])
        return np.array([d["embedding"] for d in dados], dtype=np.float32)

    def _lote(self, textos: list[str]) -> np.ndarray:
        # Texto vazio: o llama.cpp recusa. Um espaco da um vetor valido e estavel.
        textos = [t if t.strip() else " " for t in textos]
        for corte in range(CORTES_MAXIMOS + 1):
            self.server.ensure()
            try:
                return self._pedir(textos)
            except requests.ConnectionError:
                # O dono do servidor saiu entre o `ensure` e o pedido: um novo `ensure` sobe outro.
                self.server.ensure()
                return self._pedir(textos)
            except EmbedLlamaError as e:
                grande = any(m in str(e).lower() for m in ("too large", "exceeds", "n_ubatch", "n_batch", "context"))
                if not grande or corte == CORTES_MAXIMOS:
                    raise
                # Mais tokens do que o servidor aceita: corta cada texto ao meio e tenta de novo.
                logger.warning("embedding input over the server limit; truncating (attempt %d)", corte + 1)
                textos = [t[: max(1, len(t) // 2)] for t in textos]
        raise EmbedLlamaError("unreachable")  # pragma: no cover

    def __call__(self, input):
        textos = list(input)
        saida = []
        for i in range(0, len(textos), self.batch_size):
            saida.append(self._lote(textos[i:i + self.batch_size]))
        if not saida:
            return []
        v = _normalizar(np.vstack(saida))
        if self._dim is None:
            self._dim = int(v.shape[1])
            esperado = DIMENSAO.get(self.model_name)
            if esperado and esperado != self._dim:
                raise EmbedLlamaError(
                    f"the GGUF returns {self._dim}-dimensional vectors but {self.model_name} "
                    f"has {esperado}: embed_gguf points at the wrong model")
        return [row for row in v]


# ── preparar a maquina ───────────────────────────────────────────────────────

def _llama_server_do_modelo(cfg) -> str:
    """O `llama_binary` do modelo de geracao, quando e de fato um llama-server (nao o mlx_lm.server)."""
    b = (getattr(cfg, "llama_binary", "") or "").strip()
    if not b or getattr(cfg, "motor_e_mlx", False):
        return ""
    p = Path(b).expanduser()
    return str(p) if p.exists() and "mlx" not in p.name.lower() else ""


def preparar(cfg, baixar: bool = True, verificar: bool = True) -> dict:
    """Deixa o BGE pronto para rodar pelo llama.cpp e grava na config.

    Acha (ou baixa) o llama-server, baixa o GGUF do modelo de busca e, se
    `verificar`, sobe o servidor e confere a dimensao do vetor. So grava
    `embed_backend: "llamacpp"` depois que tudo isso deu certo: uma preparacao que
    falha no meio nao deixa a busca apontando para um servidor que nao sobe.
    Devolve {"status": "ok"|"error", "detail", ...}.
    """
    if cfg.bge_model not in GGUF_CATALOGO:
        return {"status": "error",
                "detail": f"no GGUF is known for {cfg.bge_model}; supported: {', '.join(GGUF_CATALOGO)}"}

    binario = achar_llama_server(cfg) if getattr(cfg, "embed_llama_binary", "") else ""
    binario = binario or _llama_server_do_modelo(cfg) or shutil.which("llama-server") or ""
    if not binario and baixar:
        from .downloader import download_llama_binary
        achado = download_llama_binary(cfg.llama_dir)
        binario = str(achado) if achado else ""
    if not binario or not Path(binario).exists():
        return {"status": "error", "step": "binary",
                "detail": "no llama-server found. Install llama.cpp (macOS: `brew install llama.cpp`) "
                          "or set embed_llama_binary in ~/.delegation_core/config.json"}

    gguf = (cfg.embed_gguf or "").strip()
    if not gguf or not Path(gguf).expanduser().is_file():
        destino = gguf_padrao(cfg)
        if destino is None:  # pragma: no cover - coberto pelo catalogo acima
            return {"status": "error", "detail": "no GGUF known for this model"}
        if not destino.is_file():
            if not baixar:
                return {"status": "error", "step": "gguf", "detail": f"missing {destino}"}
            from .downloader import download_model
            repo, arquivo, _ = GGUF_CATALOGO[cfg.bge_model]
            baixado = download_model({"name": f"{cfg.bge_model} (GGUF)", "filename": arquivo,
                                      "url": url_do_gguf(cfg.bge_model)}, cfg.models_dir)
            if not baixado:
                return {"status": "error", "step": "gguf", "detail": "GGUF download failed"}
        gguf = str(destino)

    antes = (cfg.embed_llama_binary, cfg.embed_gguf, cfg.embed_backend)
    cfg.embed_llama_binary, cfg.embed_gguf = binario, gguf
    if verificar:
        try:
            ef = LlamaCppEmbeddingFunction(cfg, EmbedServer(cfg))
            vetor = ef(["ok"])[0]
            ef.server.shutdown()
        except Exception as e:  # noqa: BLE001 - qualquer falha deixa a config como estava
            cfg.embed_llama_binary, cfg.embed_gguf, cfg.embed_backend = antes
            return {"status": "error", "step": "verify", "detail": str(e)}
        dim = int(len(vetor))
    else:
        dim = None
    cfg.embed_backend = "llamacpp"
    cfg.save()
    return {"status": "ok", "binary": binario, "gguf": gguf, "dim": dim}
