"""Trechos extrativos de uma nota: o L0 (curto) e o L1 (longo), sem modelo e sem I/O.

Porte de `crates/ai-memory-core/src/excerpt.rs` do ai-memory (MIT, Fabio Akita), com
`is_metadata_field` de `profile.rs`.

O resumo de inicio de sessao encolhe cada nota fixa a um trecho. O L0 prefere o
`abstract:` do frontmatter, o L1 prefere o `summary:`; sem eles, os dois leem a prosa
com que a nota abre, atravessando paragrafos e listas, e pulam titulos, linhas `---`,
os campos de metadado de ADR (`**Status:** Aceita`) e o rodape que a compactacao grava.
Uma nota de regras costuma abrir com uma frase sobre si mesma; ler adiante e o que poe
as primeiras regras no trecho.

Limites em bytes UTF-8 (256 e 500), com reticencias dentro do limite.

Pacote independente: so a biblioteca padrao e `texto_bytes`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..texto_bytes import (
    aparar,
    bytes_de,
    colapsar_espacos,
    cortar_em_bytes,
    dividir_espacos,
    eh_espaco,
    linhas,
    truncar_utf8,
)

BRIEF_L0_MAX_BYTES = 256
BRIEF_L1_MAX_BYTES = 500
PROSE_SCAN_MAX_BYTES = 16 * 1024
COMPACTION_FOOTER_PREFIX = "_Extractively compacted from a cold episodic page"

FIELD_LABEL_MAX_WORDS = 3
ADR_METADATA_LABELS = frozenset({
    "status", "date", "deciders", "decision-makers", "authors", "author", "owner", "owners",
    "supersedes", "superseded by", "consulted", "informed", "tags", "last updated", "reviewers",
})


@dataclass(frozen=True)
class Trecho:
    l0: str | None = None
    l1: str | None = None


def _minuscula_ascii(texto: str) -> str:
    return "".join(c.lower() if "A" <= c <= "Z" else c for c in texto)


def _campo_rotulado(linha: str) -> tuple[str, str] | None:
    """O rotulo e o valor de uma linha que abre com rotulo em destaque (`**Status:** Aceita`)."""
    resto = aparar(linha).lstrip("-*_ ")
    for fecha in (":**", "**:", ":__", "__:"):
        if fecha not in resto:
            continue
        rotulo, valor = resto.split(fecha, 1)
        palavras = len(dividir_espacos(rotulo))
        simples = not any(c in "*_.!?:`" for c in rotulo)
        if 1 <= palavras <= FIELD_LABEL_MAX_WORDS and simples:
            return aparar(rotulo), aparar(valor.lstrip("*_"))
    return None


def eh_campo_de_metadado(linha: str) -> bool:
    """`is_metadata_field`: so o rotulo decide. `**Gerenciador de pacotes:** pnpm` e afirmacao."""
    achado = _campo_rotulado(linha)
    if achado is None:
        return False
    return _minuscula_ascii(colapsar_espacos(achado[0])) in ADR_METADATA_LABELS


def _cabeca(linha: str) -> str:
    """O comeco da linha, o bastante para qualquer rotulo: nao custa ler uma linha de kilobytes."""
    return cortar_em_bytes(linha, 256)


def prosa_de_abertura(corpo: str) -> str | None:
    """A prosa com que o corpo abre, em espacos simples, lida entre paragrafos e itens de lista."""
    corpo = cortar_em_bytes(corpo, PROSE_SCAN_MAX_BYTES)
    prosa: list[str] = []
    n = 0
    for bloco in corpo.split("\n\n"):
        bloco = aparar(bloco)
        if bloco.startswith(COMPACTION_FOOTER_PREFIX):
            continue
        for linha in (aparar(x) for x in linhas(bloco)):
            if not linha or linha.startswith("#") or linha == "---" or eh_campo_de_metadado(_cabeca(linha)):
                continue
            espaco = n > 0
            for ch in linha:
                if eh_espaco(ch):
                    espaco = n > 0
                    continue
                if espaco:
                    prosa.append(" ")
                    n += 1
                    espaco = False
                prosa.append(ch)
                n += len(ch.encode("utf-8"))
                if n > BRIEF_L1_MAX_BYTES:
                    return "".join(prosa)
    return "".join(prosa) if prosa else None


def _nao_vazio(frontmatter, chave: str) -> str | None:
    if not isinstance(frontmatter, dict):
        return None
    v = frontmatter.get(chave)
    if not isinstance(v, str):
        return None
    v = aparar(v)
    return v or None


def trecho_da_nota(frontmatter, corpo: str) -> Trecho:
    """`excerpt_from_page`: L0 e L1 de uma nota a partir do frontmatter (dict) e do corpo."""
    abstract = _nao_vazio(frontmatter, "abstract")
    resumo = _nao_vazio(frontmatter, "summary")

    def para(primeiro, segundo, limite):
        texto = primeiro or segundo or prosa_de_abertura(corpo)
        return None if texto is None else truncar_utf8(colapsar_espacos(texto), limite)

    return Trecho(l0=para(abstract, resumo, BRIEF_L0_MAX_BYTES), l1=para(resumo, abstract, BRIEF_L1_MAX_BYTES))


__all__ = ["Trecho", "trecho_da_nota", "prosa_de_abertura", "eh_campo_de_metadado", "bytes_de"]
