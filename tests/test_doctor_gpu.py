"""O `doctor` passa a ver a placa escondida por ambiente.

## De onde esta checagem nasceu

Cada uma das checagens do `doctor` nasceu de algo que passou despercebido.
Esta tambem, e o caso foi medido em 26/09/2026.

O drop-in de systemd `cpu-embeddings.conf` poe `CUDA_VISIBLE_DEVICES=` vazio no
daemon para tirar o BGE-m3 da placa. O `llama-server` e processo **filho** do
daemon, entao foi junto:

| | |
|---|---|
| geracao do modelo local | 5,5 tokens/s |
| CPU do `llama-server` | 986% |
| GPU em uso | 656 MiB de 16311 |

E o comentario do proprio drop-in diz que a intencao era o contrario: llama com
offload total na placa, BGE fora.

**Nada falhava.** O modelo respondia, so devagar, e por isso a checagem e do
`doctor` e nao um erro em tempo de execucao.

## A discriminacao que a checagem precisa fazer

"Tem placa nesta maquina" e "este processo enxerga a placa" sao perguntas
diferentes, e o defeito vive exatamente na diferenca. Perguntar ao torch nao
serve: ele responde sobre o processo, e responde "nao tem placa" justamente no
caso que interessa detectar.
"""

from __future__ import annotations

import pytest

from delegation_core import dispositivos, doctor
from delegation_core.config import Config


@pytest.fixture(autouse=True)
def sem_daemon_vivo(monkeypatch):
    """Nenhum daemon, salvo onde o teste disser o contrario.

    A checagem passou a ler o ambiente do DAEMON, que e o que importa. Sem esta
    fixture os testes leriam o daemon REAL desta maquina, e um teste que
    depende do estado da maquina nao e teste: passaria ou falharia conforme o
    usuario tivesse o servico no ar.
    """
    monkeypatch.setattr(dispositivos, "pids_do_daemon", lambda: [])


def test_sem_placa_na_maquina_nao_ha_o_que_avisar(monkeypatch):
    """Maquina so-CPU nao pode receber aviso: seria ruido eterno."""
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: False)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    r = doctor.check_gpu_visivel(Config())
    assert r["status"] == "ok"


def test_placa_visivel_passa(monkeypatch):
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.delenv(dispositivos.VARIAVEL, raising=False)
    assert doctor.check_gpu_visivel(Config())["status"] == "ok"


def test_placa_existente_e_escondida_vira_aviso(monkeypatch):
    """O caso real, reproduzido.

    Conferido por mutacao: fazer a checagem perguntar `gpu_visivel()` em vez de
    combinar as duas perguntas a derruba, porque `gpu_visivel()` responde
    `False` tanto para maquina sem placa quanto para placa escondida, e as duas
    pedem respostas opostas.
    """
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    r = doctor.check_gpu_visivel(Config())

    assert r["status"] == "warn"
    assert "fix" in r, "aviso sem saida nao ajuda ninguem"


def test_o_aviso_nomeia_o_llama_em_modo_hibrido(monkeypatch):
    """O que torna este aviso util e dizer QUEM mais foi junto.

    Um texto que so falasse do encoder mandaria a pessoa olhar o lugar onde o
    drop-in foi escrito, e nao o `llama-server`, que e quem paga a conta.
    """
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    r = doctor.check_gpu_visivel(Config(engine_mode="hybrid"))
    assert "llama" in r["detail"].lower()
    assert "filho" in r["detail"].lower()


def test_em_modo_agent_o_aviso_nao_menciona_llama(monkeypatch):
    """Em `agent` nao ha modelo local, entao citar o llama seria mentira.

    O aviso continua existindo porque o encoder ainda perde a placa.
    """
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    r = doctor.check_gpu_visivel(Config(engine_mode="agent"))
    assert r["status"] == "warn"
    assert "llama" not in r["detail"].lower()


def test_e_aviso_e_nunca_erro(monkeypatch):
    """`doctor` sai com codigo 1 so em erro, e esconder a placa pode ser
    decisao deliberada de quem so tem CPU. Derrubar cron alheio por causa
    disso seria pior que o problema."""
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    assert doctor.check_gpu_visivel(Config())["status"] != "error"


def test_a_checagem_entra_no_run_all():
    """A LIGACAO. Uma checagem fora do `run_all` nao checa nada de ninguem.

    Conferido por mutacao: tirar a linha do `run_all` derruba este teste.
    """
    import inspect

    fonte = inspect.getsource(doctor.run_all)
    assert "check_gpu_visivel" in fonte, (
        "a checagem precisa estar no run_all; fora dele ninguem a executa")


def test_o_daemon_e_quem_vale_e_nao_o_proprio_processo(monkeypatch):
    """O defeito da primeira versao desta checagem, corrigido.

    Rodando pela CLI ela dizia "a placa esta visivel" enquanto o daemon estava
    cego, porque olhava a si mesma. Medido em 26/09/2026: o daemon tinha
    CUDA_VISIBLE_DEVICES vazia e o `doctor` da CLI reportava ok.

    Conferido por mutacao: voltar a checagem para
    `placa_escondida_por_ambiente()` derruba este teste.
    """
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.delenv(dispositivos.VARIAVEL, raising=False)   # este processo enxerga
    monkeypatch.setattr(dispositivos, "pids_do_daemon", lambda: [4242])
    monkeypatch.setattr(dispositivos, "placa_escondida_no_pid", lambda pid: True)

    r = doctor.check_gpu_visivel(Config())
    assert r["status"] == "warn", "o daemon esta cego; o processo da CLI nao importa"
    assert "4242" in r["detail"], "o aviso tem que dizer de qual processo fala"


def test_daemon_ilegivel_cai_no_proprio_processo(monkeypatch):
    """`None` de `placa_escondida_no_pid` e "nao da para saber", e nao "tudo bem".

    Fora do Linux nao ha `/proc`, e processo de outro usuario nao deixa ler o
    ambiente. Nesses casos a checagem volta a falar de si mesma, dizendo isso.
    """
    monkeypatch.setattr(dispositivos, "placa_existe_na_maquina", lambda: True)
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    monkeypatch.setattr(dispositivos, "pids_do_daemon", lambda: [4242])
    monkeypatch.setattr(dispositivos, "placa_escondida_no_pid", lambda pid: None)

    r = doctor.check_gpu_visivel(Config())
    assert r["status"] == "warn"
    assert "neste processo" in r["detail"]
