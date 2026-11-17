"""O id de processo entra cru num `onclick` do painel, entao a FORMA dele importa.

## O que foi medido em 26/09/2026

`dashboard/src/main.js`, linhas 1141 a 1144, monta quatro botoes assim::

    onclick="updateProcessStatus('${p.process_id}', 'paused')"

O valor entra **cru**, dentro de uma string JavaScript, dentro de um atributo
HTML. E tres linhas acima, na mesma funcao, o mesmo valor e escapado para
exibicao::

    <code>${escapeHtml(p.process_id)}</code>

Ou seja, quem escreveu sabia escapar e nao escapou ali.

## Por que isto NAO e defeito vivo

`tracker.py:60` gera `"proc_" + uuid.uuid4().hex[:6]`. Hexadecimal nao tem
aspas, nao tem `<`, nao tem barra invertida: nao existe id capaz de sair do
literal. Conferido, e nao suposto.

## Entao por que este teste existe

Porque a seguranca daquele `onclick` **depende inteiramente do formato do id**,
e nada dizia isso. Trocar a geracao para aceitar id vindo do usuario, ou para
usar o nome do processo como id, ou para aceitar um id importado de outro
sistema, abriria o buraco sem ninguem ligar uma coisa na outra: o painel fica
em outro arquivo, em outra linguagem, e o teste dele nao existe.

**A correcao estrutural seria trocar o `onclick` por atributo `data-` e
listener delegado**, que tira a classe inteira do problema em vez de depender
do formato. Ela nao foi feita nesta noite por uma razao escrita: o trabalho
correu sem navegador, e trocar a ligacao de quatro botoes sem poder ver se eles
continuam funcionando e pior troca que a que se evita.

Enquanto o `onclick` estiver la, este teste e o que segura a premissa.
"""

from __future__ import annotations

import re

import pytest

from delegation_core.tracker import ProcessTracker


#: `proc_` seguido so de hexadecimal. Nada aqui pode fechar um literal JS nem
#: abrir uma tag.
_FORMA = re.compile(r"^proc_[0-9a-f]+$")

#: Caracteres que quebrariam o `onclick`. Qualquer um deles num id e o buraco.
_PERIGOSOS = "'\"<>\\`&\n\r"


@pytest.fixture
def rastreador(tmp_path):
    return ProcessTracker(tmp_path / "processes.json")


def test_o_id_gerado_tem_a_forma_esperada(rastreador):
    p = rastreador.create("Um processo qualquer", "descricao", "a, b")
    assert _FORMA.match(p["id"]), (
        f"id {p['id']!r} fora da forma proc_<hex>; o painel interpola este "
        "valor cru num onclick, e a seguranca disso depende da forma")


def test_o_id_nao_contem_caractere_que_quebre_o_onclick(rastreador):
    """O que de fato importa, dito diretamente e nao por regex.

    Conferido por mutacao: fazer o tracker gerar id com aspas derruba este
    teste.
    """
    for titulo in ("Normal", "Com 'aspas' no nome", 'Com "aspas duplas"',
                   "Com <tag> e & no nome", "Com \\barra e `crase`"):
        p = rastreador.create(titulo, "", "")
        for c in _PERIGOSOS:
            assert c not in p["id"], (
                f"o id {p['id']!r} contem {c!r}, que fecha o literal do "
                f"onclick no painel; o titulo era {titulo!r}")


def test_o_titulo_perigoso_nao_vaza_para_o_id(rastreador):
    """O caminho plausivel de o id virar perigoso e alguem deriva-lo do titulo.

    Hoje ele vem de `uuid.uuid4().hex`, entao o titulo nao chega perto dele. E
    isso que este teste fixa.
    """
    p = rastreador.create("'); alert(1); //", "", "")
    assert "alert" not in p["id"]
    assert _FORMA.match(p["id"])


def test_ids_diferentes_para_processos_diferentes(rastreador):
    """Guarda de base: um id constante passaria nos testes acima e quebraria
    o painel de outro jeito."""
    a = rastreador.create("um", "", "")
    b = rastreador.create("outro", "", "")
    assert a["id"] != b["id"]


def test_o_painel_ainda_interpola_cru_e_por_isso_este_arquivo_existe():
    """Se o `onclick` virar `data-` + listener, este arquivo perde a razao.

    Sem esta guarda, a correcao estrutural aconteceria e este teste ficaria
    para tras afirmando um perigo que nao existe mais, que e a mesma doenca de
    prosa velha que o `capabilities()` existe para conter.
    """
    from pathlib import Path

    main_js = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "main.js"
    if not main_js.is_file():
        pytest.skip("o painel nao esta neste checkout")

    texto = main_js.read_text(encoding="utf-8")
    cru = [l for l in texto.split("\n")
           if "onclick=" in l and "${p.process_id}" in l]
    assert cru, (
        "o painel nao interpola mais process_id cru num onclick. Se a correcao "
        "estrutural foi feita, APAGUE este arquivo: ele guarda uma premissa que "
        "deixou de existir.")
