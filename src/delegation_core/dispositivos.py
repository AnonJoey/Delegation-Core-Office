"""Em que dispositivo as coisas estao rodando, e quem escondeu a placa.

## O defeito que motivou este modulo, medido em 26/09/2026

O `llama-server` e processo **filho** do daemon, entao herda o ambiente dele.
O drop-in de systemd `cpu-embeddings.conf`, escrito em 09/09/2026 para tirar o
BGE-m3 da placa, poe `CUDA_VISIBLE_DEVICES=` vazio no daemon, e com isso tirou o
**llama junto**.

Medido com o daemon no ar:

| | |
|---|---|
| geracao do modelo local | **5,5 tokens/s** |
| CPU do `llama-server` | 986% |
| RAM do `llama-server` | 11,7 GB |
| GPU em uso | **656 MiB de 16311** |

E o comentario do proprio drop-in diz que a intencao era o contrario: *"o
llama-server passou a rodar com offload total na GPU (-ngl 99), e o BGE segurava
3364 MiB"*. Era llama na placa e BGE fora. O instrumento nao distingue os dois
processos.

## Por que passou meses despercebido

**Nada falha.** O modelo responde, so devagar, e o `heartbeat()` reportava
`llama_cpp: "on-demand"` sem dizer em que dispositivo. O `vault.py` ja carregava
a descricao exata do sintoma, escrita para o caso do BGE: *"search kept working
and got an order of magnitude slower with nothing in the response to say so"*.

Este modulo existe para que essa frase deixe de ser possivel: o dispositivo vai
junto do estado, e esconder a placa por ambiente vira um aviso explicito.

## Criterio de lego

Nao sabe o que e vault, engine, heartbeat ou llama. Le duas variaveis de
ambiente e, se o torch estiver instalado, pergunta a ele. Recebe a preferencia
do encoder como argumento. Da para apagar este modulo e o sistema volta ao que
era, perdendo so a visibilidade.
"""

from __future__ import annotations

import json
import os

#: A variavel que o drop-in usa. Vazia (e nao ausente) significa "esconda todas
#: as placas", e e diferente de nao estar definida.
VARIAVEL = "CUDA_VISIBLE_DEVICES"


def _valor_cuda() -> str | None:
    """O valor cru da variavel, ou None quando ela nao existe.

    A distincao importa: ausente e o padrao do sistema, vazia e uma decisao de
    alguem. Colapsar as duas em "sem GPU" apagaria justamente a informacao que
    este modulo existe para mostrar.
    """
    return os.environ.get(VARIAVEL)


def placa_escondida_por_ambiente() -> bool:
    """True quando alguem apagou as placas deste processo pela variavel.

    So a string vazia esconde tudo. `"0"` seleciona a placa 0, `"-1"` tambem
    esconde na pratica mas nao e o que o drop-in usa, e nao vou tratar como
    equivalente sem ter medido.
    """
    valor = _valor_cuda()
    return valor is not None and valor.strip() == ""


def gpu_visivel() -> bool:
    """A placa esta ao alcance DESTE processo agora.

    Falha calada por escolha: sem torch instalado, ou com torch que nao
    inicializa, a resposta e "nao", que e o comportamento observavel.
    """
    if placa_escondida_por_ambiente():
        return False
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return False


#: Nos de dispositivo que a NVIDIA cria. Checar o disco em vez de perguntar ao
#: torch e deliberado: o torch responde sobre o PROCESSO, e responde "nao tem
#: placa" exatamente no caso que interessa detectar, que e a placa existir na
#: maquina e estar escondida deste processo.
_NOS_NVIDIA = ("/dev/nvidia0", "/dev/nvidiactl", "/proc/driver/nvidia/version")


def placa_existe_na_maquina() -> bool:
    """Ha uma placa NVIDIA nesta maquina, independente de este processo ve-la."""
    from pathlib import Path as _P
    for caminho in _NOS_NVIDIA:
        try:
            if _P(caminho).exists():
                return True
        except OSError:
            continue
    return False


def pids_do_daemon() -> list[int]:
    """Pids de daemon vivos, lidos pelos arquivos de sessao do proprio projeto.

    Usa `~/.delegation_core/sessions/`, que e o mecanismo que o
    `client_tracking` ja mantem, em vez de sair procurando processo por nome:
    `pgrep -f` casa com o proprio shell, que e armadilha ja catalogada nesta
    casa.
    """
    from pathlib import Path as _P

    pasta = _P.home() / ".delegation_core" / "sessions"
    achados: set[int] = set()
    try:
        for f in pasta.glob("*.json"):
            try:
                pid = json.loads(f.read_text(encoding="utf-8")).get("pid")
            except Exception:
                continue
            if isinstance(pid, int) and _P(f"/proc/{pid}").is_dir():
                achados.add(pid)
    except OSError:
        pass
    return sorted(achados)


def placa_escondida_no_pid(pid: int) -> bool | None:
    """A placa esta escondida NAQUELE processo? None quando nao da para saber.

    None e diferente de False, e a distincao importa: fora do Linux nao existe
    `/proc`, e um processo de outro usuario nao deixa ler o ambiente. Responder
    False nesses casos afirmaria que esta tudo bem sem ter olhado.
    """
    from pathlib import Path as _P

    try:
        bruto = _P(f"/proc/{pid}/environ").read_bytes()
    except (OSError, ValueError):
        return None
    for entrada in bruto.split(b"\0"):
        if entrada.startswith(VARIAVEL.encode() + b"="):
            return entrada.split(b"=", 1)[1].strip() == b""
    return False


def situacao(preferencia_do_encoder: str | None = "auto") -> dict:
    """Retrato do que este processo enxerga, para entrar no `heartbeat()`.

    `preferencia_do_encoder` e o `cfg.embed_device`. Recebido como argumento e
    nao lido de um `Config`, porque este modulo nao conhece `Config`.

    O campo que carrega o valor todo e `aviso`: ele so aparece quando a placa
    foi escondida por ambiente, e e a unica coisa aqui que um humano precisa
    ler sem ser perguntado.
    """
    from .embeddings import resolver_dispositivo

    escondida = placa_escondida_por_ambiente()
    retrato = {
        "gpu_visivel": gpu_visivel(),
        "encoder": resolver_dispositivo(preferencia_do_encoder),
        "cuda_visible_devices": _valor_cuda(),
    }
    if escondida:
        # O texto nomeia a heranca porque foi exatamente ela que escondeu o
        # problema: quem le "CUDA_VISIBLE_DEVICES vazio" pensa no encoder, e
        # nao no llama-server que nasce deste processo.
        retrato["aviso"] = (
            f"{VARIAVEL} esta vazia neste processo: nenhuma GPU e visivel, e "
            "todo processo filho herda isso, o llama-server inclusive. "
            "Para por so o encoder na CPU use embed_device=cpu, que nao "
            "esconde a placa dos filhos."
        )
    return retrato
