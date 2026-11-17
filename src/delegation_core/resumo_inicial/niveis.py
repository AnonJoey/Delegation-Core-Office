"""Quanto de cada nota fixa cabe no resumo de inicio de sessao: a conta dos niveis.

Porte de `crates/ai-memory-hooks/src/brief_tiers.rs` do ai-memory (MIT, Fabio Akita).

O resumo antigo despejava o corpo inteiro de cada nota fixa ate o orcamento acabar, e
uma nota longa de regras truncava e reduzia todas as seguintes a "omitida". A conta
aqui e **cobertura primeiro**: toda nota que cabe ganha o seu L0 (ou so a linha do
caminho, se nao tem trecho); com o que sobra, aprofunda para L1 e depois L2 (o corpo
inteiro), as privilegiadas (fixadas) antes. Um L2 so entra inteiro, nunca truncado.

So aritmetica sobre custos em bytes ja calculados: quem monta o texto e o dono das
strings. Pura.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum

#: Um corpo que passa so isto do que a nota ja mostra e completado mesmo enquanto outras
#: ainda esperam o L1: o resto custa o que um segundo titulo custaria.
FOLGA_CORPO_CURTO = 128


class Nivel(IntEnum):
    """Profundidade com que uma nota aparece, em ordem."""

    OMITIDA = 0      # so listada, pelo caminho, na secao de omitidas
    SO_TITULO = 1    # sem trecho para mostrar: uma linha com o caminho
    L0 = 2           # titulo mais o trecho curto
    L1 = 3           # titulo mais o trecho longo
    L2 = 4           # titulo mais o corpo inteiro


@dataclass(frozen=True)
class CustoDaNota:
    """Custo, em bytes, de uma nota em cada profundidade."""

    privilegiada: bool
    so_titulo: int
    #: Custos em L0, L1 e L2, ou None quando nao ha trecho e so cabe a linha do caminho.
    niveis: tuple[int, int, int] | None

    def custo(self, nivel: Nivel) -> int:
        if nivel == Nivel.OMITIDA:
            return 0
        if self.niveis is not None:
            if nivel == Nivel.L0:
                return self.niveis[0]
            if nivel == Nivel.L1:
                return self.niveis[1]
            if nivel == Nivel.L2:
                return self.niveis[2]
        return self.so_titulo

    def l1_acrescenta(self) -> bool:
        return self.niveis is not None and self.niveis[1] > self.niveis[0]


@dataclass(frozen=True)
class Orcamento:
    prefixo: int           # bytes ja gastos antes da primeira nota (abertura, aviso, cerca)
    teto_do_conteudo: int  # o orcamento menos tudo da cerca de fechamento em diante
    recentes_inteiro: int  # a secao de notas recentes com todo o seu tamanho
    recentes_primeiro: int  # a menor secao de recentes que ainda mostra algo: titulo e primeira linha


@dataclass(frozen=True)
class Plano:
    niveis: list[Nivel]
    omitidas_a_partir: int  # indice da primeira omitida (len(niveis) se nenhuma)
    reserva_de_recentes: int


def _sub_sat(a: int, b: int) -> int:
    return a - b if a > b else 0


def atribuir_niveis(
    notas: list[CustoDaNota],
    orc: Orcamento,
    omitidas_inteiro: Callable[[int], int],
    so_contagem: Callable[[int], int],
) -> Plano:
    """`assign_tiers`.

    `omitidas_inteiro(a_partir)` e o tamanho da secao que lista cada nota de `a_partir` em
    diante, e `so_contagem(n)` o da sua menor forma, a contagem de `n` notas.
    """
    n = len(notas)
    niveis = [Nivel.OMITIDA] * n
    variavel = _sub_sat(orc.teto_do_conteudo, orc.prefixo)

    def parte_dos_recentes(sobra: int) -> int:
        return min(orc.recentes_inteiro, max(sobra // 4, orc.recentes_primeiro))

    teto_recentes = parte_dos_recentes(variavel)
    # Nota fixa que ficou de fora e regra que o agente nao recebeu: a contagem das omitidas
    # e reservada antes da cobertura, no tamanho de quando todas sao omitidas.
    piso_omitidas = 0 if n == 0 else so_contagem(n)
    teto_da_cobertura = _sub_sat(orc.teto_do_conteudo, teto_recentes + piso_omitidas)

    gasto = orc.prefixo
    omitidas_a_partir = n
    for i, nota in enumerate(notas):
        nivel = Nivel.L0 if nota.niveis is not None else Nivel.SO_TITULO
        custo = nota.custo(nivel)
        if gasto + custo > teto_da_cobertura:
            omitidas_a_partir = i
            break
        niveis[i] = nivel
        gasto += custo

    sobra = _sub_sat(orc.teto_do_conteudo, gasto)
    if omitidas_a_partir == n:
        reserva_omitidas = 0
    else:
        reserva_omitidas = min(max(min(omitidas_inteiro(omitidas_a_partir), sobra // 4),
                                   so_contagem(n - omitidas_a_partir)), sobra)
    depois_das_omitidas = _sub_sat(sobra, reserva_omitidas)
    reserva_de_recentes = min(parte_dos_recentes(depois_das_omitidas), depois_das_omitidas)
    sala = _sub_sat(sobra, reserva_omitidas + reserva_de_recentes)

    incluidas = notas[:omitidas_a_partir]
    privilegiadas = [i for i in range(omitidas_a_partir) if notas[i].privilegiada]
    comuns = [i for i in range(omitidas_a_partir) if not notas[i].privilegiada]

    def delta(i: int, alvo: Nivel) -> int | None:
        nota = notas[i]
        atual = niveis[i]
        if nota.niveis is not None and atual != Nivel.SO_TITULO and atual < alvo:
            d = nota.custo(alvo) - nota.custo(atual)
            return d if d > 0 else None
        return None

    def promover(ordem: list[int], alvo: Nivel, delta_max: int | float) -> None:
        nonlocal sala
        for i in ordem:
            d = delta(i, alvo)
            if d is not None and d <= min(sala, delta_max):
                niveis[i] = alvo
                sala -= d

    inf = float("inf")
    promover(privilegiadas, Nivel.L1, inf)
    promover(privilegiadas, Nivel.L2, inf)
    promover(comuns, Nivel.L1, inf)
    promover(comuns, Nivel.L2, FOLGA_CORPO_CURTO)
    # Corpos inteiros para as demais so quando toda nota incluida ja mostra o que o seu L1 mostra:
    # um corpo longo nao pode passar na frente de um resumo. Os mais baratos primeiro.
    todas_em_l1 = all(niveis[i] >= Nivel.L1 or not incluidas[i].l1_acrescenta() for i in range(len(incluidas)))
    if todas_em_l1:
        def chave(i: int):
            d = delta(i, Nivel.L2)
            return (0, 0, i) if d is None else (1, d, i)  # None ordena antes de qualquer valor

        promover(sorted(comuns, key=chave), Nivel.L2, inf)

    return Plano(niveis=niveis, omitidas_a_partir=omitidas_a_partir, reserva_de_recentes=reserva_de_recentes)
