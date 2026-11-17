"""O painel e a API dele falam por string, e nada comparava os dois lados.

## Por que este arquivo existe

`dashboard_api.py` decide a rota por comparacao literal
(`parsed.path == "/api/vault/tree"`), e o `main.js` monta a URL como texto. Nao
ha tipo, schema nem import ligando um ao outro: renomear uma rota no Python nao
quebra nada em lugar nenhum, e o sintoma aparece como painel vazio.

Isso nao e hipotetico neste repo. Em 25/09/2026 o `main.js` caia na porta 8182
enquanto a API respondia na 8788, e **nao havia erro em lugar nenhum**: a
interface abria com "Vault unavailable" e "Graph unavailable". A porta ja tem
guarda propria em `test_porta_do_painel.py`. Este arquivo guarda o outro lado da
mesma fronteira, que sao as rotas.

## O que cada teste guarda

1. **Toda rota que a frente chama e servida.** Esta e a direcao que quebra o
   usuario, e a assercao e dura.
2. **Rota servida e nunca chamada precisa ser declarada.** Nao e defeito, o
   backend tambem atende CLI e MCP. Mas crescer a superficie do backend sem
   ninguem decidir o que a interface faz com ela e como se acumula capacidade
   morta, e este repo ja tem historico disso: `detect_incremental` estava
   implementada por inteiro com zero chamadores.

## Como as chamadas sao lidas

A frente chama de duas formas, e as duas contam:

- literal: `apiGet("/api/vault/tree")`
- por template: `apiPost(\\`/api/llama/${action}\\`)`, que cobre `start` e `stop`

Do template so o **prefixo** antes da interpolacao e conhecido, entao ele casa
por prefixo. Ler so os literais diria que `/api/llama/start` nao tem chamador, o
que e falso.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
API_PY = RAIZ / "src" / "delegation_core" / "dashboard_api.py"
MAIN_JS = RAIZ / "dashboard" / "src" / "main.js"

#: Servidas de proposito sem interface. Cada entrada precisa de motivo escrito.
#:
#: - `/api/graphs/affected`: consulta de raio de impacto ("se X mudar, o que
#:   quebra"). Existe no backend, na CLI (`delegation-core graph affected`) e
#:   como ferramenta MCP (`graph_affected`), e o painel nao expoe. Medido em
#:   26/09/2026: nenhuma ocorrencia de "affected" no `index.html` nem no
#:   `main.js`. Fica declarada aqui ate alguem decidir se vira painel ou nao.
#: - `/api/cores/skill`: consulta direta de detalhes de uma skill individual por ID.
#:   O dashboard web consome `/api/cores/skills` (busca agregada), mantendo esta
#:   rota para consultas programáticas pontuais e extensões.
SEM_INTERFACE_DE_PROPOSITO = {
    "/api/graphs/affected",
    "/api/cores/skill",
}


def _servidas() -> set[str]:
    texto = API_PY.read_text(encoding="utf-8")
    achadas = set(re.findall(r'parsed\.path\s*==\s*"(/api/[^"]+)"', texto))
    assert achadas, "nenhuma rota encontrada no dashboard_api.py; o padrao mudou"
    return achadas


def _chamadas() -> tuple[set[str], set[str]]:
    """Devolve (literais, prefixos de template) que a frente chama."""
    texto = MAIN_JS.read_text(encoding="utf-8")
    literais: set[str] = set()
    prefixos: set[str] = set()
    for m in re.finditer(r'api(?:Get|Post)\(\s*([`"\'])(/api/[^`"\']*)\1', texto):
        alvo = m.group(2)
        if "${" in alvo:
            prefixos.add(re.sub(r"\$\{[^}]*\}.*$", "", alvo).split("?")[0])
        else:
            literais.add(alvo.split("?")[0])
    assert literais or prefixos, "nenhuma chamada encontrada no main.js; o padrao mudou"
    return literais, prefixos


def _coberta(rota: str, literais: set[str], prefixos: set[str]) -> bool:
    if rota in literais:
        return True
    return any(rota.startswith(p) for p in prefixos if p)


pytestmark = pytest.mark.skipif(
    not (API_PY.is_file() and MAIN_JS.is_file()),
    reason="o painel ou a API dele nao estao neste checkout",
)


def test_toda_rota_que_a_frente_chama_e_servida():
    """A direcao que quebra o usuario.

    Uma rota chamada e nao servida devolve 404 com corpo JSON, e o painel
    mostra o estado vazio do painel correspondente. Nenhum erro sobe.
    """
    servidas = _servidas()
    literais, prefixos = _chamadas()

    orfas = sorted(
        r for r in literais
        if r not in servidas and not any(s.startswith(r) for s in servidas)
    )
    assert not orfas, (
        f"a frente chama rotas que o dashboard_api.py nao serve: {orfas}. "
        "Ou a rota foi renomeada no Python, ou a chamada tem erro de digitacao; "
        "o sintoma no painel e um estado vazio, sem erro.")

    prefixos_orfaos = sorted(
        p for p in prefixos
        if p and not any(s.startswith(p) for s in servidas)
    )
    assert not prefixos_orfaos, (
        f"a frente monta URLs sob prefixos que nao existem no backend: "
        f"{prefixos_orfaos}")


def test_rota_servida_sem_interface_precisa_estar_declarada():
    """Capacidade sem fio e como este repo acumula codigo morto.

    Nao falha por existir rota sem interface: o backend tambem atende CLI e
    MCP. Falha por existir uma que **ninguem decidiu**, que e diferente.
    """
    servidas = _servidas()
    literais, prefixos = _chamadas()

    sem_uso = {r for r in servidas if not _coberta(r, literais, prefixos)}
    novas = sorted(sem_uso - SEM_INTERFACE_DE_PROPOSITO)
    assert not novas, (
        f"rotas novas sem interface e sem decisao: {novas}. "
        "Decida se o painel expoe, e se nao expoe, declare em "
        "SEM_INTERFACE_DE_PROPOSITO com o motivo escrito.")


def test_a_declaracao_nao_pode_envelhecer():
    """Se a rota declarada ganhar interface ou sumir, a declaracao vira ruido.

    Sem esta guarda, a lista acumularia entradas que descrevem um mundo que
    nao existe mais, e a proxima pessoa confiaria nelas.
    """
    servidas = _servidas()
    literais, prefixos = _chamadas()

    for rota in sorted(SEM_INTERFACE_DE_PROPOSITO):
        assert rota in servidas, (
            f"{rota} esta declarada como servida sem interface, mas o backend "
            "nao serve mais essa rota; tire da lista")
        assert not _coberta(rota, literais, prefixos), (
            f"{rota} ganhou interface no painel; tire da lista, a declaracao "
            "agora mente")


def test_o_template_conta_como_chamada():
    """Guarda do proprio extrator, e ele ja erraria sem isto.

    `/api/llama/start` so aparece no `main.js` dentro de
    `apiPost(\\`/api/llama/${action}\\`)`. Ler so literais diria que a rota nao
    tem chamador, e a lista de "sem interface" cresceria com uma rota que e
    chamada o tempo todo.
    """
    literais, prefixos = _chamadas()
    assert "/api/llama/start" not in literais, (
        "o teste abaixo deixa de provar algo se a chamada virar literal")
    assert _coberta("/api/llama/start", literais, prefixos), (
        "o extrator perdeu a chamada por template")
