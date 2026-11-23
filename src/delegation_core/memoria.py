"""Operacoes de memoria trazidas do Paperclip: proveniencia, concorrencia otimista,
esquecer, corrigir e propor edicao.

O plano de memoria do Paperclip (`MemoryAdapter`) separa capturar, corrigir e
esquecer, registra quem escreveu e da a agente de baixa confianca o caminho de
PROPOR em vez de editar. Aqui, sobre o vault de Markdown:

- **Proveniencia**: `write_note` grava `written_by: <cliente>` no frontmatter.
- **Hash esperado**: `vault_note_hash` devolve o hash do arquivo; quem le, pensa e
  depois escreve passa `expected_hash`, e se outro agente mexeu no meio, a
  escrita e recusada com o hash novo em vez de pisar na mudanca alheia.
- **Esquecer**: move a nota para `<vault>/.lixeira/<data>/`, tira do indice e
  guarda a versao no historico. `vault_note_restore` traz de volta. Nunca apaga.
- **Corrigir**: troca um trecho exato (que aparece uma vez so) e deixa uma linha
  de correcao com data, autor e motivo no fim da nota.
- **Propor**: grava a mudanca sugerida em `proposals.json`; so a pessoa aplica,
  pela CLI, e a aplicacao recusa se a nota mudou desde a proposta.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from .arquivos_json import ler_json


def hash_texto(dados: bytes | str) -> str:
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    return hashlib.sha256(dados).hexdigest()[:16]


def resolver_unica(vault, nota: str) -> tuple[Path | None, dict | None]:
    """A nota, ou um erro. Caminho relativo exato vence; nome parcial so se for unico.

    Operacao que muda ou some com nota nao pode cair na primeira de varias, que e
    o que `find_notes_by_stem` faz para leitura.
    """
    from . import erros
    from .notes import resolve_in_vault
    raiz = Path(vault.cfg.vault)
    if nota.endswith(".md"):
        p = resolve_in_vault(raiz, nota)
        if p is not None and p.is_file():
            return p, None
    achadas = vault.find_notes_by_stem(nota.removesuffix(".md"))
    exatas = [a for a in achadas if a.stem.lower() == nota.removesuffix(".md").lower()]
    if len(exatas) == 1:
        return exatas[0], None
    if not achadas:
        return None, erros.nao_encontrado(f"Note not found: {nota}")
    if len(achadas) > 1:
        return None, erros.entrada_invalida(
            f"'{nota}' matches {len(achadas)} notes; pass the vault-relative path",
            candidates=[a.relative_to(raiz).as_posix() for a in achadas[:10]])
    return achadas[0], None


def info_hash(vault, nota: str) -> dict:
    p, erro = resolver_unica(vault, nota)
    if erro:
        return erro
    st = p.stat()
    return {"path": p.relative_to(vault.cfg.vault).as_posix(), "hash": hash_texto(p.read_bytes()),
            "bytes": st.st_size, "modified": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


def conferir_hash(p: Path, esperado: str) -> dict | None:
    """None se bate (ou se nao foi pedido). Senao, o erro de conflito com o hash atual."""
    if not esperado:
        return None
    atual = hash_texto(p.read_bytes())
    if atual == esperado:
        return None
    from . import erros
    return erros.entrada_invalida(
        "conflict: the note changed since you read it. Re-read it, merge, and retry "
        "with the new hash.", current_hash=atual, expected_hash=esperado)


def _guardar_versao(cfg, rel: str, dados: bytes, origem: str) -> None:
    try:
        from .historico_vault import abrir
        h = abrir(cfg)
        if h is not None:
            h.registrar(rel, dados, origem=origem)
    except Exception:  # noqa: BLE001 - historico e protecao, nao condicao
        pass


def esquecer(vault, nota: str, motivo: str = "", autor: str = "") -> dict:
    p, erro = resolver_unica(vault, nota)
    if erro:
        return erro
    raiz = Path(vault.cfg.vault)
    rel = p.relative_to(raiz).as_posix()
    dados = p.read_bytes()
    _guardar_versao(vault.cfg, rel, dados, "antes de esquecer")
    lixeira = raiz / ".lixeira"
    destino = lixeira / datetime.now().strftime("%Y-%m-%d") / rel
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino = destino.with_name(f"{destino.stem}-{uuid.uuid4().hex[:6]}{destino.suffix}")
    shutil.move(str(p), str(destino))
    vault.delete_notes([rel])
    from .busca_hibrida import esquecer_caminho
    esquecer_caminho(vault.cfg, rel)
    registro = {"when": datetime.now().isoformat(timespec="seconds"), "path": rel,
                "trash": destino.relative_to(raiz).as_posix(), "hash": hash_texto(dados),
                "by": autor, "reason": motivo}
    with (lixeira / "registro.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return {"status": "ok", **registro,
            "undo": f"vault_note_restore(note='{rel}', version=1) or move the file back from {registro['trash']}"}


def corrigir(vault, nota: str, trecho_antigo: str, trecho_novo: str, motivo: str = "",
             autor: str = "", esperado: str = "") -> dict:
    from . import erros
    from .notewriter import save_note
    p, erro = resolver_unica(vault, nota)
    if erro:
        return erro
    conflito = conferir_hash(p, esperado)
    if conflito:
        return conflito
    if not trecho_antigo:
        return erros.entrada_invalida("old_text is required")
    texto = p.read_text(encoding="utf-8")
    n = texto.count(trecho_antigo)
    if n != 1:
        return erros.entrada_invalida(
            f"old_text must appear exactly once in the note; it appears {n} times")
    rel = p.relative_to(vault.cfg.vault).as_posix()
    _guardar_versao(vault.cfg, rel, texto.encode("utf-8"), "antes de corrigir")
    quando = datetime.now().strftime("%Y-%m-%d %H:%M")
    linha = f"\n\n> Correcao {quando}" + (f" ({autor})" if autor else "") + (f": {motivo}" if motivo else "") + "\n"
    novo = texto.replace(trecho_antigo, trecho_novo).rstrip("\n") + linha
    r = save_note(vault, rel, novo)
    if "error" in r:
        return r
    return {"status": "ok", "path": rel, "hash": hash_texto(novo if not r.get("secrets_redacted") else p.read_bytes())}


# ── propostas ────────────────────────────────────────────────────────────────

class Propostas:
    """`proposals.json` em CONFIG_DIR. Atomico, uma trava por processo."""

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)
        self._trava = threading.Lock()

    def _ler(self) -> list[dict]:
        return ler_json(self.caminho, list)

    def _gravar(self, itens: list[dict]) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(itens, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def propor(self, vault, nota: str, texto_novo: str, trecho_antigo: str = "",
               motivo: str = "", autor: str = "") -> dict:
        from . import erros
        p, erro = resolver_unica(vault, nota)
        if erro:
            return erro
        if not texto_novo.strip():
            return erros.entrada_invalida("new_text is required")
        atual = p.read_text(encoding="utf-8")
        if trecho_antigo and atual.count(trecho_antigo) != 1:
            return erros.entrada_invalida("old_text must appear exactly once in the note")
        item = {
            "id": "prop_" + uuid.uuid4().hex[:8],
            "path": p.relative_to(vault.cfg.vault).as_posix(),
            "kind": "replace" if trecho_antigo else "append",
            "old_text": trecho_antigo, "new_text": texto_novo, "reason": motivo,
            "by": autor, "base_hash": hash_texto(atual), "status": "pending",
            "created": datetime.now().isoformat(timespec="seconds"), "decided": None,
        }
        with self._trava:
            itens = self._ler()
            itens.append(item)
            self._gravar(itens)
        return item

    def listar(self, status: str = "pending") -> list[dict]:
        itens = self._ler()
        if status != "all":
            itens = [i for i in itens if i["status"] == status]
        return sorted(itens, key=lambda i: i["created"], reverse=True)

    def _achar(self, itens, pid):
        achados = [i for i in itens if i["id"] == pid or i["id"].startswith(pid)]
        return achados[0] if len(achados) == 1 else None

    def rejeitar(self, pid: str) -> dict | None:
        with self._trava:
            itens = self._ler()
            i = self._achar(itens, pid)
            if i and i["status"] == "pending":
                i["status"] = "rejected"
                i["decided"] = datetime.now().isoformat(timespec="seconds")
                self._gravar(itens)
            return i

    def aplicar(self, cfg, pid: str, forcar: bool = False, gravar=None) -> dict:
        """Aplica a proposta. `gravar(rel, texto)` persiste; o padrao escreve o
        arquivo e NAO toca o indice, que e do daemon: quem chama reindexa."""
        from .notes import resolve_in_vault
        gravar = gravar or _gravar_arquivo(cfg)
        with self._trava:
            itens = self._ler()
            i = self._achar(itens, pid)
            if i is None:
                return {"error": f"proposal {pid} not found"}
            if i["status"] != "pending":
                return {"error": f"proposal {i['id']} is {i['status']}"}
            p = resolve_in_vault(Path(cfg.vault), i["path"])
            if p is None or not p.is_file():
                return {"error": f"note {i['path']} no longer exists"}
            atual = p.read_text(encoding="utf-8")
            if hash_texto(atual) != i["base_hash"] and not forcar:
                i["status"] = "stale"
                self._gravar(itens)
                return {"error": "note changed since the proposal; marked stale (use --force to apply anyway)"}
            if i["kind"] == "replace":
                if atual.count(i["old_text"]) != 1:
                    return {"error": "old_text no longer appears exactly once"}
                novo = atual.replace(i["old_text"], i["new_text"])
            else:
                novo = atual.rstrip("\n") + "\n\n" + i["new_text"].strip("\n") + "\n"
            _guardar_versao(cfg, i["path"], atual.encode("utf-8"), f"antes da proposta {i['id']}")
            r = gravar(i["path"], novo)
            if "error" in r:
                return r
            i["status"] = "applied"
            i["decided"] = datetime.now().isoformat(timespec="seconds")
            self._gravar(itens)
            return {"status": "ok", "id": i["id"], "path": i["path"]}


def _gravar_arquivo(cfg):
    """Escreve a nota (com segredo coberto), atomico, sem abrir o ChromaDB."""
    from .notes import resolve_in_vault
    from .notewriter import _proteger

    def gravar(rel: str, texto: str) -> dict:
        p = resolve_in_vault(Path(cfg.vault), rel)
        if p is None:
            return {"error": f"Path outside the vault: {rel}"}
        texto, _ = _proteger(cfg, texto)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(texto, encoding="utf-8")
        os.replace(tmp, p)
        return {"status": "ok"}
    return gravar


def propostas() -> Propostas:
    from . import config
    return Propostas(config.CONFIG_DIR / "proposals.json")


def cmd_proposals(args) -> int:
    ps = propostas()
    if args.acao == "list":
        itens = ps.listar(args.status)
        if not itens:
            print(f"no {args.status} proposals")
        for i in itens:
            print(f"{i['id']}  {i['status']:8} {i['kind']:7} {i['path']}  by {i['by'] or '?'}: {i['reason']}")
        return 0
    if args.acao == "show":
        itens = [i for i in ps.listar("all") if i["id"].startswith(args.id)]
        if len(itens) != 1:
            print(f"{args.id}: not found")
            return 1
        i = itens[0]
        print(json.dumps({k: i[k] for k in ("id", "path", "kind", "status", "by", "reason")}, ensure_ascii=False))
        if i["old_text"]:
            print("--- old\n" + i["old_text"])
        print("+++ new\n" + i["new_text"])
        return 0
    if args.acao == "reject":
        i = ps.rejeitar(args.id)
        print(f"{args.id}: {'rejected' if i else 'not found'}")
        return 0 if i else 1
    if args.acao == "apply":
        from .delegacao import _delegate
        from .config import Config
        cfg = Config.load()
        r = ps.aplicar(cfg, args.id, forcar=args.force)
        if "error" in r:
            print(r["error"])
            return 1
        print(f"applied {r['id']} to {r['path']}")
        # O indice e do daemon; a CLI so escreveu o arquivo. Um reindex
        # incremental pega a nota pela data de modificacao.
        args.local = False
        if _delegate(cfg, args, "vault_reindex_bg", {}, print) is None:
            print("daemon not reached: run `delegation-core reindex` to index the change")
        return 0
    return 1


def registrar(sub) -> dict:
    p = sub.add_parser("proposals", help="Note edits proposed by agents: list/show/apply/reject")
    s = p.add_subparsers(dest="acao", required=True)
    pl = s.add_parser("list", help="list proposals")
    pl.add_argument("--status", default="pending", choices=["pending", "applied", "rejected", "stale", "all"], help="which proposals to list")
    for nome in ("show", "reject"):
        s.add_parser(nome, help=f"{nome} a proposal").add_argument("id", help="proposal id")
    pa = s.add_parser("apply", help="apply a proposal to its note")
    pa.add_argument("id", help="proposal id")
    pa.add_argument("--force", action="store_true", help="apply even if the note changed since the proposal (otherwise it is marked stale)")
    return {"proposals": cmd_proposals}
