"""A varredura de esquecimento: quais notas expiraram, quais esfriaram, e o que fazer com elas.

Porte da parte pura de `crates/ai-memory-consolidate/src/sweep.rs` do ai-memory (MIT, Fabio
Akita): `is_decayable`, `cold_entry_for` e a ordem dos passos de `run_sweep_at`. Aqui nao se
toca em disco: entra a lista de notas com seus contadores, sai um plano. Quem aplica o plano
(`envelhecimento_vault`) guarda antes o texto inteiro no historico de versoes.

## As regras

- **Expiracao (TTL)**: uma nota com `expires_at` no passado sai, qualquer que seja a camada e
  mesmo fixada. Uma data de validade escrita e uma declaracao mais explicita que um pin.
- **Esquecimento**: so a camada episodica esfria. Semantica, procedural e de trabalho ficam,
  e uma nota fixada (`fixada` ou `pinned: true` no frontmatter) fica em qualquer camada.
- **Fria** e uma nota episodica cuja retencao (`pontuacao`) caiu abaixo do limiar.
- **Compactar ou esquecer**: com `compactar_frias` (o padrao), uma nota fria vira resumo mais
  fatos duraveis em vez de sumir. Uma nota ja compactada e terminal: nao se compacta de novo
  e nao se esquece, porque o residuo e justamente o que se quis guardar. Com a compactacao
  desligada, a fria e esquecida (como no original, mesmo se ja estava compactada).

O que o original faz e este porte nao: agrupar notas frias quase iguais por DBSCAN (A3, pede
vetores guardados), apagar observacoes e livros-razao de eventos (nao ha equivalente aqui) e
limpar lapides apos `hard_delete_after_days` (o historico de versoes tem a propria poda).

Pacote independente: so a biblioteca padrao e `retencao`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .retencao import Parametros, pontuacao

US_POR_DIA = 86_400_000_000.0


@dataclass(frozen=True)
class Nota:
    """`DecayCandidate`: o que a varredura precisa saber de uma nota."""

    caminho: str
    camada: str
    atualizada_em_us: int
    fixada: bool = False
    acessos: int = 0
    ultimo_acesso_us: int | None = None
    frontmatter: dict = field(default_factory=dict)
    expira_em_us: int | None = None
    saliencia: float | None = None
    compactada_em_us: int | None = None
    leitores_distintos: int = 0


@dataclass(frozen=True)
class Fria:
    """`ColdEntry` mais o caminho: uma nota episodica abaixo do limiar."""

    caminho: str
    retencao: float
    idade_dias: float
    acessos: int
    compactada: bool


@dataclass(frozen=True)
class Expirada:
    caminho: str
    expirou_em_us: int


@dataclass
class Plano:
    avaliadas: int = 0
    expiradas: list[Expirada] = field(default_factory=list)
    compactar: list[Fria] = field(default_factory=list)
    esquecer: list[Fria] = field(default_factory=list)

    @property
    def vazio(self) -> bool:
        return not (self.expiradas or self.compactar or self.esquecer)


def dias_decorridos(agora_us: int, antes_us: int) -> float:
    """`elapsed_days`: nunca negativo (relogio atrasado ou nota do futuro contam como zero)."""
    return max(0.0, (agora_us - antes_us) / US_POR_DIA)


def e_decaivel(n: Nota) -> bool:
    """`is_decayable`: so a camada episodica, e nunca uma nota fixada (pelo campo ou pelo frontmatter)."""
    if n.camada != "episodic":
        return False
    if n.fixada:
        return False
    if isinstance(n.frontmatter, dict) and n.frontmatter.get("pinned") is True:
        return False
    return True


def entrada_fria(n: Nota, p: Parametros, agora_us: int, peso_amplitude: float = 0.0) -> Fria | None:
    """`cold_entry_for`: a nota, se for decaivel e estiver abaixo do limiar; senao `None`."""
    if not e_decaivel(n):
        return None
    idade = dias_decorridos(agora_us, n.atualizada_em_us)
    desde_acesso = None if n.ultimo_acesso_us is None else dias_decorridos(agora_us, n.ultimo_acesso_us)
    nota = pontuacao(p, n.camada, idade, n.acessos, desde_acesso, n.saliencia, n.leitores_distintos, peso_amplitude)
    if nota < p.limiar_frio:
        return Fria(n.caminho, nota, idade, n.acessos, n.compactada_em_us is not None)
    return None


def planejar(notas, p: Parametros, agora_us: int, *, compactar_frias: bool = True, peso_amplitude: float = 0.0) -> Plano:
    """O plano de uma varredura sobre `notas`. Nao altera nada."""
    if not (math.isfinite(peso_amplitude) and peso_amplitude >= 0.0):
        raise ValueError("o peso de amplitude precisa ser finito e nao negativo")
    plano = Plano()
    for n in notas:
        plano.avaliadas += 1
        if n.expira_em_us is not None and n.expira_em_us <= agora_us:
            plano.expiradas.append(Expirada(n.caminho, n.expira_em_us))
            continue
        fria = entrada_fria(n, p, agora_us, peso_amplitude)
        if fria is None:
            continue
        if compactar_frias:
            if fria.compactada:
                continue
            plano.compactar.append(fria)
        else:
            plano.esquecer.append(fria)
    return plano
