"""O delegation-core como provedor de memoria do Paperclip.

O Paperclip planeja um `MemoryAdapter` (doc/plans/2026-03-17-memory-service-
surface-api.md, no repositorio deles) com seis operacoes: capture,
upsertRecords, query, list, get e forget, todas com um `MemoryScope` (empresa
obrigatoria; agente, projeto, issue, run, namespace opcionais) e devolvendo
`usage`. As ferramentas `memory_*` deste daemon seguem esses nomes e formatos,
para que um plugin do Paperclip (esqueleto em `integracoes/paperclip-plugin/`)
so traduza a chamada.

## Onde os registros moram

Cada registro e uma nota Markdown em
`<paperclip_memory_folder>/paperclip/<empresa>/`, com o escopo e a origem no
frontmatter. Continua sendo vault: aparece no `search_vault`, no historico, no
grafo de links. O identificador (`providerRecordId`) e o caminho relativo.

## Visibilidade

Um registro com `paperclip_agent` so aparece para aquele agente; sem, aparece
para toda a empresa. O mesmo vale para projeto. Empresa diferente nunca ve.
Essa e a regra "padrao da empresa, sobreposicao do agente" do plano deles.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

PROVEDOR = "delegation-core"
CHAVES_ESCOPO = ("agentId", "projectId", "issueId", "runId", "subjectId", "sessionKey", "namespace")
_SEGURO = re.compile(r"[^A-Za-z0-9_.-]+")


class ErroDeEscopo(ValueError):
    pass


def _limpo(texto: str) -> str:
    return _SEGURO.sub("-", texto).strip("-")[:60] or "x"


def _validar(escopo: dict | None) -> dict:
    if not isinstance(escopo, dict) or not str(escopo.get("companyId") or "").strip():
        raise ErroDeEscopo("scope.companyId is required")
    return {k: str(v) for k, v in escopo.items() if v not in (None, "") and (k == "companyId" or k in CHAVES_ESCOPO)}


def pasta_da_empresa(cfg, escopo: dict) -> Path:
    base = getattr(cfg, "paperclip_memory_folder", "") or "Reference"
    return Path(cfg.vault) / base / "paperclip" / _limpo(escopo["companyId"])


def _uso(t0: float, **extra) -> list[dict]:
    return [{"provider": PROVEDOR, "billingType": "unknown", "attributionMode": "untracked",
             "latencyMs": round((time.monotonic() - t0) * 1000, 1), **extra}]


def _fm_ler(texto: str) -> tuple[dict, str]:
    texto = texto.replace("\r\n", "\n")   # nota gravada no Windows tem CR
    if not texto.startswith("---\n"):
        return {}, texto
    fim = texto.find("\n---\n", 4)
    if fim == -1:
        return {}, texto
    fm = {}
    for linha in texto[4:fim].splitlines():
        if ":" in linha and not linha.startswith((" ", "-")):
            k, v = linha.split(":", 1)
            v = v.strip()
            try:
                fm[k.strip()] = json.loads(v)
            except ValueError:
                fm[k.strip()] = v
    return fm, texto[fim + 5:]


def _fm_escrever(fm: dict, corpo: str) -> str:
    linhas = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items() if v not in (None, "", {})]
    return "---\n" + "\n".join(linhas) + "\n---\n\n" + corpo.strip() + "\n"


def visivel(fm: dict, escopo: dict) -> bool:
    if fm.get("paperclip_company") != escopo["companyId"]:
        return False
    for chave, campo in (("agentId", "paperclip_agent"), ("projectId", "paperclip_project"),
                         ("namespace", "paperclip_namespace")):
        valor = fm.get(campo)
        if valor and valor != escopo.get(chave):
            return False
    return True


def _snippet(cfg, p: Path, fm: dict, corpo: str, limite: int = 0, score=None) -> dict:
    texto = corpo.strip()
    s = {"handle": {"providerKey": PROVEDOR, "providerRecordId": p.relative_to(cfg.vault).as_posix()},
         "text": texto[:limite] if limite else texto,
         "metadata": fm.get("paperclip_metadata") or {}}
    if fm.get("paperclip_summary"):
        s["summary"] = fm["paperclip_summary"]
    if fm.get("paperclip_source"):
        s["source"] = fm["paperclip_source"]
    if score is not None:
        s["score"] = score
    return s


def _gravar(vault, escopo: dict, texto: str, *, resumo: str = "", metadados=None, origem=None,
            tipo: str = "record", caminho_existente: str = "") -> str:
    from .notewriter import _proteger
    cfg = vault.cfg
    pasta = pasta_da_empresa(cfg, escopo)
    pasta.mkdir(parents=True, exist_ok=True)
    if caminho_existente:
        p = _resolver(cfg, caminho_existente, escopo)
    else:
        titulo = _limpo((resumo or texto)[:40])
        p = pasta / f"{datetime.now().strftime('%Y-%m-%d')}-{titulo}-{uuid.uuid4().hex[:6]}.md"
    fm = {"title": resumo[:80] if resumo else p.stem, "date": datetime.now().strftime("%Y-%m-%d"),
          "ai_generated": True, "memory_kind": tipo,
          "paperclip_company": escopo["companyId"],
          "paperclip_agent": escopo.get("agentId"), "paperclip_project": escopo.get("projectId"),
          "paperclip_issue": escopo.get("issueId"), "paperclip_run": escopo.get("runId"),
          "paperclip_namespace": escopo.get("namespace"),
          "paperclip_summary": resumo, "paperclip_metadata": metadados or {}, "paperclip_source": origem or {}}
    conteudo, _ = _proteger(cfg, _fm_escrever(fm, texto))
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(conteudo, encoding="utf-8")
    tmp.replace(p)
    rel = p.relative_to(cfg.vault).as_posix()
    if vault.index_note(conteudo, {"title": fm["title"], "path": rel, "folder": rel.split("/")[0]}):
        vault.stamp_indexed([rel])
    return rel


def _resolver(cfg, rel: str, escopo: dict) -> Path:
    from .notes import resolve_in_vault
    p = resolve_in_vault(Path(cfg.vault), rel)
    pasta = pasta_da_empresa(cfg, escopo).resolve()
    if p is None or not p.is_file():
        raise ErroDeEscopo(f"record not found: {rel}")
    try:
        p.resolve().relative_to(pasta)
    except ValueError:
        raise ErroDeEscopo(f"record {rel} is outside this company's memory") from None
    fm, _ = _fm_ler(p.read_text(encoding="utf-8"))
    if not visivel(fm, escopo):
        raise ErroDeEscopo(f"record {rel} is not visible in this scope")
    return p


# ── as seis operacoes ────────────────────────────────────────────────────────

def capture(vault, scope, source, payload, mode: str = "capture_residue", metadata=None) -> dict:
    t0 = time.monotonic()
    escopo = _validar(scope)
    texto = str((payload or {}).get("text") or "")
    if not texto.strip():
        raise ErroDeEscopo("payload.text is required")
    tipo = "residue" if mode == "capture_residue" else "record"
    rel = _gravar(vault, escopo, texto, metadados={**(payload.get("metadata") or {}), **(metadata or {})},
                  origem=source, tipo=tipo)
    return {"records": [{"providerKey": PROVEDOR, "providerRecordId": rel}], "jobs": [],
            "usage": _uso(t0, details={"chars": len(texto)})}


def upsert_records(vault, scope, records, source=None) -> dict:
    t0 = time.monotonic()
    escopo = _validar(scope)
    saida = []
    for r in records or []:
        if not str(r.get("text") or "").strip():
            raise ErroDeEscopo("every record needs text")
        meta = dict(r.get("metadata") or {})
        existente = meta.pop("providerRecordId", "")
        rel = _gravar(vault, escopo, r["text"], resumo=r.get("summary", ""), metadados=meta,
                      origem=source, caminho_existente=existente)
        saida.append({"providerKey": PROVEDOR, "providerRecordId": rel})
    return {"records": saida, "usage": _uso(t0)}


def _filtro(fm: dict, filtro: dict | None) -> bool:
    meta = fm.get("paperclip_metadata") or {}
    return all(meta.get(k) == v for k, v in (filtro or {}).items())


def query(vault, scope, query_text: str, top_k: int = 5, intent: str = "answer",
          metadata_filter=None, buscar=None) -> dict:
    """`buscar(consulta, limite) -> [caminho]`; o servidor passa a busca do search_vault."""
    t0 = time.monotonic()
    escopo = _validar(scope)
    cfg = vault.cfg
    pasta = pasta_da_empresa(cfg, escopo)
    prefixo = pasta.relative_to(cfg.vault).as_posix() + "/"
    limite_texto = {"agent_preamble": 400, "browse": 0, "answer": 1200}.get(intent, 1200)
    caminhos = [c for c in (buscar or (lambda q, n: []))(query_text, max(top_k * 6, 30)) if c.startswith(prefixo)]
    snippets = []
    for pos, rel in enumerate(caminhos):
        p = Path(cfg.vault) / rel
        try:
            fm, corpo = _fm_ler(p.read_text(encoding="utf-8"))
        except OSError:
            continue
        if not visivel(fm, escopo) or not _filtro(fm, metadata_filter):
            continue
        s = _snippet(cfg, p, fm, corpo, limite_texto or 1, score=round(1 / (pos + 1), 3))
        if intent == "browse":
            s["text"] = ""
        snippets.append(s)
        if len(snippets) >= top_k:
            break
    return {"snippets": snippets, "usage": _uso(t0)}


def list_records(vault, scope, cursor: str = "", limit: int = 20, metadata_filter=None) -> dict:
    t0 = time.monotonic()
    escopo = _validar(scope)
    cfg = vault.cfg
    pasta = pasta_da_empresa(cfg, escopo)
    arquivos = sorted(pasta.glob("*.md"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True) if pasta.is_dir() else []
    visiveis = []
    for p in arquivos:
        fm, corpo = _fm_ler(p.read_text(encoding="utf-8"))
        if visivel(fm, escopo) and _filtro(fm, metadata_filter):
            visiveis.append((p, fm, corpo))
    try:
        inicio = int(cursor or 0)
    except ValueError:
        raise ErroDeEscopo("invalid cursor") from None
    limit = max(1, min(limit, 100))
    pagina = visiveis[inicio:inicio + limit]
    out = {"items": [_snippet(cfg, p, fm, c, 400) for p, fm, c in pagina], "usage": _uso(t0)}
    if inicio + limit < len(visiveis):
        out["nextCursor"] = str(inicio + limit)
    return out


def get(vault, handle, scope) -> dict | None:
    escopo = _validar(scope)
    try:
        p = _resolver(vault.cfg, (handle or {}).get("providerRecordId", ""), escopo)
    except ErroDeEscopo:
        return None
    fm, corpo = _fm_ler(p.read_text(encoding="utf-8"))
    return _snippet(vault.cfg, p, fm, corpo)


def forget(vault, handles, scope) -> dict:
    from .memoria import esquecer
    t0 = time.monotonic()
    escopo = _validar(scope)
    esquecidos = []
    for h in handles or []:
        rel = (h or {}).get("providerRecordId", "")
        _resolver(vault.cfg, rel, escopo)  # levanta se for de outro escopo
        r = esquecer(vault, rel, motivo="paperclip memory.forget", autor=escopo.get("agentId", ""))
        if r.get("status") == "ok":
            esquecidos.append(rel)
    return {"forgotten": esquecidos, "usage": _uso(t0)}
