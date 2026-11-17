"""Caminhos de trabalho e a escolha de qual passagem entregar.

Porte de `normalize_cwd`, `cwd_within`, `auto_handoff_matches_cwd`,
`handoff_selection_key`, `is_handoff_candidate` e `prefer_handoff` de
`crates/ai-memory-store/src/reader.rs` do ai-memory (MIT, Fabio Akita).

Tudo aqui e comparacao de texto, sem tocar o disco:

- **normalizar**: barra invertida vira `/`, separador no fim sai (a raiz fica `/`); letra
  de unidade e caminho UNC (`C:/...`, `//servidor/...`) vao para minuscula, porque o
  Explorer, o Git e o PowerShell discordam sobre `C:` e `c:`. Caminho Unix fica como esta
  (`/Repo` nao e `/repo`).
- **dentro**: `/repo` contem `/repo/api`, mas nao `/repo-outro` nem `/repositorio`. A
  fronteira e de componente, e nao ha `LIKE`: `%` e `_` num caminho nao sao curinga.
- **escolha**: a passagem manual vale para o projeto todo e vence a automatica; entre
  iguais, a mais nova; so empate de instante abre espaco para o cwd mais especifico; o
  id desempata no fim.

Pacote independente: so a biblioteca padrao.
"""

from __future__ import annotations

from dataclasses import dataclass


def eh_estilo_windows(caminho: str) -> bool:
    b = caminho.encode("utf-8")
    return (len(b) >= 2 and chr(b[0]).isascii() and chr(b[0]).isalpha() and b[1] == 0x3A) or caminho.startswith("//")


def normalizar_cwd(p: str) -> str:
    """`normalize_cwd`."""
    trocado = p.replace("\\", "/") if "\\" in p else p
    aparado = trocado.rstrip("/")
    if aparado == "":
        nucleo = "/"
    else:
        nucleo = aparado
    if eh_estilo_windows(nucleo):
        # `to_ascii_lowercase`: so A-Z mudam.
        return "".join(c.lower() if "A" <= c <= "Z" else c for c in nucleo)
    return nucleo


def cwd_dentro(ancestral: str, descendente: str) -> bool:
    """`cwd_within`: `descendente` e o mesmo diretorio que `ancestral` ou esta abaixo dele."""
    a = normalizar_cwd(ancestral)
    d = normalizar_cwd(descendente)
    if a == d:
        return True
    if a == "/":
        return d.startswith("/") and len(d) > 1
    ab, db = a.encode("utf-8"), d.encode("utf-8")
    return db.startswith(ab) and len(db) > len(ab) and db[len(ab)] == 0x2F


def casa_com_cwd(cwd_da_passagem: str | None, cwd_da_sessao: str | None) -> bool:
    """`auto_handoff_matches_cwd`: uma passagem automatica serve a uma sessao que comeca em `cwd_da_sessao`?"""
    if cwd_da_sessao is None:
        return True   # leitura do projeto todo: toda passagem aberta e candidata
    if cwd_da_passagem is None:
        return True   # sem cwd guardado: vale para o projeto todo
    return cwd_dentro(cwd_da_passagem, cwd_da_sessao)


def chave_de_escolha(manual: bool, criada_em_us: int, cwd: str | None, id_bytes: bytes) -> tuple:
    """`handoff_selection_key`. A especificidade do cwd so desempata AUTOMATICAS de mesmo instante."""
    especificidade = 0 if manual else (len(normalizar_cwd(cwd).encode("utf-8")) if cwd is not None else 0)
    return (manual, criada_em_us, especificidade, bytes(id_bytes))


@dataclass(frozen=True)
class Candidata:
    """O que a escolha precisa saber de uma passagem aberta."""

    id: bytes
    manual: bool          # criada por pessoa (sem sessao de origem): vale para o projeto todo
    criada_em_us: int
    cwd: str | None
    dono: str | None = None


def admite(filtro_dono, dono: str | None) -> bool:
    """`OwnerFilter::admits`. `filtro_dono` e None (qualquer um), "" nao existe, ou ("usuario", x) / ("sem_dono",)."""
    if dono is None or filtro_dono is None:
        return True
    if filtro_dono == ("sem_dono",):
        return False
    return filtro_dono[0] == "usuario" and filtro_dono[1] == dono


def e_candidata(c: Candidata, cwd_da_sessao: str | None, filtro_dono=None) -> bool:
    """`is_handoff_candidate`. O dono e checado ANTES do atalho da manual."""
    if not admite(filtro_dono, c.dono):
        return False
    if c.manual:
        return True
    return casa_com_cwd(c.cwd, cwd_da_sessao)


def escolher(candidatas: list[Candidata], cwd_da_sessao: str | None, filtro_dono=None) -> Candidata | None:
    """A passagem a entregar entre as abertas: a maior pela chave, entre as candidatas."""
    elegiveis = [c for c in candidatas if e_candidata(c, cwd_da_sessao, filtro_dono)]
    if not elegiveis:
        return None
    return max(elegiveis, key=lambda c: chave_de_escolha(c.manual, c.criada_em_us, c.cwd, c.id))
