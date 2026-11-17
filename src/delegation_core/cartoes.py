"""Cartoes de status: buscas salvas que so dizem algo quando o resultado muda.

Trazido dos status cards do Paperclip, que tiram uma impressao digital da
entrada antes de gastar token: se nada mudou desde a ultima leitura, o cartao
responde "sem mudanca" e ninguem relê nada.

A impressao digital e por LEITOR (cliente MCP): o que mudou "desde a ultima
vez" e diferente para o Claude Code e para o Codex. Por isso ler um cartao
nao tira a novidade de outro cliente, e a leitura pode ser de escopo `read`.

Impressao = caminho e data de modificacao de cada resultado, em ordem. Mudar
uma nota que ja estava no resultado conta como mudanca; mudar a ordem tambem.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime
from pathlib import Path
from .arquivos_json import gravar_json

_TRAVA = threading.Lock()


def _arquivo() -> Path:
    from . import config
    return config.CONFIG_DIR / "status_cards.json"


def _ler() -> dict:
    try:
        d = json.loads(_arquivo().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"cards": {}, "seen": {}}
    if not isinstance(d, dict):
        return {"cards": {}, "seen": {}}
    d.setdefault("cards", {})
    d.setdefault("seen", {})
    return d


def _gravar(d: dict) -> None:
    gravar_json(_arquivo(), d)


def salvar(nome: str, consulta: str, escopo: str = "", limite: int = 5, pasta: str = "") -> dict:
    nome = nome.strip()
    if not nome or not consulta.strip():
        raise ValueError("name and query are required")
    card = {"query": consulta.strip(), "scope": escopo, "limit": max(1, min(limite, 20)),
            "folder": pasta, "created": datetime.now().isoformat(timespec="seconds")}
    with _TRAVA:
        d = _ler()
        d["cards"][nome] = card
        _gravar(d)
    return {"name": nome, **card}


def apagar(nome: str) -> bool:
    with _TRAVA:
        d = _ler()
        if nome not in d["cards"]:
            return False
        del d["cards"][nome]
        for leitor in d["seen"].values():
            leitor.pop(nome, None)
        _gravar(d)
        return True


def impressao(caminhos_mtime: list[tuple[str, float]]) -> str:
    texto = "\n".join(f"{c}\t{m:.0f}" for c, m in caminhos_mtime)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def atualizar(buscar, raiz: Path, leitor: str, nome: str = "") -> dict:
    """Roda os cartoes (ou um) e compara com o que `leitor` viu por ultimo.

    `buscar(card) -> [caminho relativo]`. So os cartoes que mudaram trazem a
    lista; os outros voltam com `changed: false` e mais nada.
    """
    with _TRAVA:
        d = _ler()
        if nome and nome not in d["cards"]:
            from . import erros
            return erros.nao_encontrado(f"card not found: {nome}")
        cards = {nome: d["cards"][nome]} if nome else dict(d["cards"])
        visto = d["seen"].setdefault(leitor or "unknown", {})
        saida = []
        for n, card in sorted(cards.items()):
            caminhos = buscar(card)
            pares = []
            for c in caminhos:
                try:
                    pares.append((c, (Path(raiz) / c).stat().st_mtime))
                except OSError:
                    pares.append((c, 0.0))
            fp = impressao(pares)
            anterior = visto.get(n) or {}
            if anterior.get("fingerprint") == fp:
                saida.append({"name": n, "changed": False, "last_change": anterior.get("when")})
                continue
            antes = set(anterior.get("paths") or [])
            agora = datetime.now().isoformat(timespec="seconds")
            saida.append({
                "name": n, "changed": True, "first_read": not anterior,
                "query": card["query"], "paths": caminhos,
                "new": [c for c in caminhos if c not in antes] if anterior else [],
                "gone": sorted(antes - set(caminhos)),
            })
            visto[n] = {"fingerprint": fp, "paths": caminhos, "when": agora}
        _gravar(d)
    return {"reader": leitor, "cards": saida, "changed": sum(1 for c in saida if c["changed"])}
