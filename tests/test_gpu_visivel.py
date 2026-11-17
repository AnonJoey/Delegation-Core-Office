"""Placa NVIDIA escondida do daemon (doctor gpu_visivel). Esconder a placa por ambiente precisa aparecer, porque nada falha quando ela some.

## O caso real, medido em 26/09/2026

O drop-in de systemd `cpu-embeddings.conf` poe `CUDA_VISIBLE_DEVICES=` vazio no
daemon para tirar o BGE-m3 da placa. O `llama-server` e processo **filho** do
daemon e herda o ambiente, entao foi junto:

| | |
|---|---|
| geracao do modelo local | 5,5 tokens/s |
| CPU do `llama-server` | 986% |
| GPU em uso | 656 MiB de 16311 |

O comentario do proprio drop-in diz que a intencao era o oposto, llama COM
offload total na placa.

**Nada falhava.** O `heartbeat()` dizia `llama_cpp: "on-demand"` sem dizer o
dispositivo, e o sintoma era so lentidao. O `vault.py` ja carregava a frase que
descreve essa classe, escrita para o BGE: *"search kept working and got an order
of magnitude slower with nothing in the response to say so"*.

Estes testes guardam que isso deixa de ser invisivel.
"""

from __future__ import annotations

from delegation_core import dispositivos


def test_variavel_vazia_e_diferente_de_variavel_ausente(monkeypatch):
    """A distincao que carrega o achado inteiro.

    Ausente e o padrao do sistema. Vazia e decisao de alguem. Colapsar as duas
    em "sem GPU" apagaria justamente a informacao que o modulo existe para
    mostrar, e foi essa informacao que faltou por meses.
    """
    monkeypatch.delenv(dispositivos.VARIAVEL, raising=False)
    assert dispositivos.placa_escondida_por_ambiente() is False

    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    assert dispositivos.placa_escondida_por_ambiente() is True


def test_placa_selecionada_nao_conta_como_escondida(monkeypatch):
    """`"0"` escolhe a placa 0. So a string vazia esconde tudo."""
    monkeypatch.setenv(dispositivos.VARIAVEL, "0")
    assert dispositivos.placa_escondida_por_ambiente() is False


def test_espaco_em_branco_conta_como_vazia(monkeypatch):
    monkeypatch.setenv(dispositivos.VARIAVEL, "   ")
    assert dispositivos.placa_escondida_por_ambiente() is True


def test_gpu_nao_e_visivel_quando_escondida(monkeypatch):
    """Sem esta linha o modulo perguntaria ao torch, que responde sobre o
    processo e nao sobre a intencao de quem configurou."""
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    assert dispositivos.gpu_visivel() is False


def test_o_aviso_nomeia_a_heranca(monkeypatch):
    """O teste que carrega o argumento.

    Um aviso que so dissesse "sem GPU" mandaria a pessoa olhar o encoder, que e
    onde o drop-in foi escrito, e nao o `llama-server`, que e quem estava
    pagando. **A heranca precisa estar no texto**, porque e ela que nao e
    obvia.

    Conferido por mutacao: trocar o texto por um que nao cite processo filho
    nem llama derruba este teste.
    """
    monkeypatch.setenv(dispositivos.VARIAVEL, "")
    aviso = dispositivos.situacao("auto").get("aviso", "")

    assert aviso, "placa escondida tem que produzir aviso"
    assert "filho" in aviso.lower(), "o aviso precisa dizer que os filhos herdam"
    assert "llama" in aviso.lower(), "o aviso precisa nomear quem mais e afetado"
    assert "embed_device" in aviso, "o aviso precisa apontar a saida com pontaria"


def test_sem_placa_escondida_nao_ha_aviso(monkeypatch):
    """Aviso que aparece sempre vira ruido e para de ser lido."""
    monkeypatch.delenv(dispositivos.VARIAVEL, raising=False)
    assert "aviso" not in dispositivos.situacao("auto")


def test_a_situacao_respeita_a_preferencia_do_encoder(monkeypatch):
    """O retrato mostra onde o encoder VAI, nao onde ele poderia ir."""
    monkeypatch.delenv(dispositivos.VARIAVEL, raising=False)
    assert dispositivos.situacao("cpu")["encoder"] == "cpu"


def test_a_situacao_entra_no_heartbeat():
    """A LIGACAO, e nao a funcao.

    Este repo ja teve campo de `Config` existindo inerte por nao chegar a quem
    usa, e o `vault.py` carrega o comentario disso. Um retrato de dispositivo
    que nao chega ao `heartbeat()` nao mostra nada a ninguem.

    Conferido por mutacao: tirar a chave do dicionario do heartbeat derruba
    este teste.
    """
    import inspect

    from delegation_core import server

    fonte = inspect.getsource(server.heartbeat)
    assert "dispositivos.situacao" in fonte, (
        "o heartbeat precisa reportar o dispositivo; sem isso o sintoma volta a "
        "ser so lentidao sem explicacao")
