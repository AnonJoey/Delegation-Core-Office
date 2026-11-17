"""Compactar uma nota fria: guardar o resumo e os fatos, soltar a prosa.

Porte de `crates/ai-memory-consolidate/src/compaction.rs` do ai-memory (MIT, Fabio Akita).

Em vez de apagar uma nota episodica que esfriou, troca o corpo por: um resumo de uma
linha (o `summary:`/`abstract:` do frontmatter, ou o primeiro paragrafo), a lista dos
fatos duraveis (`minerar_fatos`) e um rodape que avisa que a prosa foi tirada. O
frontmatter ganha `compacted: true` e o `abstract:` continua.

Nao destroi nada por conta propria: quem grava o resultado guarda antes o texto inteiro
no historico de versoes (`historico`), e a nota volta com `vault_note_restore`.

Pacote independente: so a biblioteca padrao.
"""

from __future__ import annotations

from ..texto_bytes import aparar, bytes_de, colapsar_espacos, cortar_em_bytes
from .fatos_duraveis import minerar_fatos

MAX_RESUMO_BYTES = 500

#: O rodape do original, palavra por palavra. O teste de paridade o usa.
RODAPE_AI_MEMORY = (
    "_Extractively compacted from a cold episodic page (A2 tier-down). The full "
    "pre-compaction body is retained in git history and the supersession chain, "
    "and can be recovered with `restore-page`._"
)

#: O rodape que o delegation-core grava. Comeca igual ao do original, e e por esse
#: comeco que `resumo_inicial.trecho` o reconhece e o pula.
RODAPE = (
    "_Extractively compacted from a cold episodic page (A2 tier-down). The full "
    "pre-compaction body is kept in the note history and can be recovered with "
    "`vault_note_restore`._"
)


def _truncar(texto: str) -> str:
    if bytes_de(texto) <= MAX_RESUMO_BYTES:
        return texto
    return cortar_em_bytes(texto, MAX_RESUMO_BYTES) + "…"


def _linha_de_resumo(fm: dict, corpo: str) -> str | None:
    for chave in ("summary", "abstract"):
        v = fm.get(chave)
        if isinstance(v, str):
            t = aparar(v)
            if t:
                return _truncar(t)
    for paragrafo in corpo.split("\n\n"):
        t = aparar(paragrafo)
        if not t or t.startswith("#"):
            continue
        colapsado = colapsar_espacos(t)
        if colapsado:
            return _truncar(colapsado)
    return None


def compactar(frontmatter, corpo: str, rodape: str = RODAPE) -> tuple[dict, str]:
    """`build_compacted_markdown`: devolve (frontmatter, corpo) da nota compactada."""
    fm = dict(frontmatter) if isinstance(frontmatter, dict) else {}
    fm["compacted"] = True
    resumo = _linha_de_resumo(fm, corpo)
    tokens = minerar_fatos(corpo)
    saida = ""
    if resumo:
        saida += resumo + "\n\n"
    if tokens:
        saida += "## Retained facts\n\n"
        for t in tokens:
            saida += "- `" + t + "`\n"
        saida += "\n"
    saida += rodape + "\n"
    return fm, saida
