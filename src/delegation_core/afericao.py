"""Medir a qualidade da busca sem depender de perguntas escritas a mao.

## O problema que motivou

Os limiares do `search_vault` foram calibrados em 31/07/2026 com o vault em
1.159 notas, e ninguem mediu de novo. Em 26/09/2026 o vault tem 10.234 notas, e
a banda de par irrelevante subiu: p95 de 0,480 para **0,540**, maximo de 0,524
para **0,700**.

Isso envelheceu em silencio porque a calibracao original dependia de **cinco
perguntas escritas a mao**, e ninguem reescreve cinco perguntas toda vez que o
vault cresce. O que nao se mede sozinho nao se mede.

## O instrumento

Uma frase tirada do CORPO de uma nota vira a consulta, e a resposta certa e
aquela nota. Auto-supervisionado, sem curadoria, repetivel para sempre.

Medido na primeira execucao, 50 consultas sobre o vault real:

| | |
|---|---|
| recuperou a nota certa | 35 de 50 |
| posicao mediana do acerto | 1 |
| similaridade do acerto | mediana 0,630, p05 0,568, minimo 0,552 |

## O QUE ESTE INSTRUMENTO NAO SERVE PARA FAZER

**Nao serve para escolher o limiar**, e dizer que serve seria o erro mais caro
possivel aqui.

A calibracao de 31/07 mediu acerto entre **0,518 e 0,550**, abaixo do minimo de
0,552 que este instrumento observa. A razao e o instrumento, nao o vault: frase
do corpo e quase verbatim, e pergunta de gente e **parafrase**. Uma parafrase
pontua mais baixo.

Ou seja, **este instrumento mede um caso mais facil que o real**. Subir o
limiar com base nele descartaria justamente as perguntas parafraseadas que a
calibracao de julho existiu para proteger.

## Para o que ele serve

**Detectar regressao.** Recall e mediana do acerto sao comparaveis consigo
mesmos ao longo do tempo: se o recall cair de 35/50, ou a mediana cair de
0,630, alguma coisa piorou, e isso hoje nao tem quem perceba.

## Criterio de lego

Recebe uma colecao com `.get` e `.query`, dois metodos, e devolve numeros. Nao
sabe o que e vault, config, MCP nem limiar. Da para apagar este modulo e o
sistema funciona igual, sem saber se a busca piorou.
"""

from __future__ import annotations

import json
import logging
import math
import random
import re
import statistics

from .config import CONFIG_DIR
from .locking import arquivo_travado

logger = logging.getLogger("afericao")

#: A referencia com que as corridas seguintes sao comparadas. Sem isto o modulo
#: devolve um numero solto, e numero solto nao detecta regressao nenhuma.
ARQUIVO = CONFIG_DIR / "afericao_busca.json"

#: Frase curta demais nao identifica nota, e longa demais vira o documento
#: inteiro e mede trivialidade em vez de busca.
MIN_FRASE, MAX_FRASE = 60, 240

_FRONTMATTER = re.compile(r"^---.*?---", re.S)
_WIKILINK = re.compile(r"\[\[[^\]]*\]\]")
_CODIGO = re.compile(r"`[^`]*`")


def frases_utilizaveis(texto: str) -> list[str]:
    """Frases do corpo que servem como consulta.

    Frontmatter, wikilink e trecho de codigo saem: nenhum dos tres e prosa que
    alguem escreveria numa busca, e wikilink em particular casaria pelo nome do
    alvo em vez de pelo conteudo, medindo a coisa errada.
    """
    corpo = _FRONTMATTER.sub("", texto or "").strip()
    corpo = _CODIGO.sub(" ", _WIKILINK.sub(" ", corpo))
    saida = []
    for linha in corpo.split("\n"):
        limpa = linha.strip().lstrip("#-*| ").strip()
        if MIN_FRASE <= len(limpa) <= MAX_FRASE and not limpa.startswith(("http", "|", "```")):
            saida.append(limpa)
    return saida


def aferir(colecao, amostras: int = 50, semente: int = 0, profundidade: int = 10) -> dict:
    """Recall e banda de acerto da busca, medidos contra a propria colecao.

    `semente` fixa a amostra para duas execucoes serem comparaveis; e por isso
    que o resultado carrega a semente de volta, senao dois numeros de corridas
    diferentes nao querem dizer nada um ao lado do outro.
    """
    sorteio = random.Random(semente)

    bruto = colecao.get(where={"kind": "note"},
                        include=["metadatas", "documents"], limit=4000)
    pares = [
        (m, d) for m, d in zip(bruto.get("metadatas") or [], bruto.get("documents") or [])
        if (m or {}).get("path") and d and frases_utilizaveis(d)
    ]
    if not pares:
        return {"amostras": 0, "recall": None, "motivo": "nenhuma nota com frase utilizavel"}

    escolhidas = sorteio.sample(pares, min(amostras, len(pares)))
    acertos: list[float] = []
    posicoes: list[int] = []

    for meta, doc in escolhidas:
        consulta = sorteio.choice(frases_utilizaveis(doc))
        r = colecao.query(query_texts=[consulta], n_results=profundidade,
                          where={"kind": "note"}, include=["metadatas", "distances"])
        metas = (r.get("metadatas") or [[]])[0]
        dists = (r.get("distances") or [[]])[0]
        for i, (m2, d2) in enumerate(zip(metas, dists)):
            if (m2 or {}).get("path") == meta["path"]:
                acertos.append(1.0 - float(d2))
                posicoes.append(i + 1)
                break

    def percentil(xs: list[float], q: float) -> float:
        ordenado = sorted(xs)
        return ordenado[min(len(ordenado) - 1, int(len(ordenado) * q))]

    return {
        "amostras": len(escolhidas),
        "semente": semente,
        "profundidade": profundidade,
        "recuperadas": len(acertos),
        "recall": round(len(acertos) / len(escolhidas), 3),
        "posicao_mediana": statistics.median(posicoes) if posicoes else None,
        "acerto_mediana": round(statistics.median(acertos), 3) if acertos else None,
        "acerto_p05": round(percentil(acertos, 0.05), 3) if acertos else None,
        "acerto_minimo": round(min(acertos), 3) if acertos else None,
        # Repetido no resultado de proposito: quem le um numero destes daqui a
        # tres meses precisa da ressalva junto, e nao no docstring de um modulo
        # que ele nao vai abrir.
        "ressalva": ("frase do corpo e quase verbatim e pergunta de gente e "
                     "parafrase, entao isto mede um caso MAIS FACIL que o real. "
                     "Serve para detectar regressao, nao para escolher limiar."),
    }


def ler_referencia() -> dict | None:
    """A ultima medicao gravada, ou None quando nunca houve uma.

    None e diferente de "recall zero": a primeira corrida numa maquina nao tem
    com o que comparar, e dizer que piorou seria invencao.
    """
    try:
        if ARQUIVO.is_file():
            dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
            if isinstance(dados, dict) and dados.get("recall") is not None:
                return dados
    except Exception as e:
        logger.warning("afericao de referencia ilegivel (%s); tratando como ausente", e)
    return None


def gravar_referencia(medida: dict) -> None:
    """Guarda a medicao como nova referencia, sob trava e com escrita atomica.

    Falha calada: nao gravar significa nao ter com o que comparar na proxima,
    que e o estado de quem nunca gravou. Derrubar por causa disso seria trocar
    um problema pequeno por um grande.
    """
    try:
        ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
        with arquivo_travado(ARQUIVO):
            tmp = ARQUIVO.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(medida, indent=2, ensure_ascii=False),
                           encoding="utf-8")
            tmp.replace(ARQUIVO)
    except Exception as e:
        logger.warning("nao foi possivel gravar a afericao (%s)", e)


def _erro_padrao(p: float, n: int) -> float:
    """Erro padrao de uma proporcao. Com n=50 e p=0,7 da cerca de 0,065."""
    if not n:
        return 0.0
    return math.sqrt(max(p * (1.0 - p), 0.0) / n)


def comparar_com_referencia(medida: dict, referencia: dict | None) -> dict:
    """Piorou, e o quanto, com a margem que o tamanho da amostra permite.

    **O limite nao e um numero escolhido a dedo.** Uma amostra de 50 tem erro
    padrao de cerca de 0,065 no recall, entao uma queda de 0,05 nao significa
    nada e cravar "queda de 5% e regressao" produziria alarme toda semana. O
    corte e **duas vezes o erro padrao**, que e o que o tamanho da amostra
    sustenta.

    Aumentar `amostras` estreita a margem sozinho, sem ninguem reescrever
    limite nenhum, que e a razao de o corte ser calculado e nao constante.
    """
    if referencia is None:
        return {"tem_referencia": False,
                "veredito": "primeira medicao, nada com que comparar"}

    r_antes = float(referencia.get("recall") or 0.0)
    r_agora = float(medida.get("recall") or 0.0)
    n = int(medida.get("amostras") or 0)
    margem = 2 * _erro_padrao(r_antes, n)

    queda = r_antes - r_agora
    piorou = queda > margem

    return {
        "tem_referencia": True,
        "recall_antes": round(r_antes, 3),
        "recall_agora": round(r_agora, 3),
        "queda": round(queda, 3),
        "margem": round(margem, 3),
        "piorou": piorou,
        "veredito": (f"recall caiu {queda:.3f}, acima da margem de {margem:.3f} "
                     f"para uma amostra de {n}" if piorou
                     else f"dentro da margem de {margem:.3f} para uma amostra de {n}"),
    }
