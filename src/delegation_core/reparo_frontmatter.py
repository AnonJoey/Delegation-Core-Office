"""Reparo do frontmatter que nenhum leitor de YAML consegue abrir.

Medido em 04/11/2026: 352 notas do vault com frontmatter ilegivel. Tres causas
tem reparo seguro, e so essas sao tratadas:

1. Item de lista de fluxo sem aspas (`tags: [a, @b, c/[id]]`): quota cada item
   que o YAML nao le como texto simples.
2. Valor simples com `: ` no meio ou comecando por caractere reservado
   (`subtitle: Oito mudancas: preview`): quota o valor.
3. Linha solta `- ...` no nivel das chaves, depois de uma chave que ja tem
   valor: sao os itens de um `aliases:` que perdeu o cabecalho e o fecho das
   aspas (o par `data-titulo` e `titulo` que `compose_note` grava). O reparo
   os recupera como `aliases:`; se a nota ja tem `aliases:`, sao descartados.

Todo o resto devolve a nota IGUAL, com o motivo. O corpo da nota nunca e
tocado: so o bloco entre os dois `---` muda. Se depois do reparo o bloco ainda
nao abrir, o texto original volta, porque uma nota "meio reparada" e pior que
uma nota que ainda se sabe quebrada.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .notes import _LEADING_FRONTMATTER_RE, _frontmatter_parses, yaml_quote_scalar

#: Linhas soltas tratadas por nota. Mais que isso nao e um estrago pontual,
#: e um bloco que nao e frontmatter; nesse caso nao se mexe.
MAX_LINHAS_SOLTAS = 6

_CHAVE_RE = re.compile(r"^([A-Za-z_][\w.\-]*):(?:[ \t]+(.*))?$")
_RESERVADOS = ("@", "`", "%", "*", "&", "!", "|", ">")


@dataclass
class Reparo:
    texto: str
    mudou: bool = False
    avisos: list[str] = field(default_factory=list)


def _le(trecho: str):
    import yaml
    return yaml.safe_load(trecho)


def _abre(trecho: str) -> bool:
    try:
        _le(trecho)
    except Exception:  # noqa: BLE001 - qualquer recusa do leitor conta
        return False
    return True


def _itens_de_fluxo(interno: str) -> list[str]:
    """Separa por virgula no nivel zero; colchetes dentro do item nao separam."""
    itens, atual, nivel, aspas = [], [], 0, ""
    for c in interno:
        if aspas:
            atual.append(c)
            if c == aspas:
                aspas = ""
            continue
        if c in "\"'" and not "".join(atual).strip():
            aspas = c
            atual.append(c)
            continue
        if c == "[":
            nivel += 1
        elif c == "]":
            nivel -= 1
        if c == "," and nivel == 0:
            itens.append("".join(atual).strip())
            atual = []
            continue
        atual.append(c)
    ultimo = "".join(atual).strip()
    if ultimo or itens:
        itens.append(ultimo)
    return [i for i in itens if i != ""]


def _quota_item(item: str) -> str:
    if item[:1] in "\"'" and len(item) >= 2 and item[-1] == item[0]:
        return item
    try:
        if _le(f"k: [{item}]") == {"k": [item]}:
            return item
    except Exception:  # noqa: BLE001
        pass
    return yaml_quote_scalar(item)


def _linha_de_fluxo(chave: str, valor: str) -> str | None:
    if not valor.endswith("]"):
        return None
    itens = _itens_de_fluxo(valor[1:-1])
    linha = f"{chave}: [{', '.join(_quota_item(i) for i in itens)}]"
    return linha if _abre(linha) else None


def reparar_frontmatter(texto: str) -> Reparo:
    """Tenta abrir o frontmatter de `texto`. Devolve o texto, se mudou e os avisos."""
    if _frontmatter_parses(texto):
        return Reparo(texto)
    m = _LEADING_FRONTMATTER_RE.match(texto)
    if m is None:
        return Reparo(texto)

    novas: list[str] = []
    avisos: list[str] = []
    soltas: list[str] = []
    ponto_das_soltas = -1
    lista_aberta = False
    ja_tem_aliases = any(_CHAVE_RE.match(ln) and ln.startswith("aliases:")
                         for ln in m.group(1).split("\n"))

    def desistir(motivo: str) -> Reparo:
        return Reparo(texto, False, avisos + [f"sem reparo seguro: {motivo}"])

    for linha in m.group(1).split("\n"):
        if not linha.strip() or linha[:1] in " \t":
            novas.append(linha)
            continue
        achou = _CHAVE_RE.match(linha)
        if achou is None:
            if linha.startswith("- ") and not lista_aberta:
                if len(soltas) >= MAX_LINHAS_SOLTAS:
                    return desistir(f"mais de {MAX_LINHAS_SOLTAS} linhas soltas")
                if not soltas:
                    ponto_das_soltas = len(novas)
                soltas.append(linha)
                continue
            if linha.startswith("- "):
                novas.append(linha)
                continue
            return desistir(f"linha que nao e chave nem lista: {linha[:40]!r}")
        chave, valor = achou.group(1), (achou.group(2) or "").strip()
        lista_aberta = valor == ""
        if not valor or _abre(linha):
            novas.append(linha)
            continue
        if valor.startswith("["):
            refeita = _linha_de_fluxo(chave, valor)
            if refeita is None:
                return desistir(f"lista de fluxo sem fecho em {chave}")
            avisos.append(f"itens de {chave} entre aspas")
            novas.append(refeita)
            continue
        if valor[:1] in "\"'{":
            return desistir(f"valor de {chave} comeca com {valor[0]!r} e nao abre")
        refeita = f"{chave}: {yaml_quote_scalar(valor)}"
        if not _abre(refeita):
            return desistir(f"valor de {chave} continua ilegivel entre aspas")
        avisos.append(f"valor de {chave} entre aspas")
        novas.append(refeita)

    if soltas:
        if ja_tem_aliases:
            avisos.append(f"{len(soltas)} linha(s) solta(s) removida(s): a nota ja tem aliases")
        else:
            itens = []
            for ln in soltas:
                texto_item = ln[2:].strip()
                if texto_item[:1] in "\"'":
                    texto_item = texto_item[1:]
                if texto_item[-1:] in "\"'":
                    texto_item = texto_item[:-1]
                if texto_item:
                    itens.append("  - " + yaml_quote_scalar(texto_item))
            if itens:
                novas[ponto_das_soltas:ponto_das_soltas] = ["aliases:", *itens]
                avisos.append(f"{len(itens)} linha(s) solta(s) recuperada(s) como aliases")

    novo_bloco = "\n".join(novas)
    novo = texto[:m.start(1)] + novo_bloco + texto[m.end(1):]
    if novo == texto:
        return desistir("nada a mudar e ainda ilegivel")
    if not _frontmatter_parses(novo):
        return desistir("o bloco continua ilegivel depois do reparo")
    return Reparo(novo, True, avisos)
