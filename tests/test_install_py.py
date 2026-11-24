"""install.py: o bootstrap unico das tres plataformas, sem rodar nada de verdade."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _modulo():
    spec = importlib.util.spec_from_file_location("install_boot", RAIZ / "install.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_so_biblioteca_padrao():
    """Roda antes do venv: importar o pacote ou terceiros quebraria a 1a instalacao."""
    texto = (RAIZ / "install.py").read_text(encoding="utf-8")
    for proibido in ("import delegation_core", "from delegation_core", "import requests", "import rich"):
        assert proibido not in texto


def test_dry_run_na_ordem_certa(tmp_path, monkeypatch):
    m = _modulo()
    monkeypatch.setattr(m, "VENV", tmp_path / "venv")
    monkeypatch.setattr(m, "CONFIG_DIR", tmp_path)
    feitos = []
    original = m.Executor.__call__

    def anota(self, cmd, check=True, quieto=False):
        r = original(self, cmd, check, quieto)
        feitos.append([str(c) for c in cmd])
        return r
    monkeypatch.setattr(m.Executor, "__call__", anota)
    assert m.main(["--dry-run", "--sem-pacotes-de-sistema"]) == 0
    assert feitos[0][1:3] == ["-m", "venv"]
    assert feitos[1][-3:] == ["pip", "wheel", "setuptools<82"]
    # `python -m pip`, nunca `pip.exe`: no Windows o pip.exe nao se substitui
    # enquanto roda, e o upgrade do proprio pip falhava (23/11/2026, v0.17.0).
    assert Path(feitos[1][0]).stem == "python" and feitos[1][1:3] == ["-m", "pip"]
    assert feitos[2][1:3] == ["-m", "pip"]
    assert feitos[2][-1].endswith("[graph,web]")
    assert feitos[3][-3:] == ["post-install", "--root", str(RAIZ)]


def test_extras_que_falham_caem_para_o_pacote_puro(tmp_path):
    m = _modulo()

    class Falso(m.Executor):
        def __call__(self, cmd, check=True, quieto=False):
            cmd = [str(c) for c in cmd]
            self.feitos.append(cmd)
            return 1 if cmd[-1].endswith("[graph,web]") else 0
    r = Falso()
    m.instalar(r, raiz=tmp_path, venv=tmp_path / "v")
    assert r.feitos[-1][-1] == str(tmp_path)


def test_pip_sempre_pelo_python_do_venv(tmp_path):
    """No Windows o pip.exe nao se atualiza ("To modify pip, please run ... -m pip"): a
    instalacao nova parava no primeiro passo. Todo pip passa por `python -m pip`."""
    m = _modulo()

    class Anota(m.Executor):
        def __call__(self, cmd, check=True, quieto=False):
            self.feitos.append([str(c) for c in cmd])
            return 1 if str(cmd[-1]).endswith("[graph,web]") else 0
    r = Anota()
    m.instalar(r, raiz=tmp_path, venv=tmp_path / "v")
    assert len(r.feitos) == 3
    for cmd in r.feitos:
        assert Path(cmd[0]).stem == "python" and cmd[1:3] == ["-m", "pip"], cmd


def test_post_install_que_falha_devolve_o_codigo(tmp_path, monkeypatch, capsys):
    m = _modulo()
    monkeypatch.setattr(m, "VENV", tmp_path / "venv")
    monkeypatch.setattr(m, "backup_da_anterior", lambda **k: None)

    def falso(self, cmd, check=True, quieto=False):
        return 3 if "post-install" in [str(c) for c in cmd] else 0
    monkeypatch.setattr(m.Executor, "__call__", falso)
    assert m.main(["--sem-pacotes-de-sistema"]) == 3
    assert "rerun just that step" in capsys.readouterr().out


def test_backup_copia_pacote_e_dist_info(tmp_path, monkeypatch):
    m = _modulo()
    monkeypatch.setattr(m, "WINDOWS", False)
    site = tmp_path / "venv" / "lib" / "python3.12" / "site-packages"
    (site / "delegation_core").mkdir(parents=True)
    (site / "delegation_core" / "server.py").write_text("x")
    (site / "delegation_core-0.15.0.dist-info").mkdir()
    destino = m.backup_da_anterior(tmp_path / "venv", tmp_path)
    assert (destino / "delegation_core" / "server.py").read_text() == "x"
    assert (destino / "delegation_core-0.15.0.dist-info").is_dir()


def test_sem_instalacao_anterior_nao_ha_backup(tmp_path):
    assert _modulo().backup_da_anterior(tmp_path / "venv", tmp_path) is None


def test_apt_pede_so_o_que_falta(monkeypatch):
    m = _modulo()
    monkeypatch.setattr(m.shutil, "which", lambda c: "/usr/bin/apt-get" if c == "apt-get" else None)
    monkeypatch.setattr(m, "faltando_apt", lambda pacotes=m.PACOTES_APT: ["python3-dev"])
    r = m.Executor(dry_run=True)
    m.deps_linux(r)
    assert r.feitos == [["sudo", "apt-get", "install", "-y", "python3-dev"]]


@pytest.mark.skipif(sys.platform == "win32", reason="shim de bash")
def test_o_shim_de_bash_entrega_os_argumentos_ao_install_py():
    r = subprocess.run(["bash", str(RAIZ / "install.sh"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--dry-run" in r.stdout


@pytest.mark.parametrize("winget,depois,instalou", [(True, True, True), (False, False, False), (True, False, False)])
def test_windows_sem_vcredist_instala_pelo_winget(monkeypatch, capsys, winget, depois, instalou):
    """Num Windows limpo o torch morria no post-install (WinError 126, c10.dll) sem o VC++."""
    m = _modulo()
    estados = iter([False, depois])
    monkeypatch.setattr(m, "vcredist_presente", lambda: next(estados))
    monkeypatch.setattr(m.shutil, "which", lambda nome: "C:/winget.exe" if winget and nome == "winget" else None)

    class Anota(m.Executor):
        def __call__(self, cmd, check=True, quieto=False):
            self.feitos.append([str(c) for c in cmd])
            return 0
    r = Anota()
    msg = m.deps_windows(r)
    assert bool(r.feitos and r.feitos[0][:4] == ["winget", "install", "--id", m.VCREDIST_WINGET]) == winget
    assert ("installed" in msg and "MISSING" not in msg) == instalou
    if not instalou:
        assert m.VCREDIST_URL in capsys.readouterr().out
