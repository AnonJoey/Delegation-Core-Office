"""O modelo local le uma nota e devolve fatos duraveis; o texto da nota decide o que fica.

## Por que existe

A busca devolve notas; quem pergunta "qual porta o daemon usa" ou "onde fica
o config do rclone" quer um valor, e o valor mais novo. Hoje o agente abre
tres notas e reconcilia sozinho, e erra quando a mais velha vem primeiro. O
hermes guarda fatos do usuario em memoria propria (`agent/memory`), o
openclaw destila memoria duravel da conversa (`memory-host-sdk`); aqui o
modelo local destila fato das notas, fora de hora.

## Como o texto manda no modelo

Medido em 27/09 com o gemma-4-12B em 4 notas reais: pedir a citacao exata
falhou em 8 de 12 fatos corretos (o modelo parafraseia a citacao). O que
separa fato de invencao e o **valor**: ele tem que aparecer no texto da nota,
comparado sem acento, caixa, crase ou negrito. 36 de 40 passaram, e os 4 que
cairam eram de fato reescritos pelo modelo (`asynchronous` onde a nota dizia
"em background").

## O que o prompt pede, e por que mudou

A primeira versao pedia "fato duravel" em aberto. Em 40 notas reais saiu 274
fatos, e de 25 sorteados so ~10 serviam: o resto era contagem do momento
(testes que passaram, arquivos, dinheiro), hash de commit e descricao de
comportamento de codigo. A segunda lista o que NAO extrair e fecha o
atributo num vocabulario; nas mesmas 8 notas, ~60% uteis contra ~40%, com
perda conhecida (endpoints de API e escopo de decisao, devolvidos ao
vocabulario como `endpoint` e `scope`).

## Criterio de lego

`perguntar(system, prompt) -> str` e injetado. Nao sabe o que e llama, vault ou MCP.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

SISTEMA = """You extract durable facts from one note of a personal technical vault, for later lookup.
Keep ONLY stable configuration and identity facts about a named thing:
where it lives (path, url, repository), how it is reached (port, host, command to run it),
what it runs on or with (version of installed software, model, device, runtime), its settings (a named option and its value),
and what was chosen for it (tool, vendor, approach adopted).
Never extract: counts or totals at one moment (tests passed, files, titles, money), commit hashes, dates, events,
descriptions of what code or a test does, errors, measurements, opinions, plans, anything the note says is old, wrong or replaced.
attribute MUST be one of: path, config_path, url, endpoint, repository, port, host, command, version, model, device,
runtime, service, owner, schedule, scope, chosen, setting:<option_name>
Return JSON only: {"facts": [{"subject": "...", "attribute": "...", "value": "...", "quote": "..."}]}
- subject: the thing, short canonical name as commonly written (e.g. "llama-server", "delegation-core", "rclone gdrive remote")
- value: short, exactly as written in the note
- quote: the sentence of the note that states it (max 200 chars)
At most 8 facts. Fewer is better than weak ones. Compact JSON on one line. If none, {"facts": []}."""

MAX_TEXTO = 12_000
MAX_PALAVRAS = 10

# Vocabulario fechado de atributo: e o que faz duas notas falarem da mesma
# coisa. Com atributo livre, 40 notas reais deram 271 pares (sujeito,
# atributo) e so 3 se repetiam entre notas (`test_count` e `test_suite_count`).
# Atributo de valor unico: dois valores em notas diferentes e contradicao (ou
# atualizacao). Os outros sao naturalmente multiplos: um projeto tem muitos
# caminhos, comandos e escolhas. Na primeira medicao do vault inteiro, das 40
# "divergencias" com todo atributo, quase todas eram isso (`soteria-pmo /
# path`: Deliverables, Downloads...), e nao contradicao.
UNICOS = frozenset({"port", "host", "url", "version", "model", "device", "config_path", "owner", "schedule",
                    "repository"})


def unico(atributo: str) -> bool:
    a = (atributo or "").lower()
    return a in UNICOS or a.startswith("setting:")


VOCABULARIO = frozenset({
    "path", "config_path", "url", "endpoint", "repository", "port", "host", "command", "version", "model",
    "device", "runtime", "service", "owner", "schedule", "scope", "chosen",
})
_OBJ = re.compile(r"\{[^{}]*\}")


@dataclass(frozen=True)
class Fato:
    sujeito: str
    atributo: str
    valor: str
    citacao: str = ""


def normalizar(x: str) -> str:
    """Sem acento, caixa, crase, negrito e espaco repetido: para comparar, nunca para mostrar."""
    t = "".join(c for c in unicodedata.normalize("NFKD", str(x or "")) if not unicodedata.combining(c))
    return re.sub(r"[\s*`_]+", " ", t.lower()).strip()


def chave(x: str) -> str:
    """Chave de agrupamento: `gdrive:` e `GDrive` sao o mesmo sujeito; `config path` e `config_path`, o mesmo atributo."""
    return re.sub(r"[^a-z0-9.]+", "_", normalizar(x)).strip("_.")


def _objetos(resposta: str) -> list[dict]:
    """JSON inteiro se vier inteiro; senao, cada objeto completo que der para ler (resposta cortada)."""
    r = (resposta or "").strip()
    ini = r.find("{")
    if ini >= 0:
        try:
            d = json.loads(r[ini:r.rfind("}") + 1])
            if isinstance(d, dict) and isinstance(d.get("facts"), list):
                return [f for f in d["facts"] if isinstance(f, dict)]
        except ValueError:
            pass
    saida = []
    for m in _OBJ.findall(r):
        try:
            d = json.loads(m)
        except ValueError:
            continue
        if isinstance(d, dict) and "value" in d:
            saida.append(d)
    return saida


def validar(brutos: list[dict], texto: str) -> list[Fato]:
    tn = normalizar(texto)
    vistos, saida = set(), []
    for f in brutos:
        s, a, v = (str(f.get(k) or "").strip() for k in ("subject", "attribute", "value"))
        if not (s and a and v) or len(v) > 300 or len(s) > 120 or len(a) > 80:
            continue
        a = a.strip().lower()
        if a not in VOCABULARIO and not (a.startswith("setting:") and len(a) > len("setting:")):
            continue
        # valor com mais de 10 palavras e descricao, nao valor ("tem RLock mais
        # tmp+fsync+replace", "construia um GerenciadorAcoes novo e verificava...")
        if len(v.split()) > MAX_PALAVRAS:
            continue
        vn = normalizar(v)
        if not vn or vn not in tn:
            continue
        # `hooks/x.py | path | hooks/x.py`: o valor so repete o sujeito, nao diz nada
        if chave(v) == chave(s):
            continue
        # `[[nota]]` e ligacao do vault, nao valor de nada (saiu como `repository`)
        if v.startswith("[["):
            continue
        k = (chave(s), chave(a), vn)
        if k in vistos or not k[0] or not k[1]:
            continue
        vistos.add(k)
        saida.append(Fato(s, a, v, str(f.get("quote") or "")[:300]))
    return saida


def extrair(texto: str, perguntar: Callable[[str, str], str], titulo: str = "") -> list[Fato]:
    t = (texto or "")[:MAX_TEXTO]
    if not t.strip():
        return []
    resposta = perguntar(SISTEMA, f"Note: {titulo}\n\n{t}")
    return validar(_objetos(resposta), t)
