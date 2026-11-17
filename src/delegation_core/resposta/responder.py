"""O modelo local responde com base em trechos numerados; so volta a afirmacao cuja citacao existe no trecho.

## Por que existe

`search_vault` devolve trechos e o agente que chamou sintetiza a resposta,
lendo 5 trechos de ate 800 caracteres cada. E exatamente o trabalho que o
delegation-core existe para tirar do agente. O resumo local que ja existe
(`summary`) nao diz de onde veio cada frase, e ninguem confere se o modelo
inventou.

Aqui o modelo devolve afirmacoes, cada uma com a fonte e uma citacao literal
do trecho. A citacao e conferida no texto (sem acento, caixa ou espaco
repetido); afirmacao sem citacao que confira e descartada. O que volta e so o
que da para provar, com a nota de onde veio, ou "nao encontrado".

## Criterio de lego

`perguntar(system, prompt) -> str` e injetado; as fontes chegam prontas.
Nao sabe o que e busca, vault ou MCP.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

SISTEMA = """You answer a question using ONLY the numbered sources given (excerpts of a personal notes vault).
Return JSON only:
{"found": true|false, "claims": [{"text": "...", "source": N, "quote": "..."}]}
- Each claim: one short sentence answering part of the question, in the same language as the question.
- source: the number of the source that supports it.
- quote: an EXACT substring copied from that source (5 to 30 words) that proves the claim. Copy it character by character.
- At most 5 claims, most important first. Do not repeat.
- If the sources do not answer the question, return {"found": false, "claims": []}.
Compact JSON on one line."""


@dataclass
class Fonte:
    rotulo: str      # caminho da nota, ou o que identificar a fonte
    texto: str


def _norm(x: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFKD", str(x or "")) if not unicodedata.combining(c))
    t = re.sub(r"[*`_>#|\[\]]+", " ", t.lower())
    t = re.sub(r"[“”‘’\"']", "", t)
    return re.sub(r"\s+", " ", t).strip(" .,;:")


def janela(texto: str, termos: list[str], tamanho: int = 1500) -> str:
    """O pedaco de `tamanho` caracteres com mais termos distintos da pergunta; sem termo, o comeco."""
    if len(texto) <= tamanho:
        return texto
    tn = _norm_pos(texto)
    pos = sorted((m.start(), t) for t in {_norm(t) for t in termos if len(t) >= 3}
                 for m in re.finditer(re.escape(t), tn))
    if not pos:
        return texto[:tamanho]
    melhor, ini = -1, 0
    for i, (p, _) in enumerate(pos):
        dentro = {t for q, t in pos[i:] if q < p + tamanho}
        if len(dentro) > melhor:
            melhor, ini = len(dentro), max(0, p - 200)
    return texto[ini:ini + tamanho]


def _norm_pos(texto: str) -> str:
    """Minusculo e sem acento, preservando o comprimento (para a posicao valer no texto original)."""
    return "".join((unicodedata.normalize("NFKD", c)[0] if c.strip() else c).lower() for c in texto)


def _ler(resposta: str) -> dict:
    r = (resposta or "").strip()
    ini, fim = r.find("{"), r.rfind("}")
    if ini < 0 or fim <= ini:
        return {}
    try:
        d = json.loads(r[ini:fim + 1])
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def conferir(claims: list, fontes: list[Fonte], min_palavras: int = 4) -> tuple[list[dict], list[dict]]:
    """(conferidas, descartadas). Citacao tem que existir no trecho da fonte que a afirmacao aponta."""
    ok, fora = [], []
    vistos = set()
    for c in claims if isinstance(claims, list) else []:
        if not isinstance(c, dict):
            continue
        texto, cit = str(c.get("text") or "").strip(), str(c.get("quote") or "").strip()
        try:
            n = int(c.get("source"))
        except (TypeError, ValueError):
            n = 0
        motivo = ""
        if not texto or not cit:
            motivo = "sem texto ou citacao"
        elif not 1 <= n <= len(fontes):
            motivo = "fonte inexistente"
        elif len(_norm(cit).split()) < min_palavras:
            motivo = "citacao curta demais para provar algo"
        elif _norm(cit) not in _norm(fontes[n - 1].texto):
            motivo = "citacao nao esta na fonte"
        elif _norm(texto) in vistos:
            motivo = "repetida"
        item = {"text": texto, "source": fontes[n - 1].rotulo if 1 <= n <= len(fontes) else None, "quote": cit}
        if motivo:
            fora.append({**item, "reason": motivo})
        else:
            vistos.add(_norm(texto))
            ok.append(item)
    return ok, fora


def responder(pergunta: str, fontes: list[Fonte], perguntar: Callable[[str, str], str]) -> dict:
    if not fontes:
        return {"found": False, "answer": "", "claims": [], "dropped": [], "sources": []}
    blocos = [f"[{i}] ({f.rotulo})\n{f.texto}" for i, f in enumerate(fontes, 1)]
    d = _ler(perguntar(SISTEMA, f"Question: {pergunta}\n\nSources:\n\n" + "\n\n".join(blocos)))
    ok, fora = conferir(d.get("claims") or [], fontes)
    return {"found": bool(ok), "answer": " ".join(c["text"] for c in ok), "claims": ok, "dropped": fora,
            "model_said_found": bool(d.get("found")), "sources": [f.rotulo for f in fontes]}
