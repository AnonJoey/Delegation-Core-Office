"""No Windows, o delegation-core nao pode abrir (nem deixar aberta) uma janela de console.

Um programa de console lancado por um processo SEM console (o daemon sem janela, o
dashboard, os hooks) ganha um console novo e visivel, mesmo com a saida capturada.
`procs.sem_janela()` pede um console oculto; esta guarda exige que toda chamada de
`subprocess` do pacote seja marcada ou esteja numa lista de excecoes com o motivo, para
que a proxima chamada nao reabra o problema.
"""
from __future__ import annotations

import ast
import contextlib
import logging
import sys
from pathlib import Path

import pytest

from delegation_core import config, procs, service, stdio_nulo

SRC = Path(__file__).resolve().parents[1] / "src" / "delegation_core"
FUNCOES = {"run", "Popen", "check_output", "check_call", "call"}
APELIDOS = {"subprocess", "_sp"}

# (arquivo, funcao) -> motivo. So ramos que nao existem no Windows e escrevem no
# terminal do usuario: sem console, a saida do filho nao teria para onde ir.
EXCECOES = {
    ("wizard.py", "_startup_systemd"): "systemctl, so Linux",
    ("wizard.py", "_startup_launchd"): "launchctl, so macOS",
    ("wizard.py", "_install_linux_packages"): "apt, so Linux, mostra o progresso ao usuario",
    ("wizard.py", "_step_mlx"): "pip do motor MLX, so macOS, mostra o progresso ao usuario",
}


def _chamadas_de_processo():
    for caminho in sorted(SRC.rglob("*.py")):
        rel = caminho.relative_to(SRC)
        if rel.parts[0] == "hooks":     # stdlib-only, com as proprias flags (testado abaixo)
            continue
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        funcao_de = {}
        for fn in ast.walk(arvore):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for n in ast.walk(fn):
                    funcao_de.setdefault(id(n), fn.name)
        for n in ast.walk(arvore):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id in APELIDOS and n.func.attr in FUNCOES):
                yield rel, caminho.name, funcao_de.get(id(n), "<modulo>"), n


def _marcada(chamada: ast.Call) -> bool:
    for k in chamada.keywords:
        if k.arg in ("creationflags", "start_new_session"):
            return True
        if k.arg is None and isinstance(k.value, ast.Call):
            nome = ast.unparse(k.value.func)
            if nome == "sem_janela" or "detached" in nome.lower():
                return True
    return False


def test_toda_chamada_de_subprocess_do_pacote_esta_marcada_ou_e_excecao_documentada():
    soltas = [f"{rel}:{n.lineno} em {fn}()"
              for rel, nome, fn, n in _chamadas_de_processo()
              if not _marcada(n) and (nome, fn) not in EXCECOES]
    assert not soltas, (
        "chamada de subprocess sem `**sem_janela()`: no Windows ela abre um console visivel "
        "quando o processo pai nao tem console. Marque a chamada ou, se ela so existe em "
        "Linux/macOS, acrescente em EXCECOES com o motivo:\n  " + "\n  ".join(soltas))


def test_ninguem_importa_run_ou_popen_direto_do_subprocess():
    """`from subprocess import run` escaparia da guarda acima, que procura `subprocess.run`."""
    achados = []
    for caminho in sorted(SRC.rglob("*.py")):
        if caminho.relative_to(SRC).parts[0] == "hooks":
            continue
        for n in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom) and n.module == "subprocess":
                nomes = {a.name for a in n.names} & (FUNCOES | {"getoutput", "getstatusoutput"})
                if nomes:
                    achados.append(f"{caminho.name}:{n.lineno} importa {sorted(nomes)}")
    assert not achados, achados


def test_ninguem_usa_os_system_ou_os_popen():
    achados = []
    for caminho in sorted(SRC.rglob("*.py")):
        if caminho.relative_to(SRC).parts[0] == "hooks":
            continue
        for n in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name) and n.func.value.id == "os"
                    and n.func.attr in ("system", "popen", "startfile")):
                achados.append(f"{caminho.name}:{n.lineno} os.{n.func.attr}")
    assert not achados, achados


def test_os_hooks_continuam_desacoplados_do_console():
    """Os hooks nao importam o pacote (stdlib only); a flag de cada um e a deles."""
    for nome in ("session_export.py", "session_start_brief.py"):
        texto = (SRC / "hooks" / nome).read_text(encoding="utf-8")
        assert "DETACHED_PROCESS" in texto, nome


# ── o helper ─────────────────────────────────────────────────────────────────

def test_fora_do_windows_sem_janela_nao_muda_nada(monkeypatch):
    monkeypatch.setattr(procs, "_e_windows", lambda: False)
    assert procs.sem_janela() == {}
    assert procs.sem_janela(capture_output=True) == {"capture_output": True}


def test_no_windows_sem_janela_acrescenta_o_flag_e_preserva_o_que_ja_havia(monkeypatch):
    monkeypatch.setattr(procs, "_e_windows", lambda: True)
    assert procs.sem_janela() == {"creationflags": procs.CREATE_NO_WINDOW}
    assert procs.CREATE_NO_WINDOW == 0x08000000
    assert procs.sem_janela(creationflags=0x200) == {"creationflags": 0x200 | 0x08000000}


# ── o daemon e o launcher do Windows ─────────────────────────────────────────

@pytest.fixture
def venv_windows(tmp_path, monkeypatch):
    """Uma pasta Scripts com python.exe e pythonw.exe, como a do venv."""
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    (scripts / "python.exe").write_text("")
    (scripts / "pythonw.exe").write_text("")
    monkeypatch.setattr(service.sys, "executable", str(scripts / "python.exe"))
    return scripts


def test_o_daemon_do_windows_usa_pythonw_quando_existe(venv_windows):
    comando = service._windows_run_command()
    assert comando == f'"{venv_windows / "pythonw.exe"}" -m delegation_core run'


def test_sem_pythonw_ou_com_visible_o_daemon_usa_python_e_a_janela_continua(venv_windows):
    assert service._windows_run_command(visible=True).startswith(f'"{venv_windows / "python.exe"}"')
    (venv_windows / "pythonw.exe").unlink()
    assert service._windows_run_command().startswith(f'"{venv_windows / "python.exe"}"')


def test_o_launcher_do_startup_so_dispara_o_daemon_e_fecha(venv_windows):
    """Com pythonw o .cmd termina na hora: a janela dele nao fica aberta com o daemon."""
    texto = service._windows_launcher_text()
    assert texto.startswith("@echo off\r\n")
    assert f'start "" "{venv_windows / "pythonw.exe"}" -m delegation_core run' in texto


def test_o_launcher_visible_roda_o_python_em_primeiro_plano(venv_windows):
    texto = service._windows_launcher_text(visible=True)
    assert "start" not in texto
    assert f'"{venv_windows / "python.exe"}" -m delegation_core run' in texto


def _instalar_no_windows(monkeypatch, tmp_path, tarefa_ok: bool, **kw):
    monkeypatch.setattr(service.platform, "system", lambda: "Windows")
    monkeypatch.setattr(service, "WIN_STARTUP_DIR", tmp_path / "startup")
    monkeypatch.setattr(service, "WIN_STARTUP_CMD", tmp_path / "startup" / "delegation-core.cmd")
    monkeypatch.setattr(service, "WIN_STARTUP_VBS", tmp_path / "startup" / "delegation-core.vbs")
    chamadas = []
    monkeypatch.setattr(service, "_run",
                        lambda cmd, timeout=30: (chamadas.append(cmd), (0, "") if tarefa_ok else (1, "denied"))[1])
    return service.install(**kw), chamadas


def test_a_tarefa_agendada_do_windows_roda_o_pythonw(venv_windows, monkeypatch, tmp_path):
    r, chamadas = _instalar_no_windows(monkeypatch, tmp_path, tarefa_ok=True)
    assert r["status"] == "installed"
    assert str(venv_windows / "pythonw.exe") in chamadas[0][chamadas[0].index("/TR") + 1]


def test_o_atalho_da_pasta_startup_usa_start_e_diz_que_nao_tem_janela(venv_windows, monkeypatch, tmp_path):
    r, _ = _instalar_no_windows(monkeypatch, tmp_path, tarefa_ok=False)
    assert r["status"] == "installed"
    assert "without a console window" in r["hint"]
    assert 'start ""' in service.WIN_STARTUP_CMD.read_text(encoding="utf-8")


def test_install_visible_mantem_a_janela_para_diagnostico(venv_windows, monkeypatch, tmp_path):
    r, _ = _instalar_no_windows(monkeypatch, tmp_path, tarefa_ok=False, visible=True)
    assert "visible" in r["hint"]
    assert "pythonw" not in service.WIN_STARTUP_CMD.read_text(encoding="utf-8")


def test_abrir_o_launcher_nao_abre_console_novo(monkeypatch, tmp_path):
    """Era `cmd /c start "" <launcher>`: o `start` abre um console novo para o .cmd."""
    monkeypatch.setattr(procs, "_e_windows", lambda: True)
    visto = {}
    monkeypatch.setattr(service.subprocess, "Popen",
                        lambda cmd, **kw: visto.update(cmd=cmd, kw=kw))
    service._abrir_launcher(tmp_path / "delegation-core.cmd")
    assert visto["cmd"] == ["cmd", "/c", str(tmp_path / "delegation-core.cmd")]
    assert "start" not in visto["cmd"]
    assert visto["kw"]["creationflags"] & procs.CREATE_NO_WINDOW


# ── stdout e stderr nulos (pythonw) ──────────────────────────────────────────

@contextlib.contextmanager
def _processo_sem_stdio(estado):
    """O estado de um processo do pythonw.exe: nada de stdin, stdout e stderr.

    Dentro do corpo do teste e com um MonkeyPatch proprio: a captura de saida do pytest
    reatribui sys.stdout/sys.stderr a cada fase, entao um None posto numa fixture de
    setup e sobrescrito antes de o teste rodar.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(config, "CONFIG_DIR", estado)
        for nome in ("stdin", "stdout", "stderr"):
            mp.setattr(sys, nome, None)
        try:
            yield
        finally:
            for fluxo in (sys.stdin, sys.stdout, sys.stderr):
                if fluxo is not None and hasattr(fluxo, "close"):
                    fluxo.close()


def test_garantir_stdio_da_destino_a_stdin_stdout_e_stderr_nulos(tmp_path):
    with _processo_sem_stdio(tmp_path / "estado"):
        stdio_nulo.garantir_stdio()
        assert sys.stdin is not None and sys.stdout is not None and sys.stderr is not None
        assert sys.stdout.isatty() is False   # o que o uvicorn pergunta ao montar o log
        print("sai pelo nulo")
        sys.stderr.write("traceback que antes sumia\n")
        sys.stderr.flush()
        escrito = (tmp_path / "estado" / "daemon-stderr.log").read_text(encoding="utf-8")
    assert "traceback que antes sumia" in escrito


def test_o_stdout_de_fallback_nao_e_um_terminal_em_plataforma_nenhuma():
    """`open(os.devnull).isatty()` e True no Windows (NUL e um dispositivo de caracteres,
    medido no CI com Python 3.12): o uvicorn ligaria as cores. O sorvedouro nosso diz False."""
    nulo = stdio_nulo._Nulo()
    assert nulo.isatty() is False
    assert nulo.write("abc") == 3
    nulo.flush()
    nulo.close()


def test_garantir_stdio_nao_mexe_em_quem_ja_tem_terminal():
    out, err = sys.stdout, sys.stderr
    stdio_nulo.garantir_stdio()
    assert sys.stdout is out and sys.stderr is err


def test_o_log_de_stderr_tem_teto_e_o_anterior_vira_ponto_um(tmp_path):
    arquivo = stdio_nulo._ArquivoComTeto(tmp_path / "daemon-stderr.log", limite=100)
    try:
        for i in range(20):
            arquivo.write(f"linha {i:02d} " + "x" * 20 + "\n")
        arquivo.flush()
        atual = tmp_path / "daemon-stderr.log"
        assert atual.stat().st_size <= 100
        assert (tmp_path / "daemon-stderr.log.1").exists()
        assert "linha 19" in atual.read_text(encoding="utf-8")   # o mais novo nunca se perde
    finally:
        arquivo.close()


def test_o_stderr_de_fallback_serve_ao_logging(tmp_path):
    """O daemon monta `logging.StreamHandler(sys.stderr)`; precisa aceitar o objeto."""
    log = logging.getLogger("teste-stdio-nulo")
    with _processo_sem_stdio(tmp_path / "estado"):
        stdio_nulo.garantir_stdio()
        manipulador = logging.StreamHandler(sys.stderr)
        log.addHandler(manipulador)
        try:
            log.error("erro do daemon sem console")
            manipulador.flush()
        finally:
            log.removeHandler(manipulador)
        escrito = (tmp_path / "estado" / "daemon-stderr.log").read_text(encoding="utf-8")
    assert "erro do daemon sem console" in escrito
