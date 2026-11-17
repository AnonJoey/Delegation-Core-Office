"""Instalador do delegation-core, o mesmo para Linux, macOS e Windows.

`install.sh` e `install.bat` so acham um Python 3.11+ e chamam este arquivo.
Tudo o mais acontece aqui: pacotes de sistema, venv, backup da instalacao
anterior, pip e o `post-install` do pacote.

So biblioteca padrao: roda ANTES do venv existir, com o Python do sistema, e
nao pode importar `delegation_core`.

Ate 06/10/2026 cada passo existia duas vezes, em bash e em batch, e as duas
metades tinham divergido: so o bash fazia backup da instalacao anterior, so o
batch avisava quando o `post-install` falhava, so o batch conferia o VC++ e so
o bash instalava os pacotes de compilacao da distribuicao.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

MIN_PYTHON = (3, 11)
CONFIG_DIR = Path.home() / ".delegation_core"
VENV = CONFIG_DIR / "venv"
RAIZ = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"

PACOTES_APT = ("python3-venv", "python3-dev", "build-essential")
PACOTES_DNF = ("python3-devel", "gcc", "gcc-c++", "make")
PACOTES_PACMAN = ("python", "base-devel")
CHAVES_VCREDIST = (r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64",
                   r"SOFTWARE\WOW6432Node\Microsoft\VisualStudio\14.0\VC\Runtimes\X64")


def _bin(nome: str, venv: Path = VENV) -> Path:
    return venv / ("Scripts" if WINDOWS else "bin") / (nome + (".exe" if WINDOWS else ""))


class Executor:
    """Roda comandos, ou so os anota com `--dry-run`. Os testes leem `feitos`."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.feitos: list[list[str]] = []

    def __call__(self, cmd: list, check: bool = True, quieto: bool = False) -> int:
        cmd = [str(c) for c in cmd]
        self.feitos.append(cmd)
        if self.dry_run:
            print("  [dry-run] " + " ".join(cmd))
            return 0
        saida = subprocess.DEVNULL if quieto else None
        r = subprocess.run(cmd, stdout=saida, stderr=saida)
        if check and r.returncode:
            raise SystemExit(f"\nERROR: failed ({r.returncode}): {' '.join(cmd)}\n")
        return r.returncode


# ── pacotes de sistema ───────────────────────────────────────────────────────

def faltando_apt(pacotes=PACOTES_APT) -> list[str]:
    return [p for p in pacotes
            if subprocess.run(["dpkg", "-s", p], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode]


def deps_linux(rodar: Executor) -> str:
    if shutil.which("apt-get"):
        falta = faltando_apt()
        if not falta:
            return "system packages OK"
        print(f"  Missing: {' '.join(falta)} (requires sudo)")
        rodar(["sudo", "apt-get", "install", "-y", *falta])
        return "installed: " + " ".join(falta)
    if shutil.which("dnf"):
        rodar(["sudo", "dnf", "install", "-y", *PACOTES_DNF], check=False)
        return "dnf: build dependencies"
    if shutil.which("pacman"):
        rodar(["sudo", "pacman", "-S", "--noconfirm", "--needed", *PACOTES_PACMAN], check=False)
        return "pacman: build dependencies"
    return ("unknown package manager: install python3-dev and build tools "
            "by hand if pip fails")


def deps_macos(rodar: Executor) -> str:
    if subprocess.run(["xcode-select", "-p"], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0:
        return "Xcode CLT OK"
    print("  Xcode Command Line Tools not found. Opening Apple's installer:")
    print("  click Install, then come back here.")
    rodar(["xcode-select", "--install"], check=False)
    if not rodar.dry_run:
        input("  Press Enter once the Xcode installer has finished: ")
    return "Xcode CLT installed"


def vcredist_presente() -> bool | None:
    try:
        import winreg
    except ImportError:
        return None
    for chave in CHAVES_VCREDIST:
        try:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave))
            return True
        except OSError:
            continue
    return False


def deps_sistema(rodar: Executor) -> str:
    sistema = platform.system()
    if sistema == "Linux":
        return deps_linux(rodar)
    if sistema == "Darwin":
        return deps_macos(rodar)
    if sistema == "Windows":
        return ("VC++ Redistributable OK" if vcredist_presente()
                else "VC++ Redistributable not detected (usually not required)")
    return f"{sistema}: no system packages checked"


# ── venv, backup e pip ───────────────────────────────────────────────────────

def pacote_instalado(venv: Path = VENV) -> Path | None:
    padroes = ("Lib/site-packages/delegation_core",) if WINDOWS else ("lib/python*/site-packages/delegation_core",)
    for padrao in padroes:
        for p in sorted(venv.glob(padrao)):
            if p.is_dir():
                return p
    return None


def backup_da_anterior(venv: Path = VENV, destino_base: Path = CONFIG_DIR,
                       dry_run: bool = False) -> Path | None:
    """Copia o pacote instalado e o dist-info antes do pip sobrescrever."""
    pacote = pacote_instalado(venv)
    if pacote is None:
        return None
    destino = destino_base / f"backups_pre_upgrade_{time.strftime('%Y%m%d_%H%M%S')}"
    if dry_run:
        return destino
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pacote, destino / pacote.name, dirs_exist_ok=True)
    for info in pacote.parent.glob("delegation_core-*.dist-info"):
        shutil.copytree(info, destino / info.name, dirs_exist_ok=True)
    return destino


def instalar(rodar: Executor, raiz: Path = RAIZ, venv: Path = VENV) -> None:
    pip = _bin("pip", venv)
    rodar([pip, "install", "--quiet", "--upgrade", "pip", "wheel", "setuptools<82"])
    if rodar([pip, "install", f"{raiz}[graph,web]"], check=False, quieto=True):
        print("  Extras [graph,web] failed; installing the package without them.")
        rodar([pip, "install", str(raiz)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install delegation-core on this computer.")
    ap.add_argument("--dry-run", action="store_true", help="print the steps without running them")
    ap.add_argument("--sem-pacotes-de-sistema", action="store_true",
                    help="skip apt/dnf/pacman/xcode")
    args = ap.parse_args(argv)

    if sys.version_info < MIN_PYTHON:
        print(f"ERROR: Python {'.'.join(map(str, MIN_PYTHON))}+ is required; this is {platform.python_version()}.")
        return 1
    rodar = Executor(args.dry_run)
    print(f"\n  delegation-core installer\n  {platform.system()} ({platform.machine()}), "
          f"Python {platform.python_version()} at {sys.executable}\n")

    if not args.sem_pacotes_de_sistema:
        print("System packages...")
        print("  " + deps_sistema(rodar) + "\n")

    print(f"Virtual environment at {VENV}...")
    rodar([sys.executable, "-m", "venv", VENV])
    bk = backup_da_anterior(dry_run=args.dry_run)
    if bk:
        print(f"  Existing install backed up to {bk}")
    print("\nInstalling delegation-core and its Python dependencies")
    print("  (sentence-transformers and chromadb are large: this may take a few minutes)")
    instalar(rodar)

    print("\nFinishing the install...")
    exe = _bin("delegation-core")
    codigo = rodar([exe, "post-install", "--root", RAIZ], check=False)
    if codigo:
        print(f"\nWARNING: the finishing step reported a problem (exit {codigo}). The package "
              f"is installed; rerun just that step with:\n  \"{exe}\" post-install --root \"{RAIZ}\"")
    return codigo


if __name__ == "__main__":
    raise SystemExit(main())
