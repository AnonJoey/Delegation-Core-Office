"""Arquivar no vault so o artigo que mudou.

## Onde o custo estava, medido em 25/09/2026

Um `graph_build` deste fork, cronometrado fase a fase:

| Fase | Tempo |
|---|---|
| pipeline inteiro (detect, extract, build, cluster, analise, report, json, callflow, wiki) | 4,5s |
| arquivar 330 artigos no vault | 270s |

O pipeline e 1,6% do build. **Os outros 98% sao escrever nota**, e todo
rebuild reescreve as 330, inclusive as que nao mudaram uma virgula.

Duas medicoes de controle, porque o numero obvio estava errado das duas vezes:

- **O cache por arquivo do `graph/cache.py` nao explica nada aqui.** Extracao
  com cache quente custa 2,31s e com cache FRIO custa 2,40s. Este caminho e
  AST puro, sem LLM: nao ha o que cachear. Era por isso que ligar o
  `detect_incremental` nao ia adiantar, e nao pela falta de manifesto.
- **Medir num vault pequeno mentiria, mas NAO pelo motivo que escrevi.** A
  primeira versao deste docstring dizia que `index_note` custa 0,024s num vault
  de 20 notas e 0,82s no real "porque o custo por nota cresce com a colecao".
  **Medido depois, isso e falso:** o `delete(where={"path": ...})` custa 0,002s
  numa colecao de 41.431 linhas, e um `get` com filtro custa 0,008s. Tamanho de
  colecao nao e o gargalo.

  As duas medicoes diferiam em coisas que eu nao controlei: o vault real usa
  **bge-m3** e o temporario pegou o padrao **bge-base-en-v1.5**, que e outro
  modelo; e a medicao de 0,82s saiu de um build rodando sob o daemon, que
  mantem o llama.cpp na GPU. O custo por nota e o **embed**, 0,106s para o
  artigo tipico de 1,12 chunks, e ele responde ao modelo e a disputa por GPU,
  nao ao numero de linhas ja indexadas.

  O que continua valendo, e foi medido ponta a ponta: dois builds seguidos do
  fork passaram de 65,5s para 27,5s, e o segundo reescreveu **0 de 344**
  artigos.

## Quanto da para pular

Medido de verdade: uma funcao acrescentada a um arquivo, wiki regerado, os
dois lados comparados por md5.

- **231 de 328 artigos ficam identicos byte a byte (70,4%)**
- 97 sao novos ou mudaram (29,6%), e 25 somem

Uma mudanca de um arquivo mexe em 37% do wiki, porque renumera as comunidades
vizinhas. Sobra 70% de trabalho caro para nao fazer.

## A armadilha do frontmatter, que teria matado isto em silencio

`_frontmatter` grava `date: <hoje>` em cada nota. Hashear o arquivo ESCRITO
daria 100% de acerto enquanto se testasse no mesmo dia e **zero no dia
seguinte**, sem erro nenhum: o build so voltaria a demorar e ninguem ligaria
uma coisa na outra.

Por isso o hash e do **corpo** do artigo, que e o que o grafo produziu.

Consequencia deliberada: nota pulada mantem a data antiga no frontmatter.
Esse e o comportamento certo, porque a nota de fato nao foi refeita naquele
dia, e a data diz quando ela foi escrita.

## Criterio de lego

Nao sabe o que e vault, ChromaDB, BGE ou grafo. Recebe dois dicionarios de
`caminho -> hash` e devolve tres listas de caminho. Da para apagar este modulo
e o arquivamento volta a ser completo, so mais lento.

Depende de `locking` para gravar o manifesto, e essa dependencia e de
utilidade pura, da mesma natureza de `pathlib`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .locking import arquivo_travado

logger = logging.getLogger("arquivamento")

#: Nome do manifesto dentro da pasta de saida do grafo. Fica ao lado dos
#: artefatos e NAO no registro central: `vault_paths` sozinho ja levou o
#: registro a 181.666 caracteres, e guardar um hash por nota o dobraria.
NOME_MANIFESTO = "arquivadas.json"


@dataclass
class Plano:
    """O que fazer com cada caminho, decidido antes de tocar em disco."""

    escrever: list[str] = field(default_factory=list)
    manter: list[str] = field(default_factory=list)
    apagar: list[str] = field(default_factory=list)

    @property
    def economia(self) -> float:
        """Fracao dos artigos desejados que nao precisa ser reescrita."""
        total = len(self.escrever) + len(self.manter)
        return len(self.manter) / total if total else 0.0


def hash_do_corpo(corpo: str) -> str:
    """Impressao do conteudo gerado pelo grafo, sem o frontmatter.

    Quem chama passa o corpo do artigo, nunca o arquivo montado: o frontmatter
    carrega a data de hoje e invalidaria tudo a cada virada de dia.
    """
    return hashlib.md5(corpo.encode("utf-8")).hexdigest()


def planejar(desejado: dict[str, str], anterior: dict[str, str]) -> Plano:
    """Decide o que escrever, manter e apagar.

    `desejado` e `anterior` mapeiam caminho relativo no vault para o hash do
    corpo. Sem manifesto anterior, tudo e escrita, que e o comportamento de
    hoje e o padrao seguro.
    """
    plano = Plano()
    for caminho, h in sorted(desejado.items()):
        if anterior.get(caminho) == h:
            plano.manter.append(caminho)
        else:
            plano.escrever.append(caminho)
    plano.apagar = sorted(set(anterior) - set(desejado))
    return plano


def confirmar_no_disco(raiz: Path, anterior: dict[str, str]) -> dict[str, str]:
    """Descarta do manifesto o que nao esta mais no disco.

    Sem isto, apagar uma nota do vault na mao nunca a traria de volta: o
    manifesto continuaria dizendo que aquele hash esta arquivado e o build
    pularia a escrita para sempre. O modo de falha seria **vault
    silenciosamente incompleto**, que e exatamente a classe de defeito que
    este arquivamento incremental poderia introduzir.

    So confere existencia, nao reconfere conteudo: reler 330 arquivos para
    comparar hash devolveria parte do custo que o modulo existe para evitar, e
    o caso que importa na pratica e a nota sumida, nao a editada na mao.
    """
    return {c: h for c, h in anterior.items() if (raiz / c).is_file()}


def ler(pasta: Path) -> dict[str, str]:
    """O manifesto da ultima filagem, ou vazio.

    Manifesto ilegivel vale como ausente: o pior caso e refazer o
    arquivamento inteiro, que e o comportamento antigo. Levantar aqui
    derrubaria o build por causa de um arquivo de controle.
    """
    alvo = Path(pasta) / NOME_MANIFESTO
    try:
        if alvo.is_file():
            dados = json.loads(alvo.read_text(encoding="utf-8"))
            if isinstance(dados, dict):
                return {str(k): str(v) for k, v in dados.items()
                        if isinstance(v, (str, int, float))}
    except Exception as e:
        logger.warning("manifesto de arquivamento ilegivel em %s (%s); "
                       "tratando como ausente", alvo, e)
    return {}


def gravar(pasta: Path, mapa: dict[str, str]) -> None:
    """Guarda o manifesto sob trava, com escrita atomica.

    Trava porque dois `graph_build` do mesmo grafo ao mesmo tempo e possivel e
    barato de proteger, e a corrida aqui reintroduziria a mesma familia de
    update perdido que apagou duas fontes do registro de ingestao em
    31/08/2026.

    Falha calada por escolha: nao gravar o manifesto significa arquivamento
    completo no proximo build, que e lento e correto.
    """
    destino = Path(pasta)
    alvo = destino / NOME_MANIFESTO
    try:
        destino.mkdir(parents=True, exist_ok=True)
        with arquivo_travado(alvo):
            tmp = alvo.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(mapa, indent=2, sort_keys=True),
                           encoding="utf-8")
            tmp.replace(alvo)
    except Exception as e:
        logger.warning("nao foi possivel gravar o manifesto de arquivamento "
                       "(%s); o proximo build refaz tudo", e)
