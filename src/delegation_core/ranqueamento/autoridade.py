"""Autoridade de uma nota na busca: um fator limitado que desempata a favor do que e mantido.

Porte de `PageAuthority` em `crates/ai-memory-store/src/reader.rs` do ai-memory (MIT,
Fabio Akita).

A relevancia continua mandando: mesmo a nota mais mantida ganha no maximo 1,5 vez, e
metadado de baixa autoridade explicito fica em no minimo 0,55 vez em vez de tirar a
nota da busca. O fator soma:

- **tipo** da nota: regra e decisao +0,15; procedimento, correcao e preferencia +0,12;
  conceito e vaga +0,07; sessao -0,15.
- **camada**: semantica e procedural +0,10; episodica -0,08; trabalho -0,03.
- **fixada**: +0,08.
- **etiquetas**: `canonical` ou `source-of-truth` +0,20, `active` +0,05; e as negativas
  limitam o fator: `do-not-answer-from` e `test-fixture` em 0,55, `superseded` em 0,65,
  `historical` em 0,80.

Sessao e a unica que a busca por "o que fizemos naquela vez" deve achar: quando a
pergunta e sobre uma sessao passada, a penalidade volta e ainda ganha um bonus
(`fator_para`). Quem decide e `eh_pergunta_de_sessao`, por marcadores de texto, sem modelo.

Pacote independente: so a biblioteca padrao e `texto_bytes`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..texto_bytes import aparar, eh_alfabetico

PISO = 0.55
TETO = 1.50

CANDIDATOS_MULTIPLICADOR = 4
CANDIDATOS_MINIMO = 20
CANDIDATOS_EXTRA_MAXIMO = 300

_AJUSTE_DE_TIPO = {
    "rule": 0.15, "decision": 0.15,
    "procedure": 0.12, "gotcha": 0.12, "preference": 0.12,
    "concept": 0.07, "slot": 0.07,
    "session": -0.15,
}
_AJUSTE_DE_CAMADA = {"semantic": 0.10, "procedural": 0.10, "episodic": -0.08, "working": -0.03}


@dataclass(frozen=True)
class Autoridade:
    fator: float
    #: Penalidade que a nota carrega por ser uma sessao (0,0 para os outros tipos).
    penalidade_de_sessao: float

    def fator_para(self, busca_de_sessao: bool, bonus: float) -> float:
        """O fator quando a pergunta foi roteada para recordar uma sessao passada."""
        if busca_de_sessao and self.penalidade_de_sessao > 0.0:
            return min(max(self.fator + self.penalidade_de_sessao + bonus, PISO), TETO)
        return self.fator

    def ajustar_posto(self, posto: float) -> float:
        return multiplicar_posto(posto, self.fator)


def normalizar_etiqueta(etiqueta: str) -> str:
    return "".join(c.lower() if "A" <= c <= "Z" else c for c in aparar(etiqueta)).replace("_", "-")


def etiquetas_de(frontmatter) -> list[str]:
    """As etiquetas do frontmatter, normalizadas. Fora de lista de textos, nenhuma."""
    if not isinstance(frontmatter, dict):
        return []
    etiquetas = frontmatter.get("tags")
    if not isinstance(etiquetas, list):
        return []
    return [normalizar_etiqueta(t) for t in etiquetas if isinstance(t, str)]


def autoridade_da_nota(caminho: str, tipo: str, camada: str, fixada: bool, frontmatter=None) -> Autoridade:
    """`PageAuthority::from_stored`."""
    fator = 1.0
    ajuste_tipo = _AJUSTE_DE_TIPO.get(tipo, 0.0)
    ajuste_camada = _AJUSTE_DE_CAMADA.get(camada, 0.0)
    fator += ajuste_tipo + ajuste_camada
    penalidade = -(ajuste_tipo + min(ajuste_camada, 0.0)) if tipo == "session" else 0.0
    if fixada:
        fator += 0.08
    if caminho.startswith("_lint/"):
        fator -= 0.20
    elif caminho.startswith("investigations/"):
        fator -= 0.05

    etiquetas = etiquetas_de(frontmatter)
    if "canonical" in etiquetas or "source-of-truth" in etiquetas:
        fator += 0.20
    if "active" in etiquetas:
        fator += 0.05
    # Etiqueta negativa e instrucao explicita: limita o fator, mas nunca tira a nota da busca.
    if "do-not-answer-from" in etiquetas or "test-fixture" in etiquetas:
        fator = min(fator, 0.55)
    elif "superseded" in etiquetas:
        fator = min(fator, 0.65)
    elif "historical" in etiquetas:
        fator = min(fator, 0.80)
    return Autoridade(fator=min(max(fator, PISO), TETO), penalidade_de_sessao=penalidade)


# Marcadores de `retrieval_tuning.rs`, procurados na pergunta em minuscula. Os chineses casam como
# trecho de texto; os latinos casam por palavra inteira, para "now" nunca disparar dentro de "known".
_SESSAO_ZH = (
    "之前", "上次", "上回", "上一次", "那次", "那回", "前几天", "前天", "昨天", "那天", "上周", "上星期", "上个月",
    "的会话", "次会话", "个会话", "会话里", "会话中", "历史会话", "当时我们", "我们当时",
)
_SESSAO_EN = (
    "last time", "last session", "previous session", "earlier session", "that session", "the session where", "yesterday",
    "the other day", "last week", "when we", "we did", "did we", "what did we", "how did we", "back then", "earlier we", "previously",
)
_SESSAO_PT = (
    "última sessão", "ultima sessao", "última sessao", "ultima sessão", "sessão anterior", "sessao anterior", "onde paramos ontem",
    "decisão anterior", "decisao anterior",
)


def _com_espacos_nas_pontas(minuscula: str) -> str:
    """`latin_word_padded`: tudo que nao e letra ou digito latino vira espaco, e as pontas levam um."""
    saida = [" "]
    for c in minuscula:
        saida.append(c if (c.isascii() and c.isalnum()) or (not c.isascii() and eh_alfabetico(c)) else " ")
    saida.append(" ")
    return "".join(saida)


def eh_pergunta_de_sessao(consulta: str) -> bool:
    """`is_session_recall_query`: a pergunta quer recordar uma sessao passada? Um falso positivo custa
    algumas posicoes no ranque, nao uma resposta errada."""
    minuscula = consulta.lower()
    if any(m in minuscula for m in _SESSAO_ZH):
        return True
    rodeada = _com_espacos_nas_pontas(minuscula)
    return any(f" {m} " in rodeada for m in _SESSAO_EN + _SESSAO_PT)


def multiplicar_posto(posto: float, multiplicador: float) -> float:
    """`apply_rank_multiplier`: multiplicador maior sempre melhora o posto, em qualquer convencao.

    Posto fundido por RRF e a nota negada (<= 0); posto bruto de FTS e positivo.
    """
    if posto <= 0.0:
        return posto * multiplicador
    return posto / multiplicador


def limite_de_candidatos(limite: int) -> int:
    """`authority_candidate_limit`: quantos candidatos ler para reordenar e ainda devolver `limite`."""
    if limite == 0:
        return 0
    return min(max(limite * CANDIDATOS_MULTIPLICADOR, CANDIDATOS_MINIMO), limite + CANDIDATOS_EXTRA_MAXIMO)
