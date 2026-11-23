"""Cliente fino do `shell`, do `recall` e do hook, e o daemon como escritor unico (item 6.1.2).

O que estes testes provam, e como:
- o cliente pelo daemon mostra exatamente o que o caminho local mostra, nos cinco modos;
- o comando roda UMA vez, com o daemon atendendo, caindo antes ou caindo depois de rodar;
- com o daemon no ar, o processo do cliente nao grava `saidas.sqlite3` (o daemon grava);
- os workers do pool nao gravam: juntam e o daemon grava ao receber;
- muitos clientes ao mesmo tempo nao perdem nenhuma saida.

O cliente roda como subprocesso, com HOME proprio: o daemon de teste grava no CONFIG_DIR do
conftest, e o cliente le o config.json do HOME dele. Se o cliente gravasse por conta propria, o
arquivo apareceria no HOME dele, e e isso que os testes procuram.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from delegation_core import cliente_fino, dashboard_api, entrada_rapida
from delegation_core.filtros_saida import execucao, servico
from tests._dashboard_auth import TOKEN

# ── comandos falsos: saida fixa e contagem de execucoes ───────────────────────

_FALSOS = {
    # toml (make.toml): muitas linhas, o filtro corta e a guarda entra
    "make": "for i in $(seq 1 400); do echo \"make[1]: Entering directory '/tmp/x$i'\"; echo \"gcc -c arquivo$i.c\"; done; echo 'ERRO: falhou' >&2; exit 2",
    # modulo portado (pytest, so stdout)
    "pytest": "printf '%s\\n' '============ test session starts ============' 'collected 3 items' '' 'a.py ..F' '' '=== FAILURES ===' '___ test_c ___' 'assert 1 == 2' '=== 1 failed, 2 passed in 0.12s ==='; exit 1",
    # rota (docker, modulo Rust do RTK nao portado): compressor de log
    "docker": "for i in $(seq 1 300); do echo \"2026-11-23T10:00:$((i % 60))Z INFO container web-$((i % 7)) healthy check=$i\"; done; echo '2026-11-23T10:05:00Z ERROR container db-1 exited 137'",
}


@pytest.fixture
def falsos(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    contador = tmp_path / "execucoes.log"
    for nome, corpo in _FALSOS.items():
        p = bindir / nome
        p.write_text(f"#!/bin/sh\necho {nome} >> '{contador}'\n{corpo}\n")
        p.chmod(0o755)
    return bindir, contador


def _execucoes(contador: Path, nome: str) -> int:
    if not contador.exists():
        return 0
    return [l.strip() for l in contador.read_text().splitlines()].count(nome)


# ── daemon de teste ───────────────────────────────────────────────────────────

@pytest.fixture
def daemon(monkeypatch):
    """A API local de verdade, numa porta livre, com este processo como escritor unico."""
    monkeypatch.setattr(execucao, "_ESCRITOR", True)
    monkeypatch.setattr(dashboard_api, "_token", TOKEN)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), dashboard_api._Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _home(tmp_path: Path, nome: str, porta: int | None) -> Path:
    home = tmp_path / nome
    (home / ".delegation_core").mkdir(parents=True)
    if porta is not None:
        (home / ".delegation_core" / "config.json").write_text(
            json.dumps({"dashboard_port": porta, "server_token": TOKEN}))
    return home


def _rodar(args, home: Path, bindir: Path, sem_daemon: bool, entrada: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != "DELEGATION_CORE_SEM_DAEMON"}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["PATH"] = f"{bindir}{os.pathsep}{env.get('PATH', '')}"
    if sem_daemon:
        env["DELEGATION_CORE_SEM_DAEMON"] = "1"
    return subprocess.run([sys.executable, "-m", "delegation_core.entrada_rapida", *args],
                          input=entrada, capture_output=True, text=True, env=env, timeout=120)


def _linhas_guardadas(pasta: Path) -> int:
    arq = pasta / "saidas.sqlite3"
    if not arq.exists():
        return 0
    with sqlite3.connect(arq) as c:
        return c.execute("SELECT COUNT(*) FROM s").fetchone()[0]


COMANDOS = ["make all", "pytest -q", "docker ps", "echo oi tudo bem"]


# ── paridade e escritor unico ─────────────────────────────────────────────────

@pytest.mark.parametrize("comando", COMANDOS)
def test_pelo_daemon_mostra_o_mesmo_que_o_caminho_local(comando, daemon, falsos, tmp_path):
    from delegation_core import config
    bindir, contador = falsos
    local = _rodar(["shell", comando], _home(tmp_path, "local", None), bindir, sem_daemon=True)
    antes = _execucoes(contador, comando.split()[0])
    fino_home = _home(tmp_path, "fino", daemon)
    fino = _rodar(["shell", comando], fino_home, bindir, sem_daemon=False)
    assert fino.stdout == local.stdout
    assert fino.returncode == local.returncode
    if comando.split()[0] in _FALSOS:
        assert _execucoes(contador, comando.split()[0]) == antes + 1, "o comando rodou mais de uma vez"
    # O cliente nao gravou nada no proprio HOME: quem grava e o daemon.
    assert not (fino_home / ".delegation_core" / "saidas.sqlite3").exists()
    if "recall" in local.stdout:
        assert _linhas_guardadas(Path(config.CONFIG_DIR)) >= 1


def test_os_modos_cobrem_os_cinco_caminhos(falsos):
    assert servico.plano("git status")["modo"] == "local"
    assert servico.plano("make all")["modo"] == "toml"
    assert servico.plano("pytest -q")["modo"] == "modulo"
    assert servico.plano("docker ps")["modo"] == "rota"
    assert servico.plano("echo oi")["modo"] == "direto"


def test_com_o_daemon_fora_o_resultado_e_o_mesmo_e_roda_uma_vez(falsos, tmp_path):
    bindir, contador = falsos
    with socket.socket() as s:   # uma porta que ninguem escuta
        s.bind(("127.0.0.1", 0))
        porta_morta = s.getsockname()[1]
    local = _rodar(["shell", "make all"], _home(tmp_path, "local", None), bindir, sem_daemon=True)
    home = _home(tmp_path, "fino", porta_morta)
    fino = _rodar(["shell", "make all"], home, bindir, sem_daemon=False)
    assert fino.stdout == local.stdout and fino.returncode == local.returncode
    assert _execucoes(contador, "make") == 2   # uma no local, uma aqui
    # Sem daemon, o cliente guarda sozinho, como antes do 6.1.2: a dica de recall continua valendo.
    assert (home / ".delegation_core" / "saidas.sqlite3").exists()


def test_daemon_que_cai_depois_de_rodar_nao_faz_o_comando_rodar_de_novo(falsos, monkeypatch, capsys, tmp_path):
    bindir, contador = falsos
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    chamadas = []

    def chamar(rota, corpo, tempo=0):
        chamadas.append(rota)
        if rota == "/api/saidas/plano":
            return servico.plano(corpo["comando"])
        return None   # o exibir falha: daemon caiu no meio

    monkeypatch.setattr(cliente_fino, "chamar", chamar)
    codigo = cliente_fino.shell("make all")
    fino = capsys.readouterr().out
    assert chamadas == ["/api/saidas/plano", "/api/saidas/exibir", "/api/saidas/guardar"]
    assert _execucoes(contador, "make") == 1
    local = _rodar(["shell", "make all"], _home(tmp_path, "local", None), bindir, sem_daemon=True)
    assert fino == local.stdout and codigo == local.returncode


def test_modo_local_volta_para_o_caminho_local_sem_rodar_nada(monkeypatch):
    """git, gh, ls, grep e wc consultam a ferramenta mais de uma vez: so rodam no processo do agente."""
    assert servico.plano("git status") == {"modo": "local"}
    monkeypatch.setattr(cliente_fino, "chamar", lambda rota, corpo, tempo=0: {"modo": "local"})
    rodou = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: rodou.append(a))
    assert cliente_fino.shell("git status") is None
    assert rodou == []


def test_muitos_clientes_ao_mesmo_tempo_nao_perdem_saida(daemon, tmp_path):
    from delegation_core import config
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for i in range(24):
        p = bindir / f"make{i}"
        p.write_text(f"#!/bin/sh\nfor j in $(seq 1 300); do echo \"cliente {i} linha $j\"; done\n")
        p.chmod(0o755)
    home = _home(tmp_path, "fino", daemon)
    # `make<i>` nao casa com filtro; usar make com argumento distinto mantem o filtro TOML e a guarda.
    fake = bindir / "make"
    fake.write_text("#!/bin/sh\nfor j in $(seq 1 300); do echo \"alvo $1 linha $j\"; done\n")
    fake.chmod(0o755)

    def um(i):
        return _rodar(["shell", f"make alvo{i}"], home, bindir, sem_daemon=False)

    with ThreadPoolExecutor(max_workers=12) as ex:
        res = list(ex.map(um, range(24)))
    assert all(r.returncode == 0 for r in res)
    assert not any("locked" in r.stderr.lower() or "Traceback" in r.stderr for r in res)
    assert all("recall" in r.stdout for r in res)
    assert _linhas_guardadas(Path(config.CONFIG_DIR)) == 24
    assert not (home / ".delegation_core" / "saidas.sqlite3").exists()


# ── recall e hook ─────────────────────────────────────────────────────────────

def test_recall_pelo_daemon_devolve_o_original(daemon, falsos, tmp_path):
    bindir, _ = falsos
    home = _home(tmp_path, "fino", daemon)
    r = _rodar(["shell", "make all"], home, bindir, sem_daemon=False)
    dica = [l for l in r.stdout.splitlines() if "recall" in l][-1]
    h = dica.split("recall ")[1].rstrip("]").split()[0]
    rec = _rodar(["recall", h], home, bindir, sem_daemon=False)
    assert rec.returncode == 0
    assert rec.stdout.count("gcc -c arquivo") == 400
    parte = _rodar(["recall", h, "--from", "799"], home, bindir, sem_daemon=False)
    assert parte.stdout.splitlines()[0].startswith("gcc -c arquivo400") or "arquivo400" in parte.stdout
    nada = _rodar(["recall", "000000000000"], home, bindir, sem_daemon=False)
    assert nada.returncode == 1 and "not found" in nada.stderr


@pytest.mark.parametrize("payload", [
    {"tool_name": "Bash", "tool_input": {"command": "make all"}},
    {"tool_name": "Bash", "tool_input": {"command": "make all | tail -3"}},
    {"tool_name": "Bash", "tool_input": {"command": "echo oi"}},
    {"tool_name": "Read", "tool_input": {"file_path": "/x"}},
    {"tool_name": "Bash", "tool_input": {"command": "delegation-core shell 'make'"}},
])
def test_hook_pelo_daemon_responde_o_mesmo_que_o_local(payload, daemon, tmp_path):
    entrada = json.dumps(payload)
    local = _rodar(["filters", "hook"], _home(tmp_path, "local", None), tmp_path, True, entrada)
    fino = _rodar(["filters", "hook"], _home(tmp_path, "fino", daemon), tmp_path, False, entrada)
    assert fino.stdout == local.stdout and fino.returncode == local.returncode == 0


def test_hook_com_entrada_quebrada_nao_derruba_nada(daemon, tmp_path):
    r = _rodar(["filters", "hook"], _home(tmp_path, "fino", daemon), tmp_path, False, "isto nao e json")
    assert r.returncode == 0 and r.stdout == ""


# ── workers do pool ───────────────────────────────────────────────────────────

def test_worker_do_pool_nao_grava_e_o_daemon_grava_ao_receber(monkeypatch):
    from delegation_core import config
    from delegation_core.compressao import pool
    from delegation_core.compressao.ccr import Guarda
    log = "\n".join(f"2026-11-23T10:00:{i % 60:02d}Z INFO servico ok passo={i}" for i in range(400))
    log += "\n2026-11-23T10:07:00Z ERROR falhou de verdade"
    volta = pool._trabalho(log, "journalctl", "log", 1.0, True, str(config.CONFIG_DIR))
    assert execucao._COLETOR is None, "o coletor tem que ser desligado ao sair do worker"
    pendentes = volta["ccr"]
    assert pendentes, "este log deveria acionar a guarda reversivel"
    chave, original = pendentes[0]
    assert Guarda().get(chave) is None, "o worker gravou por conta propria"
    monkeypatch.setattr(execucao, "_ESCRITOR", True)
    r = pool._gravar_do_worker(volta)
    assert r is volta["resultado"]
    assert Guarda().get(chave) == original


# ── o cliente HTTP e a entrada ────────────────────────────────────────────────

def _servidor_cru(resposta: bytes):
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)

    def atender():
        c, _ = s.accept()
        c.recv(65536)
        c.sendall(resposta)
        c.close()
        s.close()

    threading.Thread(target=atender, daemon=True).start()
    return s.getsockname()[1]


@pytest.mark.parametrize("resposta,esperado", [
    (b"HTTP/1.0 200 OK\r\nContent-Length: 10\r\n\r\n{\"a\": 1}  ", {"a": 1}),
    (b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\n{\"b\r\n5\r\n\": 2}\r\n0\r\n\r\n", {"b": 2}),
    (b"HTTP/1.0 200 OK\r\nContent-Length: 50\r\n\r\n{\"a\": 1}", None),     # cortada no meio
    (b"HTTP/1.0 401 Unauthorized\r\nContent-Length: 2\r\n\r\n{}", None),
    (b"HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\n[1]", None),            # nao e objeto
    (b"lixo sem cabecalho", None),
])
def test_cliente_http_so_aceita_resposta_inteira_e_200(resposta, esperado, monkeypatch, tmp_path):
    from delegation_core import config
    monkeypatch.delenv("DELEGATION_CORE_SEM_DAEMON", raising=False)
    porta = _servidor_cru(resposta)
    (Path(config.CONFIG_DIR) / "config.json").write_text(json.dumps({"dashboard_port": porta, "server_token": "t"}))
    assert cliente_fino.chamar("/x", {}) == esperado


def test_sem_token_ou_porta_nao_tenta_o_daemon(monkeypatch):
    from delegation_core import config
    monkeypatch.delenv("DELEGATION_CORE_SEM_DAEMON", raising=False)
    (Path(config.CONFIG_DIR) / "config.json").write_text(json.dumps({"dashboard_port": 8788, "server_token": ""}))
    assert cliente_fino._destino() is None
    (Path(config.CONFIG_DIR) / "config.json").write_text("{nao e json")
    assert cliente_fino._destino() is None


@pytest.mark.parametrize("argv,esperado", [
    (["recall", "abc123"], ("abc123", 0)),
    (["recall", "abc123", "--from", "7"], ("abc123", 7)),
    (["recall", "abc123", "--from=7"], ("abc123", 7)),
    (["recall"], None),
    (["recall", "--help"], None),
    (["recall", "abc", "--from", "x"], None),
    (["recall", "abc", "--outra"], None),
])
def test_formas_do_recall_que_a_entrada_rapida_atende(argv, esperado):
    assert entrada_rapida._recall_argv(argv) == esperado


@pytest.mark.parametrize("argv", [["shell", "--help"], ["shell"], ["filters", "list"], ["status"], ["recall"]])
def test_o_resto_vai_para_o_cli_de_sempre(argv, monkeypatch):
    import delegation_core.cli as cli
    monkeypatch.setattr(sys, "argv", ["delegation-core", *argv])
    monkeypatch.setattr(cli, "main", lambda: "cli")
    assert entrada_rapida.main() == "cli"


def test_guarda_feita_fora_do_daemon_vai_para_o_daemon(daemon, tmp_path):
    """O caminho `local` (git, gh, ls, grep, wc) roda no processo do agente e guarda o que corta:
    com o daemon no ar, a guarda e feita por ele, e o processo do agente nao abre o arquivo."""
    from delegation_core import config
    home = _home(tmp_path, "fino", daemon)
    codigo = ("import json; from delegation_core.filtros_saida import execucao; "
              "print(json.dumps(execucao.guardar('linha\\n' * 900, 'git log', 1, 1)))")
    env = {k: v for k, v in os.environ.items() if k != "DELEGATION_CORE_SEM_DAEMON"}
    env.update(HOME=str(home), USERPROFILE=str(home))
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, timeout=60)
    g = json.loads(r.stdout)
    assert g and len(g["hash"]) == 12
    assert not (home / ".delegation_core" / "saidas.sqlite3").exists()
    assert execucao.recuperar(g["hash"])["output"].count("linha") == 900
    assert _linhas_guardadas(Path(config.CONFIG_DIR)) == 1
