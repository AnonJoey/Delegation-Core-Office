"""O modelo local julga a relacao entre uma nota nova e uma antiga, e a citacao e conferida.

## Por que existe

O vault acumula estado que muda: uma decisao de agosto e revogada em setembro,
um "resolvido" e desmentido dois dias depois. A nota nova e escrita, a antiga
fica, e uma busca pode devolver a antiga como se valesse. Neste vault isso tem
nome proprio na memoria do usuario ("nao declare estado fechado": seis
retratacoes num dia so).

O hermes tem um curador que revisa o que acumulou (`agent/curator.py`), e o
openclaw tem uma fase de "sonho" que reorganiza a memoria fora do horario
(`memory-host-sdk/dreaming.ts`). Aqui o sonho faz a pergunta que mais importa
para este vault: **a nota nova contradiz ou atualiza alguma antiga?**

## A salvaguarda

Modelo local inventa. Por isso ele e obrigado a citar o trecho de cada nota que
sustenta o veredito, e `conferir()` procura a citacao no texto de verdade. Um
"contradiz" ou "atualiza" cuja citacao nao existe na nota vira
`citacao_inventada` e nao entra no relatorio como achado. E melhor o sonho nao
achar nada do que achar contradicao que nao existe.

## Criterio de lego

A funcao que pergunta ao modelo e injetada (`perguntar(system, prompt) -> str`).
Nao sabe o que e llama.cpp, fila, vault ou MCP.
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

RELACOES = ("contradicts", "updates", "repeats", "complements", "unrelated")
ACHADOS = ("contradicts", "updates")

SISTEMA = """You compare two notes from the same personal knowledge vault. NOTE A is newer, NOTE B is older.
Decide the relation of A to B, choosing exactly one:
- "contradicts": A states something incompatible with a claim in B, and B was not explicitly corrected.
- "updates": A supersedes or corrects a specific claim or decision in B (a later state of the same thing).
- "repeats": A says substantially the same thing as B.
- "complements": same topic, A adds new information without conflicting.
- "unrelated": different topics.
Answer with a single JSON object and nothing else:
{"relation": "...", "claim_in_B": "<short quote from B, or empty>", "claim_in_A": "<short quote from A, or empty>", "confidence": <0 to 1>}
Quote only text that is literally present in the notes."""


@dataclass
class Veredito:
    relacao: str
    citacao_b: str = ""
    citacao_a: str = ""
    confianca: float = 0.0
    problemas: list[str] = field(default_factory=list)
    bruto: str = ""

    @property
    def achado(self) -> bool:
        """Conta como achado so se for contradicao/atualizacao com as duas citacoes conferidas."""
        return self.relacao in ACHADOS and not self.problemas


def montar_prompt(titulo_a: str, data_a: str, texto_a: str, titulo_b: str, data_b: str, texto_b: str,
                  max_chars: int = 2500) -> str:
    return (f"NOTE A ({data_a}): {titulo_a}\n{texto_a[:max_chars]}\n\n"
            f"NOTE B ({data_b}): {titulo_b}\n{texto_b[:max_chars]}")


def _primeiro_json(texto: str) -> dict | None:
    """O primeiro objeto JSON do texto, tolerando cerca de codigo e prosa em volta."""
    texto = texto or ""
    ini = texto.find("{")
    while ini != -1:
        prof = 0
        for i in range(ini, len(texto)):
            if texto[i] == "{":
                prof += 1
            elif texto[i] == "}":
                prof -= 1
                if prof == 0:
                    try:
                        d = json.loads(texto[ini:i + 1])
                        if isinstance(d, dict):
                            return d
                    except ValueError:
                        break
                    break
        ini = texto.find("{", ini + 1)
    return None


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"[`*_>#\[\]|]", " ", t)
    return " ".join(t.split())


def citacao_existe(citacao: str, texto: str, min_chars: int = 12) -> bool:
    """A citacao esta no texto? Ignora caixa, acento, markdown e espaco; exige tamanho minimo.

    Aceita tambem citacao cortada pelo modelo com reticencias: cada pedaco entre
    "..." precisa existir, na ordem. Curta demais nao prova nada (tres palavras
    comuns existem em qualquer nota), entao nao conta como conferida.
    """
    c = _norm(citacao)
    if len(c) < min_chars:
        return False
    alvo = _norm(texto)
    pedacos = [p.strip() for p in re.split(r"\.\.\.|…", c) if p.strip()]
    pos = 0
    literal = True
    for p in pedacos:
        i = alvo.find(p, pos)
        if i == -1:
            literal = False
            break
        pos = i + len(p)
    return literal or cobertura(c, alvo) >= COBERTURA_MINIMA


#: Medido nos 7 vereditos "updates" do primeiro sonho sobre o vault real: o
#: modelo costura a citacao com pedacos que existem literalmente na nota, e a
#: busca exata recusava tres assim, dois deles verdadeiros. Cobertura por
#: blocos de 12+ caracteres: 0,97 a 1,00 nas citacoes costuradas de verdade,
#: 0,88 na unica inventada ("offload total na GPU (-ngl 99)", que nao existe
#: na nota). 0,95 separa os dois grupos.
COBERTURA_MINIMA = 0.95
BLOCO_MINIMO = 12


def cobertura(citacao_norm: str, alvo_norm: str) -> float:
    """Fracao da citacao coberta por blocos de pelo menos 12 caracteres que existem no texto."""
    if not citacao_norm:
        return 0.0
    s = difflib.SequenceMatcher(None, alvo_norm, citacao_norm, autojunk=False)
    return sum(b.size for b in s.get_matching_blocks() if b.size >= BLOCO_MINIMO) / len(citacao_norm)


def interpretar(bruto: str) -> Veredito:
    d = _primeiro_json(bruto)
    if d is None:
        return Veredito("invalido", problemas=["resposta sem JSON"], bruto=bruto)
    rel = str(d.get("relation", "")).strip().lower()
    if rel not in RELACOES:
        return Veredito("invalido", problemas=[f"relacao desconhecida: {rel!r}"], bruto=bruto)
    try:
        conf = float(d.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0.0
    return Veredito(rel, str(d.get("claim_in_B", "") or ""), str(d.get("claim_in_A", "") or ""),
                    max(0.0, min(1.0, conf)), bruto=bruto)


def conferir(v: Veredito, texto_a: str, texto_b: str) -> Veredito:
    """Achado sem citacao verificavel nas duas notas vira problema, e nao achado."""
    if v.relacao in ACHADOS:
        if not citacao_existe(v.citacao_b, texto_b):
            v.problemas.append("citacao_inventada: claim_in_B nao esta na nota B")
        if not citacao_existe(v.citacao_a, texto_a):
            v.problemas.append("citacao_inventada: claim_in_A nao esta na nota A")
    return v


def julgar(perguntar: Callable[[str, str], str], titulo_a: str, data_a: str, texto_a: str,
           titulo_b: str, data_b: str, texto_b: str) -> Veredito:
    bruto = perguntar(SISTEMA, montar_prompt(titulo_a, data_a, texto_a, titulo_b, data_b, texto_b))
    return conferir(interpretar(bruto), texto_a, texto_b)
