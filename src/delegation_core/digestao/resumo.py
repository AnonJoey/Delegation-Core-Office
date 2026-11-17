"""Transcricao bruta de sessao vira resumo curado, pelo modelo local, em map-reduce.

## Por que existe

O hook de fim de sessao guarda a transcricao bruta de toda sessao do Claude
Code em `Sessions/`. O resumo curado so existe quando o agente lembra de chamar
`export_session`. Medido em 27/09: 126 transcricoes brutas (6,2 MB), e 60
delas, 2,5 MB, sao de dias sem NENHUMA sessao curada; mais 18 sem data no nome.
Para essas sessoes o unico registro e o bruto, que e justamente o texto que
mais atrapalha a busca (longo, generico, em muitos pedacos).

O openclaw resume transcricao (`src/transcripts/summary.ts`, `compaction.ts`);
o hermes comprime trajetoria. Aqui o modelo local faz o resumo, fora de hora.

## Como

1. **Pedacos**: a transcricao e cortada em fronteira de turno (`### You`,
   `### Claude`), perto de 10 mil caracteres, para caber no contexto do modelo
   local sem partir uma mensagem no meio.
2. **Map**: cada pedaco vira uma lista curta de fatos (decisao, o que foi
   feito, problema e solucao, pendencia), no idioma da conversa.
3. **Reduce**: as listas viram um resumo com secoes fixas.
4. **Conferencia**: nome de arquivo e comando citados no resumo tem que
   aparecer na transcricao; o que nao aparece e contado como possivel invencao
   e vai no rodape da nota, em vez de ser escondido.

## Criterio de lego

`perguntar(system, prompt) -> str` e injetado. Nao sabe o que e llama, vault ou MCP.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_FM = re.compile(r"^---\n.*?\n---\n?", re.S)
_TURNO = re.compile(r"^### (?:You|Claude)\b", re.M)
_CODIGO = re.compile(r"`([^`\n]{3,80})`")

MAPA = """You read one part of a conversation between a user and an AI coding assistant.
Extract only what matters later, as short bullet points, in the same language as the conversation:
- DECISION: something decided or chosen
- DONE: something built, changed, fixed or configured (name files, commands, tools)
- PROBLEM: an error or obstacle, and its cause or fix if found
- OPEN: something left pending or unresolved
Use only facts present in the text. No preamble. If nothing matters, answer: NOTHING"""

REDUZIR = """You receive bullet points extracted from consecutive parts of one work session.
Write a concise session summary in the same language as the bullets, in markdown, with exactly these sections:
## Resumo
(2 or 3 sentences: what the session was about and how it ended)
## Decisoes
## O que foi feito
## Problemas e solucoes
## Pendencias
Keep file names, commands and numbers exactly as given. Merge duplicates. Omit empty sections' bullets but keep the heading with "Nenhum." under it. No preamble."""


def corpo(texto: str) -> str:
    return _FM.sub("", texto or "", count=1)


def pedacos(texto: str, alvo: int = 10_000) -> list[str]:
    """Corta em fronteira de turno. Turno maior que o alvo sozinho vira um pedaco inteiro."""
    t = corpo(texto)
    inicios = [m.start() for m in _TURNO.finditer(t)] or [0]
    if inicios[0] != 0:
        inicios = [0] + inicios
    turnos = [t[a:b] for a, b in zip(inicios, inicios[1:] + [len(t)])]
    saida, atual = [], ""
    for tu in turnos:
        if atual and len(atual) + len(tu) > alvo:
            saida.append(atual)
            atual = ""
        atual += tu
    if atual.strip():
        saida.append(atual)
    # Transcricao de reuniao (Teams, `[mm:ss] Nome: fala`) nao tem marca de turno
    # e vinha inteira como um pedaco so. 33 KB cabem no contexto do modelo
    # local; a "Human AmplifIed" de 181 KB nao caberia. Pedaco acima de 1,5x o
    # alvo e recortado em fronteira de linha.
    final = []
    for p in saida:
        if len(p) <= alvo * 1.5:
            final.append(p)
            continue
        bloco = ""
        for linha in p.splitlines(keepends=True):
            if bloco and len(bloco) + len(linha) > alvo:
                final.append(bloco)
                bloco = ""
            bloco += linha
        if bloco.strip():
            final.append(bloco)
    return final


def citacoes_sem_lastro(resumo: str, transcricao: str) -> list[str]:
    """Trechos entre crases no resumo que nao aparecem na transcricao."""
    return sorted({c for c in _CODIGO.findall(resumo) if c not in transcricao})


def resumir(transcricao: str, perguntar: Callable[[str, str], str], alvo: int = 10_000) -> dict:
    partes = pedacos(transcricao, alvo)
    fatos = []
    for i, p in enumerate(partes):
        r = (perguntar(MAPA, p) or "").strip()
        if r and r.upper() != "NOTHING":
            fatos.append(f"(parte {i + 1})\n{r}")
    if not fatos:
        return {"resumo": "", "partes": len(partes), "sem_lastro": [], "vazio": True}
    resumo = (perguntar(REDUZIR, "\n\n".join(fatos)) or "").strip()
    return {"resumo": resumo, "partes": len(partes), "sem_lastro": citacoes_sem_lastro(resumo, transcricao),
            "vazio": not resumo}
