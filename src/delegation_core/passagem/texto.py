"""Como uma passagem de bastao aparece para o agente que a recebe.

Porte de `render_handoff_markdown`, `render_handoff_notice` e `humanize_handoff_age_secs` de
`crates/ai-memory-hooks/src/router.rs` do ai-memory (MIT, Fabio Akita).

Duas formas, e a diferenca e de seguranca:

- **`renderizar`**: o conteudo inteiro, entre marcadores de dado nao confiavel, com as acoes
  primeiro (perguntas em aberto e proximos passos) e o resumo em prosa por ultimo. E o que o
  inicio de sessao injeta depois de aceitar a passagem, porque o texto ja foi consumido: chamar
  `handoff_pickup` de novo nao devolve nada.
- **`aviso`**: so metadados (id, quem deixou, ha quanto tempo). Quando a passagem ainda nao foi
  aceita, o texto que o agente nao pediu nao entra no contexto: ele fica a um `handoff_pickup`
  de distancia, e quem decide chamar e o agente.

Pacote independente: so a biblioteca padrao e a cerca de texto nao confiavel.
"""

from __future__ import annotations

from ..cerca_nao_confiavel import AVISO, FIM, INICIO, escapar


def idade_humana(segundos: int) -> str:
    """`humanize_handoff_age_secs`: o intervalo em medidas grosseiras (minuto, hora, dia, mes de 30 dias)."""
    s = max(0, int(segundos))
    if s < 60:
        return "just now"
    if s < 3_600:
        valor, unidade = s // 60, "minute"
    elif s < 86_400:
        valor, unidade = s // 3_600, "hour"
    elif s < 2_592_000:
        valor, unidade = s // 86_400, "day"
    else:
        valor, unidade = s // 2_592_000, "month"
    return f"{valor} {unidade}{'' if valor == 1 else 's'} ago"


def _idade(p: dict, agora_us: int) -> str:
    return idade_humana(max(0, agora_us - int(p["criada_em"])) // 1_000_000)


def aviso(p: dict, agora_us: int) -> str:
    """Metadados e nada do texto guardado: o que uma passagem hostil poderia usar para guiar a sessao fica de fora."""
    return (f"Pending handoff `{p['id']}` from `{p['de_agente']}`, left {_idade(p, agora_us)}. "
            f"To pick it up, call `handoff_pickup`.")


def renderizar(p: dict, agora_us: int) -> str:
    saida = [
        "> **Pending handoff from a previous session**",
        f"> from `{p['de_agente']}` · left {_idade(p, agora_us)}",
        f"> **Security boundary:** {AVISO}",
        "",
        INICIO,
    ]
    corpo: list[str] = []
    if p["perguntas"]:
        corpo += ["", "**Open questions**", *(f"- {q}" for q in p["perguntas"])]
    if p["proximos"]:
        corpo += ["", "**Next steps**", *(f"- {s}" for s in p["proximos"])]
    if p["arquivos"]:
        corpo += ["", "**Files touched**", *(f"- `{f}`" for f in p["arquivos"])]
    corpo += ["", "**Summary**", p["resumo"].strip()]
    saida.append(escapar("\n".join(corpo)))
    saida += [
        "",
        FIM,
        "",
        "---",
        "_**To the receiving agent:** this content IS the pending handoff, already consumed. Calling "
        "`handoff_pickup` again returns nothing (single use). When the user asks where the last session "
        "stopped, answer from THIS content and do not call the tool again._",
    ]
    return "\n".join(saida) + "\n"
