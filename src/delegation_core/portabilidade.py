"""Exportar e importar uma instalacao, e backup com rotacao.

Trazido do Paperclip (`company export/import` e `db-backup`). A troca de
computador de um colega em 28 e 29/09 foi feita a mao, arquivo por arquivo;
este modulo e esse roteiro em codigo.

## O que vai no pacote (um .zip)

- `config.json` **sem segredo**: `server_token` e `client_tokens` saem vazios, e
  qualquer chave com cara de segredo tambem. A maquina nova gera o proprio token.
- Os estados pequenos que nao se reconstroem do vault: registro de ingestao, de
  grafos, processos, workspaces, calibracao, afericao de busca, consultas de
  avaliacao, cartoes de status. Lista em `ESTADOS`.
- `manifest.json` com versao, data, caminhos de origem e o sha256 de cada arquivo.

## O que NAO vai

O indice (ChromaDB): se reconstroi das fontes, como a recuperacao de indice ja
faz. Os modelos: se baixam de novo. O vault: e Markdown, copia-se como pasta
(ou `--with-vault`, que o poe no pacote).

## Importar

Sem `--apply`, so mostra o plano. Com `--apply`, todo arquivo que ja existe no
destino vai antes para `import_backup/<data>/`: importar nunca apaga estado.
`--map ANTIGO=NOVO` troca prefixo de caminho no config e nos registros.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

#: Estados pequenos, relativos a CONFIG_DIR. Arquivo que nao existir e pulado.
ESTADOS = (
    "ingested_sources.json",
    "graphs_registry.json",
    "processes.json",
    "mcp_workspaces.json",
    "calibracao.json",
    "afericao_busca.json",
    "job_durations.json",
    "status_cards.json",
    "open_questions.json",
    "avaliacao/consultas.json",
)

def _cfg_dir() -> Path:
    from . import config
    return config.CONFIG_DIR


def limpar_config(dados: dict) -> tuple[dict, list[str]]:
    """Config sem segredo, e a lista das chaves esvaziadas."""
    from .revisoes_config import chave_secreta
    saida, tiradas = {}, []
    for k, v in dados.items():
        if chave_secreta(k) and v not in ("", None, {}, []):
            saida[k] = type(v)() if isinstance(v, (str, dict, list)) else None
            tiradas.append(k)
        else:
            saida[k] = v
    return saida, tiradas


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def exportar(destino: Path, com_vault: bool = False) -> dict:
    from . import __version__, config
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    base = _cfg_dir()
    arquivos: dict[str, bytes] = {}
    tiradas: list[str] = []
    cfg_dados = {}
    if config.CONFIG_FILE.is_file():
        cfg_dados = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
        limpo, tiradas = limpar_config(cfg_dados)
        arquivos["config.json"] = json.dumps(limpo, indent=2).encode("utf-8")
    for rel in ESTADOS:
        p = base / rel
        if p.is_file():
            arquivos[f"state/{rel}"] = p.read_bytes()
    vault_n = 0
    vault = Path(cfg_dados.get("vault_path") or "")
    if com_vault and vault.is_dir():
        for p in sorted(vault.rglob("*.md")):
            rel = p.relative_to(vault)
            if any(parte.startswith(".") for parte in rel.parts):
                continue
            arquivos[f"vault/{rel.as_posix()}"] = p.read_bytes()
            vault_n += 1
    manifesto = {
        "format": "delegation-core-export/1",
        "version": __version__,
        "created": datetime.now().isoformat(timespec="seconds"),
        "source_config_dir": str(base),
        "source_vault": str(vault) if vault else "",
        "scrubbed_keys": tiradas,
        "files": {nome: _sha(b) for nome, b in arquivos.items()},
    }
    tmp = destino.with_suffix(destino.suffix + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifesto, indent=2))
        for nome, b in arquivos.items():
            z.writestr(nome, b)
    tmp.replace(destino)
    return {"path": str(destino), "files": len(arquivos), "vault_notes": vault_n,
            "scrubbed_keys": tiradas, "bytes": destino.stat().st_size}


def _trocar(valor, mapa: list[tuple[str, str]]):
    if isinstance(valor, str):
        for antigo, novo in mapa:
            if valor == antigo or valor.startswith(antigo.rstrip("/\\") + "/") or valor.startswith(antigo.rstrip("/\\") + "\\"):
                return novo + valor[len(antigo):]
        return valor
    if isinstance(valor, dict):
        return {_trocar(k, mapa): _trocar(v, mapa) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_trocar(v, mapa) for v in valor]
    return valor


def ler_pacote(origem: Path) -> tuple[dict, dict[str, bytes]]:
    """Manifesto e arquivos, conferindo o sha256 de cada um."""
    with zipfile.ZipFile(origem) as z:
        manifesto = json.loads(z.read("manifest.json"))
        if manifesto.get("format") != "delegation-core-export/1":
            raise ValueError(f"not a delegation-core export: {manifesto.get('format')!r}")
        arquivos = {}
        for nome, sha in manifesto["files"].items():
            if ".." in Path(nome).parts or Path(nome).is_absolute():
                raise ValueError(f"unsafe path in package: {nome}")
            b = z.read(nome)
            if _sha(b) != sha:
                raise ValueError(f"checksum mismatch for {nome}: the package is damaged")
            arquivos[nome] = b
    return manifesto, arquivos


def importar(origem: Path, mapa: list[tuple[str, str]] | None = None, aplicar: bool = False,
             vault_destino: Path | None = None) -> dict:
    from . import config
    manifesto, arquivos = ler_pacote(Path(origem))
    mapa = list(mapa or [])
    base = _cfg_dir()
    plano = []
    conteudo: dict[Path, bytes] = {}

    for nome, b in arquivos.items():
        if nome == "config.json":
            novo = _trocar(json.loads(b), mapa)
            if config.CONFIG_FILE.is_file():
                atual = json.loads(config.CONFIG_FILE.read_text(encoding="utf-8"))
                for k in ("server_token", "client_tokens"):
                    if atual.get(k):
                        novo[k] = atual[k]  # o segredo desta maquina fica
            conteudo[config.CONFIG_FILE] = json.dumps(novo, indent=2).encode("utf-8")
        elif nome.startswith("state/"):
            rel = nome[len("state/"):]
            texto = b
            if rel.endswith(".json") and mapa:
                try:
                    texto = json.dumps(_trocar(json.loads(b), mapa), indent=2).encode("utf-8")
                except ValueError:
                    pass
            conteudo[base / rel] = texto
        elif nome.startswith("vault/"):
            if vault_destino is None:
                continue
            conteudo[Path(vault_destino) / nome[len("vault/"):]] = b

    for alvo, b in sorted(conteudo.items()):
        plano.append({"target": str(alvo), "action": "replace" if alvo.exists() else "create",
                      "bytes": len(b)})

    resultado = {"manifest": {k: manifesto[k] for k in ("version", "created", "source_vault", "scrubbed_keys")},
                 "plan": plano, "applied": False, "backup_dir": ""}
    if not aplicar:
        return resultado

    backup = base / "import_backup" / datetime.now().strftime("%Y%m%dT%H%M%S")
    for alvo, b in conteudo.items():
        if alvo.exists():
            try:
                rel = alvo.relative_to(base)
            except ValueError:
                rel = Path("vault") / alvo.name
            copia = backup / rel
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(alvo, copia)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        tmp = alvo.with_name(alvo.name + ".import.tmp")
        tmp.write_bytes(b)
        if alvo == config.CONFIG_FILE:
            tmp.chmod(0o600)
        tmp.replace(alvo)
    resultado["applied"] = True
    resultado["backup_dir"] = str(backup) if backup.exists() else ""
    return resultado


# ── backup com rotacao ───────────────────────────────────────────────────────

def _dir_backups() -> Path:
    return _cfg_dir() / "backups"


def backup(manter: int = 10) -> dict:
    """Um export em backups/, e so os `manter` mais novos ficam."""
    d = _dir_backups()
    nome = d / f"backup-{datetime.now().strftime('%Y%m%dT%H%M%S%f')}.zip"
    r = exportar(nome)
    removidos = []
    for velho in sorted(d.glob("backup-*.zip"), reverse=True)[max(1, manter):]:
        velho.unlink(missing_ok=True)
        removidos.append(velho.name)
    r["removed"] = removidos
    return r


def estado_backups() -> dict:
    d = _dir_backups()
    todos = sorted(d.glob("backup-*.zip"), reverse=True) if d.is_dir() else []
    if not todos:
        return {"count": 0, "newest": "", "age_days": None}
    novo = todos[0]
    idade = (datetime.now() - datetime.fromtimestamp(novo.stat().st_mtime)).total_seconds() / 86400
    return {"count": len(todos), "newest": novo.name, "age_days": round(idade, 1)}


# ── CLI ──────────────────────────────────────────────────────────────────────

def cmd_export(args) -> int:
    r = exportar(Path(args.path).expanduser(), com_vault=args.with_vault)
    print(f"exported {r['files']} files ({r['bytes']} bytes) to {r['path']}")
    if r["scrubbed_keys"]:
        print(f"secrets left out: {', '.join(r['scrubbed_keys'])}")
    return 0


def cmd_import(args) -> int:
    mapa = []
    for m in args.map or []:
        if "=" not in m:
            print(f"--map needs OLD=NEW, got {m!r}")
            return 1
        a, b = m.split("=", 1)
        mapa.append((a, b))
    try:
        r = importar(Path(args.path).expanduser(), mapa, aplicar=args.apply,
                     vault_destino=Path(args.vault).expanduser() if args.vault else None)
    except (ValueError, KeyError, zipfile.BadZipFile) as e:
        print(f"cannot import: {e}")
        return 1
    m = r["manifest"]
    print(f"package from v{m['version']}, created {m['created']}, vault {m['source_vault'] or '?'}")
    for p in r["plan"]:
        print(f"  {p['action']:8} {p['target']}")
    if r["applied"]:
        print("applied." + (f" Previous files kept in {r['backup_dir']}" if r["backup_dir"] else ""))
        print("Run `delegation-core reindex` so the index matches the imported state.")
    else:
        print("dry run: nothing written. Repeat with --apply.")
    return 0


def cmd_backup(args) -> int:
    if args.status:
        print(json.dumps(estado_backups()))
        return 0
    r = backup(args.keep)
    print(f"backup written: {r['path']} ({r['files']} files)")
    if r["removed"]:
        print(f"rotated out: {', '.join(r['removed'])}")
    return 0


def registrar(sub) -> dict:
    p = sub.add_parser("export", help="Export config (no secrets) and state to a .zip")
    p.add_argument("path")
    p.add_argument("--with-vault", action="store_true", help="also pack the vault's markdown")
    p = sub.add_parser("import", help="Import an export .zip (dry run unless --apply)")
    p.add_argument("path")
    p.add_argument("--map", action="append", help="OLD=NEW path prefix rewrite, repeatable")
    p.add_argument("--vault", default="", help="where to unpack vault notes, if the package has them")
    p.add_argument("--apply", action="store_true")
    p = sub.add_parser("backup", help="Rotating local backup of config and state")
    p.add_argument("--keep", type=int, default=10)
    p.add_argument("--status", action="store_true")
    return {"export": cmd_export, "import": cmd_import, "backup": cmd_backup}
