"""Token e cabecalho que os testes da API do dashboard apresentam.

A API exige `Authorization: Bearer` em toda requisicao menos no preflight CORS.
O fixture autouse de conftest.py instala TOKEN no servidor; cada chamada de
teste manda AUTH de forma explicita, de modo que um teste que esquecesse a
cabecalho falharia com 401 em vez de passar por uma porta aberta.
"""
TOKEN = "token-de-teste-do-dashboard"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
