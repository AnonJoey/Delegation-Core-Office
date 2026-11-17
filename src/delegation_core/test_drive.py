"""`delegation-core test-drive`: um daemon descartavel, isolado da instalacao real.

Trazido do `paperclipai test-drive`. Serve para experimentar uma versao, um
ajuste de config ou um cliente novo sem tocar no vault, no indice nem no
config.json de verdade.

Isolamento por HOME: `CONFIG_DIR` e `Path.home() / ".delegation_core"`, entao
o daemon filho, rodando com HOME (e USERPROFILE) apontando para um diretorio
temporario, nao tem como achar o estado real. O cache de modelos do Hugging
Face fica apontado para o real (HF_HOME), para nao baixar o BGE de novo.

Guardas, porque o ambiente de teste ja escreveu na producao uma vez por
symlink (27/09/2026):
- todo caminho e resolvido (`resolve()`) antes de comparar;
- o diretorio temporario e o vault de teste nao podem cair dentro do vault real
  nem do `~/.delegation_core` real;
- `--from` COPIA a pasta de origem; o daemon nunca aponta para ela.

Roda em modo `agent` (sem llama.cpp) e sem painel nem agenda.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

PASTAS = ["Decisions", "Fixes", "Reference", "Sessions", "Projects"]

AMOSTRAS = {
    "Decisions/2026-01-01-Exemplo de decisao.md":
        "---\ntitle: Exemplo de decisao\n---\n\n## Decisao\nUsar o canal stable no test-drive.\n",
    "Fixes/2026-01-02-Exemplo de correcao.md":
        "---\ntitle: Exemplo de correcao\n---\n\n## Problema\nPorta ocupada.\n\n## Correcao\nOutra porta.\n",
}


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _dentro(filho: Path, pai: Path) -> bool:
    try:
        filho.resolve().relative_to(pai.resolve())
        return True
    except ValueError:
        return False


def preparar(base: Path | None = None, origem: Path | None = None, porta: int = 0) -> dict:
    from . import config
    real_dir = config.CONFIG_DIR
    real_vault = None
    try:
        v = config.Config.load().vault_path
        real_vault = Path(v) if v else None
    except Exception:  # noqa: BLE001
        pass

    home = Path(base or tempfile.mkdtemp(prefix="dc-test-drive-")).resolve()
    for proibido in filter(None, (real_dir, real_vault)):
        if _dentro(home, proibido) or _dentro(proibido, home):
            raise ValueError(f"test-drive directory {home} overlaps the real install at {proibido.resolve()}")

    vault = home / "vault"
    if origem is not None:
        origem = Path(origem).expanduser()
        if not origem.is_dir():
            raise ValueError(f"--from {origem} is not a directory")
        shutil.copytree(origem, vault, symlinks=False, ignore=shutil.ignore_patterns(".chroma*", ".historico", ".lixeira"))
    else:
        for rel, texto in AMOSTRAS.items():
            p = vault / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(texto, encoding="utf-8")
    for pasta in PASTAS:
        (vault / pasta).mkdir(parents=True, exist_ok=True)
    if real_vault is not None and _dentro(vault, real_vault):
        raise ValueError("test vault resolves into the real vault")

    porta = porta or porta_livre()
    token = secrets.token_urlsafe(24)
    cfg_dir = home / ".delegation_core"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    dados = {
        "vault_path": str(vault), "vault_folders": sorted({*PASTAS, *(p.name for p in vault.iterdir() if p.is_dir() and not p.name.startswith("."))}),
        "engine_mode": "agent", "server_host": "127.0.0.1", "server_port": porta,
        "server_token": token, "dashboard_port": 0, "agenda_enabled": False,
        # CPU: o daemon real ja ocupa a GPU com o BGE e o llama-server.
        "embed_device": "cpu",
    }
    arq = cfg_dir / "config.json"
    arq.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    arq.chmod(0o600)

    env = dict(os.environ)
    hf = env.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    env.update({"HOME": str(home), "USERPROFILE": str(home), "HF_HOME": hf,
                "FASTMCP_DISABLE_UPDATE_CHECK": "1"})
    return {"home": str(home), "vault": str(vault), "config": str(arq), "port": porta,
            "url": f"http://127.0.0.1:{porta}/mcp", "token": token, "env": env}


def cmd_test_drive(args) -> int:
    try:
        r = preparar(Path(args.dir) if args.dir else None,
                     Path(args.source) if args.source else None, args.port)
    except ValueError as e:
        print(f"refused: {e}")
        return 1
    print(f"test-drive home: {r['home']}\nvault:  {r['vault']}\nurl:    {r['url']}")
    print(f"header: Authorization: Bearer {r['token']}")
    if args.prepare_only:
        print(f"prepared only. Start with: HOME={r['home']} {sys.executable} -m delegation_core run")
        return 0
    print("starting the daemon (Ctrl-C stops it)...")
    try:
        return subprocess.call([sys.executable, "-m", "delegation_core", "run"], env=r["env"])
    except KeyboardInterrupt:
        return 0
    finally:
        if not args.keep:
            shutil.rmtree(r["home"], ignore_errors=True)
            print(f"removed {r['home']}")


def registrar(sub) -> dict:
    p = sub.add_parser("test-drive", help="Throwaway daemon with its own HOME, vault and port")
    p.add_argument("--from", dest="source", default="", help="copy this folder in as the test vault")
    p.add_argument("--dir", default="", help="use this directory instead of a new temp dir")
    p.add_argument("--port", type=int, default=0, help="port for the throwaway daemon (0 = a free one)")
    p.add_argument("--keep", action="store_true", help="keep the directory after it stops")
    p.add_argument("--prepare-only", action="store_true", help="set it up and print how to start it, without starting it")
    return {"test-drive": cmd_test_drive}
