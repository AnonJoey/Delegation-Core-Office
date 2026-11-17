"""Retencao de uma nota: o quanto vale guardar, em funcao da idade e do uso.

Porte de `crates/ai-memory-store/src/decay.rs` do ai-memory (MIT, Fabio Akita).
A formula e pura, e o ai-memory a adaptou do agentmemory:

    retencao = saliencia * exp(-lambda * idade_em_dias)
             + sigma * ln(1 + acessos) * exp(-mu * dias_desde_o_ultimo_acesso) * amplitude

- Uma nota nova e nunca usada vale a sua saliencia (1,0). Sem uso, cai para menos
  de 0,20 em cerca de 80 dias (lambda 0,02, meia-vida de 35 dias).
- Cada leitura reforca: `sigma * ln(1 + acessos)` cresce devagar com a contagem e
  esquece com `mu` (meia-vida do reforco: 17 dias).
- `amplitude` so conta quando ha mais de um leitor distinto e o peso e positivo; no
  delegation-core, que tem um operador, ela e 1 e o termo some.
- A saliencia anda de 0,25 em 0,25 entre 0,25 e 2,0 com o voto de utilidade.

Parametros por camada (`lambda_por_camada`) deixam, por exemplo, a camada de trabalho
esquecer mais depressa que a episodica. O padrao e um lambda so, o mesmo do original.

Paridade com o original: `scripts/paridade_ai_memory.py` roda estas funcoes e as do
ai-memory (compiladas de `scripts/oraculo_ai_memory`) nos mesmos casos.

Pacote independente: so a biblioteca padrao.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

CAMADAS = ("working", "episodic", "semantic", "procedural")

SALIENCIA_MIN = 0.25
SALIENCIA_MAX = 2.0
SALIENCIA_PASSO = 0.25


def lambda_da_meia_vida(dias: float) -> float:
    """`lambda_from_half_life_days`: lambda = ln(2) / meia-vida. Quem chama valida `dias > 0`."""
    if dias == 0:
        return math.inf
    return math.log(2) / dias


@dataclass(frozen=True)
class Parametros:
    """`DecayParams`. Os nomes das camadas sao os do ai-memory (working, episodic, semantic, procedural)."""

    lamb: float = 0.02
    sigma: float = 0.6
    mu: float = 0.04
    saliencia_padrao: float = 1.0
    limiar_frio: float = 0.20
    apagar_apos_dias: int = 180
    lambda_por_camada: dict = field(default_factory=dict)

    def lambda_de(self, camada: str) -> float:
        v = self.lambda_por_camada.get(camada)
        return self.lamb if v is None else v


def pontuacao(p: Parametros, camada: str, idade_dias: float, acessos: int,
             dias_desde_acesso: float | None, saliencia: float | None = None,
             leitores_distintos: int = 0, peso_amplitude: float = 0.0) -> float:
    """`retention_score_with_breadth`. Maior = vale guardar."""
    sal = p.saliencia_padrao if saliencia is None else saliencia
    # Peso invalido (NaN, infinito, negativo) desliga o bonus em vez de estragar a nota.
    if not (math.isfinite(peso_amplitude) and peso_amplitude >= 0.0):
        peso_amplitude = 0.0
    termo_tempo = sal * math.exp(-p.lambda_de(camada) * idade_dias)
    amplitude = 1.0 + peso_amplitude * math.log1p(float(max(leitores_distintos, 1)) - 1.0)
    if dias_desde_acesso is None:
        termo_acesso = 0.0
    else:
        termo_acesso = p.sigma * math.log(1.0 + float(acessos)) * math.exp(-p.mu * dias_desde_acesso) * amplitude
    return termo_tempo + termo_acesso


def saliencia_depois_do_voto(p: Parametros, atual: float | None, voto: str) -> float:
    """`salience_after_feedback`. Votos: helpful, not_helpful, stale, wrong.

    `stale` e `wrong` vao direto ao piso: dizem que o conteudo nao merece mais confianca,
    e a retencao deixa de segura-lo enquanto ele espera uma revisao.
    """
    atual = p.saliencia_padrao if atual is None else atual
    if voto == "helpful":
        prox = atual + SALIENCIA_PASSO
    elif voto == "not_helpful":
        prox = atual - SALIENCIA_PASSO
    elif voto in ("stale", "wrong"):
        prox = SALIENCIA_MIN
    else:
        raise ValueError(f"voto desconhecido: {voto!r}")
    return min(max(prox, SALIENCIA_MIN), SALIENCIA_MAX)
