"""Liga `passagem/` ao delegation-core: onde guardar, qual e o projeto, e o que os hooks fazem.

O pacote `passagem` nao sabe o que e projeto, config nem hook. Este modulo sabe:

- **Projeto**: a pasta do repositorio git mais proxima do diretorio da sessao (o nome dela), ou o
  nome do proprio diretorio. Duas sessoes no mesmo repositorio, em subpastas diferentes, sao o
  mesmo projeto, e a passagem automatica ainda so serve a quem comeca no mesmo diretorio ou abaixo.
- **Inicio de sessao** (`ao_comecar`): registra a sessao, escolhe a passagem, aceita (atomico) e
  devolve o texto cercado como dado nao confiavel. Se outra sessao foi mais rapida, nao devolve nada.
- **Fim de sessao** (`ao_terminar`): encerra a sessao e deixa uma passagem automatica extraida da
  transcricao, sem modelo: o ultimo pedido, a ultima resposta e as caixas de selecao em aberto.
- **Ferramentas** `handoff_*`: passagem manual (vale para o projeto todo), listar, aceitar e cancelar.

Os hooks leem a config como dicionario (`config.json`) e o servidor como objeto: `_flag` aceita os dois.
Desligado por padrao (`passagem_enabled=false`); desligado, nada aqui toca o disco.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from .passagem.armazem import Passagens
from .passagem.texto import renderizar

logger = logging.getLogger(__name__)

_BANCOS: dict[str, Passagens] = {}
_CAIXA_ABERTA = re.compile(r"^\s*[-*]\s+\[ \]\s+(.+?)\s*$", re.MULTILINE)
RESUMO_MAX_CARACTERES = 1500
PEDIDO_MAX_CARACTERES = 600


def _flag(cfg, nome: str, padrao):
    if isinstance(cfg, dict):
        v = cfg.get(nome)
    else:
        v = getattr(cfg, nome, None)
    return padrao if v is None else v


def ligado(cfg) -> bool:
    return bool(_flag(cfg, "passagem_enabled", False))


def caminho_do_banco(cfg) -> Path:
    escolhido = _flag(cfg, "passagem_path", "")
    if escolhido:
        return Path(escolhido).expanduser()
    return Path.home() / ".delegation_core" / "passagens.sqlite3"


def abrir(cfg) -> Passagens | None:
    if not ligado(cfg):
        return None
    caminho = str(caminho_do_banco(cfg))
    if caminho not in _BANCOS:
        _BANCOS[caminho] = Passagens(caminho)
    return _BANCOS[caminho]


def fechar_todos() -> None:
    for b in _BANCOS.values():
        b.fechar()
    _BANCOS.clear()


def projeto_de(cwd: str | None) -> str:
    """O nome do repositorio git que contem `cwd`, ou o nome do proprio diretorio. `default` se nao houver."""
    if not cwd:
        return "default"
    p = Path(cwd.replace("\\", "/"))
    for d in (p, *p.parents):
        try:
            if (d / ".git").exists():
                return d.name or "default"
        except OSError:
            break
    return p.name or "default"


def _agora_us() -> int:
    return time.time_ns() // 1000


# ── hooks ──────────────────────────────────────────────────────────────────


def ao_comecar(cfg, payload: dict, agente: str = "claude-code") -> str | None:
    """O texto a injetar no inicio de uma sessao, ou None. Nunca levanta: o inicio da sessao nao pode quebrar."""
    try:
        b = abrir(cfg)
        sessao, cwd = payload.get("session_id"), payload.get("cwd") or ""
        if b is None or not sessao:
            return None
        projeto = projeto_de(cwd)
        b.abrir_sessao(sessao, projeto, agente, cwd or None)
        escolhida = b.escolher(projeto, cwd or None)
        if escolhida is None:
            return None
        if not b.aceitar(escolhida["id"], projeto=projeto, agente=agente, sessao=sessao, cwd_do_receptor=cwd or None):
            return None  # outra sessao levou: o texto nao chega a este agente
        return renderizar(escolhida, _agora_us())
    except Exception as e:  # noqa: BLE001
        logger.warning("passagem: o inicio de sessao falhou: %s", e)
        return None


def resumo_da_transcricao(mensagens: list[dict]) -> dict | None:
    """O que a proxima sessao precisa, extraido sem modelo: ultimo pedido, ultima resposta, caixas em aberto."""
    pedido = next((m["text"] for m in reversed(mensagens) if m.get("role") == "user" and (m.get("text") or "").strip()
                   and not m["text"].lstrip().startswith("<")), "")
    respostas = [m["text"] for m in mensagens if m.get("role") == "assistant" and (m.get("text") or "").strip()]
    if not pedido and not respostas:
        return None
    ultima = respostas[-1] if respostas else ""
    resumo = []
    if pedido:
        resumo.append("Last request: " + " ".join(pedido.split())[:PEDIDO_MAX_CARACTERES])
    if ultima:
        resumo.append("Last reply: " + " ".join(ultima.split())[:RESUMO_MAX_CARACTERES])
    abertos: list[str] = []
    for texto in respostas[-3:]:
        for m in _CAIXA_ABERTA.finditer(texto):
            item = m.group(1)[:300]
            if item not in abertos:
                abertos.append(item)
    return {"resumo": "\n\n".join(resumo), "proximos": abertos}


def ao_terminar(cfg, payload: dict, mensagens: list[dict], agente: str = "claude-code") -> str | None:
    """Encerra a sessao e deixa uma passagem automatica. Devolve o id, ou None. Nunca levanta."""
    try:
        b = abrir(cfg)
        sessao, cwd = payload.get("session_id"), payload.get("cwd") or ""
        if b is None or not sessao:
            return None
        projeto = projeto_de(cwd)
        b.abrir_sessao(sessao, projeto, agente, cwd or None)
        b.encerrar_sessao(sessao)
        r = resumo_da_transcricao(mensagens)
        if r is None:
            return None
        return b.criar(projeto=projeto, de_agente=agente, resumo=r["resumo"], cwd=cwd or None, de_sessao=sessao,
                       proximos=r["proximos"])
    except Exception as e:  # noqa: BLE001
        logger.warning("passagem: o fim de sessao falhou: %s", e)
        return None


# ── ferramentas ────────────────────────────────────────────────────────────


def criar_manual(cfg, resumo: str, *, projeto: str = "", cwd: str = "", agente: str = "agent", perguntas=(), proximos=(),
                 arquivos=()) -> dict:
    b = abrir(cfg)
    if b is None:
        return {"error": "passagem desligada (passagem_enabled=false)"}
    if not resumo.strip():
        return {"error": "o resumo da passagem nao pode ser vazio", "kind": "invalid"}
    projeto = projeto or projeto_de(cwd)
    pid = b.criar(projeto=projeto, de_agente=agente, resumo=resumo, cwd=cwd or None, perguntas=perguntas, proximos=proximos,
                  arquivos=arquivos)
    return {"status": "ok", "id": pid, "project": projeto, "manual": True}


def pegar(cfg, *, projeto: str = "", cwd: str = "", agente: str = "agent") -> dict:
    """Escolhe e aceita a passagem para quem chama. `handoff` vem com o texto cercado, ou None se nao havia."""
    b = abrir(cfg)
    if b is None:
        return {"error": "passagem desligada (passagem_enabled=false)"}
    projeto = projeto or projeto_de(cwd)
    escolhida = b.escolher(projeto, cwd or None)
    if escolhida is None:
        return {"project": projeto, "handoff": None}
    if not b.aceitar(escolhida["id"], projeto=projeto, agente=agente, cwd_do_receptor=cwd or None):
        return {"project": projeto, "handoff": None, "note": "another session picked it up first"}
    return {"project": projeto, "id": escolhida["id"], "manual": escolhida["manual"], "handoff": renderizar(escolhida, _agora_us())}


def listar(cfg, *, projeto: str = "", cwd: str = "", estado: str = "aberta", limite: int = 20) -> dict:
    b = abrir(cfg)
    if b is None:
        return {"error": "passagem desligada (passagem_enabled=false)"}
    projeto = projeto or projeto_de(cwd)
    itens = b.listar(projeto, estado or None, max(1, min(int(limite), 100)))
    return {"project": projeto, "count": len(itens), "handoffs": [
        {"id": i["id"], "state": i["estado"], "from_agent": i["de_agente"], "manual": i["manual"], "cwd": i["cwd"],
         "created_us": i["criada_em"], "summary": i["resumo"][:200]} for i in itens]}


def cancelar(cfg, handoff_id: str, *, projeto: str = "", cwd: str = "") -> dict:
    b = abrir(cfg)
    if b is None:
        return {"error": "passagem desligada (passagem_enabled=false)"}
    projeto = projeto or projeto_de(cwd)
    return {"status": "ok" if b.cancelar(handoff_id, projeto=projeto) else "not_open", "id": handoff_id, "project": projeto}
