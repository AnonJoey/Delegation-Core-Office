"""Aviso de progresso MCP enquanto uma ferramenta longa trabalha.

Trazido do REA (`docs/mcp-contracts.md`, "Progress and cancellation"): avisos
monotonicos, espacados, e sem porcentagem inventada. O delegation-core nao
sabe quanto falta numa manutencao ou num relink, entao o aviso diz so quantos
segundos ja passaram, com `total` ausente.

Por que: o `relink_folder` sincrono numa pasta de 31 notas passou do limite de
inatividade de 300 s do cliente MCP, que derrubou a conexao com o servidor
ainda trabalhando (AGENT_GUIDE). Se um cliente reinicia esse relogio quando
recebe progresso, o aviso evita a queda. ISSO NAO FOI MEDIDO no Claude Code:
o `_bg` com `task_status` continua sendo o caminho recomendado para pasta grande.

Sem token de progresso na chamada, `report_progress` nao manda nada; o custo
e uma tarefa assincrona a mais.
"""

from __future__ import annotations

import asyncio
import time

INTERVALO = 10.0


async def com_progresso(ctx, aguardavel, rotulo: str, intervalo: float = INTERVALO):
    """Espera `aguardavel`, avisando a cada `intervalo` segundos. Devolve o resultado dele."""
    tarefa = asyncio.ensure_future(aguardavel)
    if ctx is None:
        return await tarefa
    inicio = time.monotonic()
    while True:
        feito, _ = await asyncio.wait({tarefa}, timeout=intervalo)
        if feito:
            return tarefa.result()
        passou = round(time.monotonic() - inicio, 1)
        try:
            await ctx.report_progress(progress=passou, total=None,
                                      message=f"{rotulo}: still running after {passou:.0f}s")
        except Exception:  # noqa: BLE001 - aviso e acessorio; o trabalho segue
            pass
