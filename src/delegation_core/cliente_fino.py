"""Cliente fino do daemon para `shell`, `recall` e `filters hook` (item 6.1.2).

Cada comando Bash do agente passa pelo hook e, quando um filtro casa, vira um processo
`delegation-core shell`. Medido em 23/11/2026 nesta maquina: 65 a 75 ms por `shell` e 61 ms
por hook, dos quais 50 ms eram so importar o `cli` e montar o argparse de todos os
subcomandos, e outros ~20 ms carregar os filtros TOML a cada chamada. O daemon ja tem tudo
isso carregado.

Aqui fica so a biblioteca padrao leve (os, json, socket): o cliente pergunta ao daemon o
que fazer, roda o comando UMA vez no proprio processo (mesmo diretorio, mesmo ambiente do
agente) e manda a saida para o daemon filtrar e guardar. Assim o daemon e o unico escritor
de `saidas.sqlite3`.

Regra de ouro: qualquer falha do daemon (desligado, porta errada, token recusado, resposta
estranha, demora) devolve None, e quem chamou segue pelo caminho local de antes. Nunca se
roda o comando de novo e nunca se perde a saida.

HTTP por socket cru: `http.client` sozinho custa ~19 ms para importar, mais que a viagem.
"""

from __future__ import annotations

import json
import os
import socket
import sys

#: Quanto esperar o daemon aceitar a conexao. Ele e local: se nao aceitou nisso, nao esta la.
TEMPO_CONEXAO = 0.25
#: Quanto esperar a resposta das rotas rapidas (plano, guardar, recall, hook).
TEMPO_RESPOSTA = 5.0
#: Quanto esperar o daemon filtrar uma saida (o compressor pode levar alguns segundos).
TEMPO_EXIBIR = 30.0
#: Variavel que desliga o cliente fino (diagnostico e testes): qualquer valor nao vazio.
DESLIGAR = "DELEGATION_CORE_SEM_DAEMON"


def _pasta_config() -> str:
    """A mesma pasta que `config.CONFIG_DIR`, sem importar o `config` (~23 ms).

    Se o `config` ja foi carregado neste processo (testes, ou o proprio daemon), vale o que
    ele diz: os testes reapontam `config.CONFIG_DIR` para uma pasta temporaria."""
    cfg = sys.modules.get("delegation_core.config")
    if cfg is not None and getattr(cfg, "CONFIG_DIR", None) is not None:
        return str(cfg.CONFIG_DIR)
    return os.path.join(os.path.expanduser("~"), ".delegation_core")


def _destino() -> tuple[int, str] | None:
    """(porta da API local, token) lidos do config.json, ou None se nao der para falar com o daemon."""
    if os.environ.get(DESLIGAR):
        return None
    try:
        with open(os.path.join(_pasta_config(), "config.json"), encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return None
    porta = dados.get("dashboard_port", 8788)
    token = dados.get("server_token") or ""
    if not isinstance(porta, int) or not porta or not token:
        return None
    return porta, token


def chamar(rota: str, corpo: dict, tempo: float = TEMPO_RESPOSTA) -> dict | None:
    """POST de `corpo` em JSON na rota da API local do daemon. None em qualquer falha."""
    alvo = _destino()
    if alvo is None:
        return None
    porta, token = alvo
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    pedido = (f"POST {rota} HTTP/1.1\r\nHost: 127.0.0.1:{porta}\r\nAuthorization: Bearer {token}\r\n"
              f"Content-Type: application/json\r\nContent-Length: {len(dados)}\r\nConnection: close\r\n\r\n"
              ).encode("ascii") + dados
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=TEMPO_CONEXAO) as s:
            s.settimeout(tempo)
            s.sendall(pedido)
            partes = []
            while True:
                bloco = s.recv(65536)
                if not bloco:
                    break
                partes.append(bloco)
    except OSError:
        return None
    resposta = b"".join(partes)
    cabeca, sep, resto = resposta.partition(b"\r\n\r\n")
    if not sep:
        return None
    linhas = cabeca.split(b"\r\n")
    status = linhas[0].split(b" ")
    if len(status) < 2 or status[1] != b"200":
        return None
    cabecalhos = {}
    for l in linhas[1:]:
        k, _, v = l.partition(b":")
        cabecalhos[k.strip().lower()] = v.strip()
    if cabecalhos.get(b"transfer-encoding", b"").lower() == b"chunked":
        resto = _sem_chunks(resto)
        if resto is None:
            return None
    elif b"content-length" in cabecalhos:
        try:
            n = int(cabecalhos[b"content-length"])
        except ValueError:
            return None
        if len(resto) < n:
            return None  # conexao caiu no meio: nao confie numa resposta pela metade
        resto = resto[:n]
    try:
        r = json.loads(resto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return r if isinstance(r, dict) else None


def _sem_chunks(b: bytes) -> bytes | None:
    saida = []
    while True:
        tam, sep, b = b.partition(b"\r\n")
        if not sep:
            return None
        try:
            n = int(tam.split(b";")[0], 16)
        except ValueError:
            return None
        if n == 0:
            return b"".join(saida)
        if len(b) < n + 2:
            return None
        saida.append(b[:n])
        b = b[n + 2:]


# ── shell ──────────────────────────────────────────────────────────────────

def _no_shell(comando: str):
    """(argv, shell=) para rodar `comando` no shell do sistema.

    `sh -c` onde houver `sh` (Linux, macOS, Windows com o Git Bash no PATH); sem ele, o shell
    padrao do Python (`cmd.exe` no Windows). Ate 17/11/2026 era "/bin/sh" fixo, e no Windows
    todo `delegation-core shell` dava FileNotFoundError. Mora aqui, e nao no `cli`, para o
    cliente fino nao importar nada pesado."""
    import shutil
    sh = shutil.which("sh") or ("/bin/sh" if os.path.exists("/bin/sh") else None)
    return ([sh, "-c", comando], False) if sh else (comando, True)


def rodar(comando: str, plano: dict) -> tuple[str | None, int]:
    """Roda o comando UMA vez, como o `plano` manda. (saida capturada, codigo).

    No modo `direto` a saida ja foi escrita (intacta, no fim, com o stderr indo direto ao
    terminal) e a saida devolvida e None. Usado aqui e pelo caminho local (`filtros_saida.cli`),
    para os dois rodarem o comando exatamente do mesmo jeito."""
    import subprocess
    modo = plano["modo"]
    argv, usar_shell = _no_shell(plano.get("comando_real") or comando)
    if modo == "direto":
        p = subprocess.run(argv, shell=usar_shell, stdout=subprocess.PIPE)
        sys.stdout.write(p.stdout.decode("utf-8", "replace"))
        return None, p.returncode
    if modo == "modulo":
        so_stdout = bool(plano.get("so_stdout"))
        p = subprocess.run(argv, shell=usar_shell, stdout=subprocess.PIPE,
                           stderr=None if so_stdout else subprocess.STDOUT)
        return p.stdout.decode("utf-8", "replace"), p.returncode
    juntar = bool(plano.get("juntar_stderr"))
    p = subprocess.run(argv, shell=usar_shell, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE if juntar else None)
    saida = p.stdout.decode("utf-8", "replace")
    if juntar:
        saida += (p.stderr or b"").decode("utf-8", "replace")
    return saida, p.returncode


def shell(comando: str) -> int | None:
    """`delegation-core shell <comando>` pelo daemon. None: o daemon nao atendeu ANTES de o
    comando rodar, e quem chamou deve seguir pelo caminho local (que roda o comando)."""
    plano = chamar("/api/saidas/plano", {"comando": comando})
    if not plano or plano.get("modo") not in ("direto", "toml", "modulo", "rota"):
        return None   # "local" (git e gh, que consultam a ferramenta varias vezes) ou falha
    saida, codigo = rodar(comando, plano)
    if saida is None:
        return codigo
    r = chamar("/api/saidas/exibir", {"comando": comando, "modo": plano["modo"], "saida": saida,
                                      "codigo": codigo}, TEMPO_EXIBIR)
    texto = r.get("output") if r else None
    if not isinstance(texto, str):
        # O comando ja rodou: nunca rodar de novo. Filtra aqui mesmo, como antes do 6.1.2.
        texto = _exibir_local(comando, plano["modo"], saida, codigo)
    print(texto)
    return codigo


def _exibir_local(comando: str, modo: str, saida: str, codigo: int) -> str:
    """A mesma decisao que o daemon toma em /api/saidas/exibir, feita neste processo."""
    from .filtros_saida import servico
    return servico.exibir(comando, modo, saida, codigo)["output"]


# ── recall e hook ──────────────────────────────────────────────────────────

def recall(h: str, a_partir: int = 0) -> dict | None:
    """O registro guardado, pelo daemon. None: nao atendeu (o chamador le o arquivo direto)."""
    r = chamar("/api/saidas/recall", {"hash": h, "from": a_partir})
    if r is None or "found" not in r:
        return None
    return r


def hook(payload: dict, executavel: str = "delegation-core") -> tuple[bool, dict | None]:
    """(atendido, resposta do hook). atendido False: o daemon nao respondeu, decida localmente."""
    r = chamar("/api/filtros/reescrever", {"payload": payload, "executavel": executavel})
    if r is None or "resposta" not in r:
        return False, None
    resposta = r["resposta"]
    return True, resposta if isinstance(resposta, dict) else None


# ── escritor unico ─────────────────────────────────────────────────────────

def guardar(conteudo: str, comando: str, codigo: int | None, mostrado_ate: int) -> tuple[bool, dict | None]:
    """(atendido, resultado) de `execucao.guardar` feito pelo daemon."""
    r = chamar("/api/saidas/guardar", {"conteudo": conteudo, "comando": comando, "codigo": codigo,
                                       "mostrado_ate": mostrado_ate})
    if r is None or "guardado" not in r:
        return False, None
    g = r["guardado"]
    return True, g if isinstance(g, dict) else None


def guardar_ccr(chave: str, conteudo: str) -> bool:
    """True se o daemon guardou o original do CCR."""
    r = chamar("/api/saidas/ccr", {"chave": chave, "conteudo": conteudo})
    return bool(r and r.get("ok") is True)
