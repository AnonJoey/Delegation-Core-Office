"""O Hub do Hugging Face sem o pedido que ninguem fez.

Medido em 27/11/2026 com `sys.addaudithook`, no huggingface_hub 2.5.0: toda chamada que monta os
cabecalhos (`build_hf_headers`), inclusive `hf_hub_download(..., local_files_only=True)`, consulta
`<endpoint>/api/agent-harnesses` para por o nome do agente no user-agent. Uma leitura "so do
cache" resolvia `huggingface.co`, num servidor que se declara local. A biblioteca pula esse passo
quando a telemetria dela esta desligada (`HF_HUB_DISABLE_TELEMETRY`).

E o mesmo caso do aviso de atualizacao do fastmcp, que o `cli.py` desliga na partida.
"""
from __future__ import annotations

import os
import sys

_VARIAVEL = "HF_HUB_DISABLE_TELEMETRY"
_LIGADO = {"1", "true", "yes", "on"}


def sem_telemetria() -> bool:
    """Desliga a telemetria do huggingface_hub, a menos que o operador tenha escolhido outra coisa.

    A variavel so e lida quando a biblioteca e importada, entao o valor tambem vai direto ao
    modulo ja carregado. Devolve True quando a telemetria ficou desligada."""
    if os.environ.get(_VARIAVEL) is None:
        os.environ[_VARIAVEL] = "1"
    desligada = os.environ[_VARIAVEL].strip().lower() in _LIGADO
    constantes = sys.modules.get("huggingface_hub.constants")
    if desligada and constantes is not None:
        constantes.HF_HUB_DISABLE_TELEMETRY = True
    return desligada
