"""Achar e cobrir segredo em texto: chave de API, token, chave privada, cabecalho Bearer.

## Por que existe

Medido em 26/09/2026: o vault desta maquina tem ZERO segredos, varridos por
dez padroes em 10.567 notas. Este modulo nao existe por dor medida, e sim por
tres portas que ja estao abertas e so nao foram usadas para isso ainda:

- a transcricao bruta de sessao vai inteira para `Sessions/`, e uma sessao em
  que alguem cola um token leva o token para o vault, indexado e buscavel
- a ferramenta de ler log (`registros.py`) devolve linhas de log para o
  agente, e log de cliente HTTP pode ter `Authorization: Bearer ...`
- o daemon tem um `server_token` que da acesso a tudo, e ja saiu por HTTP
  sem autenticacao uma vez (defeito corrigido em 04/09)

O desenho vem do openclaw (`src/logging/redact*.ts`, com padroes e limite de
tamanho) e do hermes (`agent/redact.py`).

## Regra de cobertura

O segredo vira `[REDIGIDO:<tipo>:<4 ultimos>]`. Os quatro ultimos caracteres
ficam para que duas ocorrencias do mesmo segredo possam ser reconhecidas como
a mesma, sem revelar nada util. Chave privada inteira vira uma linha so.

## Criterio de lego

So `re`. Recebe texto, devolve texto e contagem. Nao sabe o que e vault.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Padrao:
    tipo: str
    regex: re.Pattern
    grupo: int = 0


PADROES: tuple[Padrao, ...] = (
    Padrao("chave_privada", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----")),
    Padrao("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    Padrao("openai", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    Padrao("github", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    Padrao("github_fino", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}")),
    Padrao("google", re.compile(r"\bAIza[0-9A-Za-z_-]{35}")),
    Padrao("aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    Padrao("slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    Padrao("clickup", re.compile(r"\bpk_[0-9]+_[A-Z0-9]{20,}")),
    Padrao("huggingface", re.compile(r"\bhf_[A-Za-z0-9]{30,}")),
    Padrao("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    Padrao("bearer", re.compile(r"(?i)\b(?:authorization:\s*)?bearer\s+([A-Za-z0-9._~+/=-]{20,})"), grupo=1),
    Padrao("senha_em_url", re.compile(r"://[^/\s:@]+:([^/\s@]{6,})@"), grupo=1),
)


_SEM_SUFIXO = frozenset({"chave_privada", "senha_em_url"})


def _cobrir(tipo: str, segredo: str) -> str:
    # Sufixo so para token longo e aleatorio (20+): quatro caracteres de uma
    # senha de 13 revelam quase um terco dela. Pego pelo teste da URL.
    fim = segredo[-4:] if tipo not in _SEM_SUFIXO and len(segredo) >= 20 else ""
    return f"[REDIGIDO:{tipo}{':' + fim if fim else ''}]"


def redigir(texto: str, extras: tuple[str, ...] = ()) -> tuple[str, dict[str, int]]:
    """(texto coberto, contagem por tipo). `extras` sao segredos literais conhecidos (o server_token)."""
    contagem: dict[str, int] = {}
    saida = texto or ""
    for s in extras:
        if s and len(s) >= 12 and s in saida:
            contagem["conhecido"] = contagem.get("conhecido", 0) + saida.count(s)
            saida = saida.replace(s, _cobrir("conhecido", s))
    for p in PADROES:
        def troca(m, p=p):
            alvo = m.group(p.grupo)
            if alvo.startswith("[REDIGIDO"):
                return m.group(0)
            contagem[p.tipo] = contagem.get(p.tipo, 0) + 1
            inteiro = m.group(0)
            return inteiro.replace(alvo, _cobrir(p.tipo, alvo)) if p.grupo else _cobrir(p.tipo, alvo)
        saida = p.regex.sub(troca, saida)
    return saida, contagem


def achar(texto: str, extras: tuple[str, ...] = ()) -> dict[str, int]:
    """So a contagem, sem montar o texto novo."""
    return redigir(texto, extras)[1]
