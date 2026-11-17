"""Modulo que ninguem importa e capacidade sem fio, e este projeto tem historico.

## Por que esta guarda existe

Na noite de 25 para 26/09/2026 o `capabilities()` listava **cinco** funcoes
implementadas e sem chamador. Quatro foram medidas e recusadas por nao terem
sobre o que agir aqui, e uma, o `graph_diff`, era lacuna de verdade: existia
pronta e testada desde sempre, e o que faltava era o build guardar o grafo
anterior para ela ter contra o que comparar.

E no meio dessa mesma noite **eu cometi o mesmo defeito**: escrevi o
`afericao.py` com dez testes e zero chamadores fora deles. So percebi ao
auditar o proprio trabalho.

Prosa nao previne isso. Um teste previne.

## O que a guarda faz, e o que ela NAO faz

Ela garante que todo modulo de `src/delegation_core/` seja importado por algum
outro modulo de producao. E uma condicao fraca de proposito: passar nela nao
significa que o modulo esta bem ligado, so que alguem o alcanca. Um modulo
importado e nunca chamado ainda passa.

A condicao forte, "existe caminho de execucao que chega aqui", nao da para
escrever de forma barata e confiavel, e uma guarda que promete mais do que
cumpre e pior que nenhuma. Esta cobre o caso grosseiro, que foi o que
aconteceu duas vezes.

## A lista de excecao

Dois nomes, ambos pontos de entrada que o sistema operacional invoca, e nao o
Python. Uma excecao sem motivo escrito vira permissao permanente, entao cada
uma carrega o seu.
"""

from __future__ import annotations

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "src" / "delegation_core"

#: Modulos que ninguem importa DE PROPOSITO, com o motivo.
#:
#: - `__main__`: e o que `python -m delegation_core` executa. Ser importado
#:   seria justamente o erro.
#: - `graph_hook_rebuild`: o hook de post-commit do git o invoca como
#:   subprocesso, por caminho de arquivo. Importa-lo do daemon traria o
#:   rebuild para dentro do processo errado.
PONTOS_DE_ENTRADA = {
    "__main__": "executado por python -m, nunca importado",
    "graph_hook_rebuild": "invocado como subprocesso pelo hook de post-commit",
}


def _importadores(modulo: str, fontes: dict[pathlib.Path, str]) -> list[str]:
    # `from ..modulo import` conta: um subpacote que alcanca um modulo da raiz (os portes do ai-memory
    # usam `..texto_bytes`) e um importador, e sem isso o modulo parecia orfao.
    padrao = re.compile(
        rf"from \.{{1,2}}{modulo} import|from \. import {modulo}\b|from \.\. import {modulo}\b|"
        rf"from delegation_core\.{modulo} import|import delegation_core\.{modulo}\b")
    return sorted(p.name for p, texto in fontes.items()
                  if p.stem != modulo and padrao.search(texto))


def _fontes() -> dict[pathlib.Path, str]:
    return {p: p.read_text(encoding="utf-8") for p in RAIZ.rglob("*.py")}


def test_todo_modulo_tem_quem_o_importe():
    """O caso grosseiro: modulo novo que ninguem alcanca.

    Conferido por mutacao: tirar `from . import diferenca` do `graphbridge`
    derruba este teste, que e exatamente a forma do defeito que aconteceu com
    o `afericao.py`.
    """
    fontes = _fontes()
    # `__init__` sai por REGRA DA LINGUAGEM e nao por decisao do projeto:
    # ninguem escreve `from .__init__ import`, ele e carregado ao importar o
    # pacote. Por isso fica fora daqui e nao na lista de excecao, que existe
    # para escolhas que alguem fez.
    modulos = sorted(p.stem for p in RAIZ.glob("*.py") if p.stem != "__init__")
    orfaos = [m for m in modulos
              if m not in PONTOS_DE_ENTRADA and not _importadores(m, fontes)]
    assert not orfaos, (
        f"modulo(s) que ninguem importa: {orfaos}. Ligue, ou acrescente a "
        "PONTOS_DE_ENTRADA com o motivo escrito.")


def test_a_lista_de_excecao_nao_tem_nome_morto():
    """Excecao para modulo que nao existe mais e permissao dada a ninguem.

    A mesma doenca que o `capabilities()` existe para conter: prosa que
    descreve um mundo que mudou.
    """
    existentes = {p.stem for p in RAIZ.rglob("*.py")}
    mortos = sorted(set(PONTOS_DE_ENTRADA) - existentes)
    assert not mortos, f"excecao para modulo inexistente: {mortos}"


def test_a_lista_de_excecao_nao_esconde_modulo_ja_ligado():
    """Se um ponto de entrada ganhar importador, a excecao passa a mentir.

    Sem isto, a lista acumularia nomes que nao precisam mais estar la, e a
    proxima pessoa confiaria nela para decidir se um modulo e alcancavel.
    """
    fontes = _fontes()
    for modulo in sorted(PONTOS_DE_ENTRADA):
        quem = _importadores(modulo, fontes)
        assert not quem, (
            f"{modulo} esta declarado como ponto de entrada nao importado, mas "
            f"{quem} o importa; tire da lista")


def test_os_modulos_escritos_nesta_noite_estao_ligados():
    """Os oito, nomeados, porque generico nao pega regressao especifica.

    Cada um foi escrito nesta noite ou na anterior, e um deles, o `afericao`,
    passou horas sem chamador nenhum.
    """
    fontes = _fontes()
    for modulo in ("locking", "erros", "calibracao", "arquivamento",
                   "dispositivos", "diferenca", "listas", "afericao"):
        assert _importadores(modulo, fontes), f"{modulo} ficou sem chamador"
