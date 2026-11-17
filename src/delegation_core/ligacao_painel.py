"""O modulo server do daemon, para os paineis do dashboard que leem estado dele.

Os paineis (painel_resposta, painel_vigia) importavam o server, e o server
sobe o dashboard que importa os paineis: o ciclo server -> dashboard_api ->
painel -> server. Agora o server se entrega aqui ao carregar, e os paineis leem
os atributos na hora da chamada (quem troca `server._vault` num teste ve a
troca). Fora do daemon nao ha servidor, e os paineis dizem isso.
"""

from __future__ import annotations

_servidor = None


def ligar(servidor) -> None:
    global _servidor
    _servidor = servidor


def servidor():
    return _servidor
