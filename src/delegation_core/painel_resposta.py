"""Rota do painel para `ask_vault`: a pessoa pergunta e recebe so afirmacoes com citacao conferida.

O painel roda dentro do daemon, entao usa o mesmo `ask_vault` do agente (busca
hibrida, conferencia de citacao, aviso de nota superada). Fora do daemon,
sem vault carregado, diz isso em vez de abrir um segundo indice.
"""

from __future__ import annotations

import asyncio
import json

from .ligacao_painel import servidor as _srv


def _vault():
    return getattr(_srv(), "_vault", None)


async def _aguardar(r):
    return await r


def _rodar(r):
    """Ferramenta async ou ja convertida para def: o painel nao depende de qual."""
    return asyncio.run(_aguardar(r)) if asyncio.iscoroutine(r) else r


def perguntar(pergunta: str) -> dict:
    if not (pergunta or "").strip():
        return {"error": "question is required"}
    if _vault() is None:
        return {"error": "the vault is not loaded in this process (ask works only inside the daemon)"}
    return json.loads(_rodar(_srv().ask_vault(question=pergunta.strip())))


def fatos(consulta: str = "", divergentes: bool = False, limite: int = 30) -> dict:
    """Fatos para o painel: os mesmos grupos de `vault_facts`, lidos do armazem."""
    from . import fatos_vault

    cfg = getattr(_vault(), "cfg", None)
    if cfg is None:
        return {"error": "the vault is not loaded in this process (facts work only inside the daemon)"}
    arm = fatos_vault.armazem(cfg)
    if arm is None:
        return {"error": "fact extraction is disabled (fatos_enabled=false)"}
    grupos = arm.divergencias(limite) if divergentes else arm.buscar(consulta, limite=limite)
    return {"stats": arm.estatisticas(), "groups": grupos}


def achado(velha: str, nova: str, acao: str) -> dict:
    """Aplicar ou descartar um achado do sonho pelo painel: as mesmas ferramentas do agente."""
    if _vault() is None:
        return {"error": "the vault is not loaded in this process (works only inside the daemon)"}
    if acao not in ("apply", "dismiss") or not velha or not nova:
        return {"error": "action must be apply or dismiss, with old and new"}
    f = _srv().dream_apply if acao == "apply" else _srv().dream_dismiss
    return json.loads(_rodar(f(old=velha, new=nova)))
