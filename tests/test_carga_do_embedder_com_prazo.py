"""A carga do modelo de embeddings nao pode pendurar tudo que precisa do indice."""
import threading
import time

import pytest

from delegation_core import embeddings, vault as vault_mod
from delegation_core.config import Config
from delegation_core.vault import VaultManager


@pytest.fixture(autouse=True)
def sem_cargas_pendentes():
    embeddings._CARGAS.clear()
    yield
    embeddings._CARGAS.clear()


def _lenta():
    solta = threading.Event()
    chamadas = []

    def fabrica():
        chamadas.append(1)
        solta.wait(5)
        return "embedder"
    return fabrica, solta, chamadas


def test_carga_que_passa_do_prazo_solta_quem_espera_com_o_motivo():
    fabrica, solta, _ = _lenta()
    t0 = time.time()
    with pytest.raises(TimeoutError, match="passou de 0.3 s"):
        embeddings.carregar_com_prazo(("k",), fabrica, 0.3)
    assert time.time() - t0 < 2
    solta.set()


def test_a_proxima_chamada_continua_esperando_a_mesma_carga_e_nao_inicia_outra():
    fabrica, solta, chamadas = _lenta()
    with pytest.raises(TimeoutError):
        embeddings.carregar_com_prazo(("k",), fabrica, 0.2)
    solta.set()
    assert embeddings.carregar_com_prazo(("k",), fabrica, 3) == "embedder"
    assert chamadas == [1], "iniciou uma segunda carga: dobraria a memoria do modelo"


def test_erro_da_carga_chega_a_quem_espera_e_a_proxima_tenta_de_novo():
    n = []

    def quebra():
        n.append(1)
        raise ValueError("pesos corrompidos")
    with pytest.raises(ValueError, match="pesos corrompidos"):
        embeddings.carregar_com_prazo(("k",), quebra, 2)
    with pytest.raises(ValueError):
        embeddings.carregar_com_prazo(("k",), quebra, 2)
    assert len(n) == 2


def test_prazo_zero_ou_ausente_e_a_chamada_direta():
    chamou = []
    assert embeddings.carregar_com_prazo(("k",), lambda: chamou.append(threading.current_thread().name) or 1, 0) == 1
    assert embeddings.carregar_com_prazo(("k",), lambda: 2, None) == 2
    assert chamou == [threading.current_thread().name], "com prazo desligado nao pode criar thread"
    assert embeddings._CARGAS == {}


def test_cargas_de_modelos_diferentes_nao_se_misturam():
    a, solta_a, _ = _lenta()
    with pytest.raises(TimeoutError):
        embeddings.carregar_com_prazo(("a",), a, 0.1)
    assert embeddings.carregar_com_prazo(("b",), lambda: "outro", 1) == "outro"
    solta_a.set()


def test_construir_embedding_function_usa_o_prazo_do_config(tmp_path):
    fabrica, solta, _ = _lenta()
    cfg = Config(vault_path=str(tmp_path), embed_load_timeout_sec=0.2)
    with pytest.raises(TimeoutError):
        embeddings.construir_embedding_function(cfg, lambda *a, **k: fabrica())
    solta.set()


def test_o_vault_conta_o_motivo_no_init_error_e_se_recupera_quando_a_carga_termina(tmp_path, monkeypatch):
    solta = threading.Event()
    chamadas = []

    class Ef:
        def __call__(self, input):
            return [[1.0, 0.0]] * len(list(input))

    def lenta(*a, **k):
        chamadas.append(1)
        solta.wait(5)
        return Ef()
    monkeypatch.setattr(vault_mod, "make_bge_embedding_function", lenta)
    cfg = Config(vault_path=str(tmp_path / "v"), index_backend="sqlite", embed_device="cpu",
                 embed_load_timeout_sec=0.3)
    vm = VaultManager(cfg)
    vm._init()
    assert not vm._initialized
    assert vm.init_error and "passou de" in vm.init_error, vm.init_error
    solta.set()
    vm._init()
    assert vm._initialized and vm.init_error is None
    assert chamadas == [1]
