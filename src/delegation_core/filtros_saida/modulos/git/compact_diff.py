"""`compact_diff` do `git_cmd.rs` do RTK: um diff unificado (ou combinado) reduzido ao que mudou.

Usado por `git diff`, `git show` e `gh pr diff`. Cada arquivo vira o seu
caminho e as linhas alteradas, com no maximo 100 por hunk, tres linhas de
contexto antes da primeira mudanca (e `max_lines / 10` no diff todo), e a
contagem `+N -M` ao fim. O que sobra do corte e dito, nunca calado.

O orcamento de cada hunk vem do cabecalho `@@ -a,b +c,d @@` (ou `@@@` num diff
combinado): o corpo termina onde as contagens se esgotam, nao na proxima
linha de cabecalho, e o que vem depois (envelope de mbox, assinatura `-- `)
nao e lido como conteudo do diff. As colunas de marcador sao lidas como bytes,
como no RTK: `--word-diff` nao tem coluna de marcador e o conteudo pode
comecar por um caractere de varios bytes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..base import linhas, pelo_filtro, split_whitespace

USIZE_MAX = 2**64 - 1
MAX_HUNK_LINES = 100
MAX_LEADING_CONTEXT = 3
_USIZE = re.compile(r"\+?[0-9]+")
_OCTAL = re.compile(rb"[0-7]{1,3}")
_ESCAPES = {ord("a"): 0x07, ord("b"): 0x08, ord("t"): 0x09, ord("n"): 0x0A,
            ord("v"): 0x0B, ord("f"): 0x0C, ord("r"): 0x0D}


def _parse_usize(texto: str) -> int | None:
    """`str::parse::<usize>()`: digitos ASCII com um `+` opcional, sem estourar 64 bits."""
    if not _USIZE.fullmatch(texto):
        return None
    n = int(texto)
    return n if n <= USIZE_MAX else None


# ── caminho do cabecalho `diff --git` ────────────────────────────────────────

def unescape_path(quoted: str) -> str:
    """Desfaz os escapes C de um caminho entre aspas do git (`core.quotepath`).

    Os escapes octais soletram os bytes do caminho um a um, por isso sao juntos
    como bytes e decodificados uma vez no fim.
    """
    b = quoted.encode("utf-8")
    saida = bytearray()
    i, n = 0, len(b)
    while i < n:
        if b[i] != 0x5C or i + 1 == n:
            saida.append(b[i])
            i += 1
            continue
        escape = b[i + 1]
        if 0x30 <= escape <= 0x39:
            fim = min(i + 4, n)
            digitos = b[i + 1:fim]
            if _OCTAL.fullmatch(digitos) and int(digitos, 8) <= 0xFF:
                saida.append(int(digitos, 8))
                i = fim
            else:
                saida.append(b[i])
                i += 1
            continue
        saida.append(_ESCAPES.get(escape, escape))
        i += 2
    return saida.decode("utf-8", "replace")


def unquote_path(raw: str) -> str:
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        return unescape_path(raw[1:-1])
    return raw


def same_path_twice(rest: str) -> str | None:
    """O caminho que um `diff --git` nomeia duas vezes, partido ao meio."""
    b = rest.encode("utf-8")
    if len(b) % 2 == 0:
        return None
    meio = len(b) // 2
    if b[meio] != 0x20:
        return None
    esquerda = unquote_path(b[:meio].decode("utf-8", "replace"))
    direita = unquote_path(b[meio + 1:].decode("utf-8", "replace"))
    if esquerda == direita:
        return esquerda
    if "/" not in esquerda or "/" not in direita:
        return None
    e_caminho = esquerda.split("/", 1)[1]
    d_caminho = direita.split("/", 1)[1]
    return d_caminho if e_caminho == d_caminho else None


def diff_header_path(linha: str) -> str:
    partes = linha.split(" ", 2)
    if len(partes) < 3:
        return "unknown"
    rest = partes[2]
    if not linha.startswith("diff --git "):
        return unquote_path(rest)
    igual = same_path_twice(rest)
    if igual is not None:
        return igual
    # Um renome nomeia dois caminhos diferentes, e o destino e o segundo.
    pedacos = rest.split(' "b/')
    if len(pedacos) > 1 and pedacos[1].endswith('"'):
        return unescape_path(pedacos[1][:-1])
    pedacos = rest.split(" b/")
    if len(pedacos) > 1:
        return pedacos[1]
    return unquote_path(rest)


# ── cabecalho de hunk e orcamento de linhas ──────────────────────────────────

@dataclass
class HunkHeader:
    #: Linhas que o hunk ocupa em cada pai, na ordem das colunas de marcador.
    parents: list[int] = field(default_factory=list)
    #: Linhas que o hunk ocupa no arquivo resultante.
    new: int = 0
    #: Colunas de marcador: 1 para `@@`, uma por pai para `@@@`.
    prefix_width: int = 1

    def exhausted(self) -> bool:
        return self.new == 0 and all(p == 0 for p in self.parents)

    def consume(self, markers: bytes) -> None:
        """Cobra uma linha do corpo dos orcamentos que ela ocupa."""
        is_add = 0x2B in markers
        is_del = 0x2D in markers
        for i in range(len(self.parents)):
            coluna = markers[i] if i < len(markers) else None
            presente = coluna == 0x2D if is_del else coluna != 0x2B
            if presente:
                self.parents[i] = max(0, self.parents[i] - 1)
        if is_add or not is_del:
            self.new = max(0, self.new - 1)


def parse_hunk_header(linha: str) -> HunkHeader | None:
    """`@@ -a,b +c,d @@` e o combinado `@@@ -a,b -c,d +e,f @@@`."""
    at_run = len(linha) - len(linha.lstrip("@"))
    if at_run < 2:
        return None
    corpo = linha[at_run:].split("@")[0]
    parents: list[int] = []
    novo = None
    for grupo in split_whitespace(corpo):
        if grupo[0] not in "-+":
            continue
        rest = grupo[1:]
        if "," in rest:
            contagem = _parse_usize(rest.split(",", 1)[1])
            if contagem is None:
                return None
        else:
            contagem = 1
        if grupo.startswith("-"):
            parents.append(contagem)
        else:
            novo = contagem
    prefix_width = at_run - 1
    if len(parents) != prefix_width:
        parents = (parents + [USIZE_MAX] * prefix_width)[:prefix_width]
    return HunkHeader(parents, novo if novo is not None else 0, prefix_width)


def hunk_truncation_note(deletions: int, additions: int) -> str | None:
    def conta(n: int, substantivo: str) -> str:
        return f"{n} {substantivo}" if n == 1 else f"{n} {substantivo}s"

    if deletions == 0 and additions == 0:
        return None
    if deletions == 0:
        return f"  ... ({conta(additions, 'addition')} truncated)"
    if additions == 0:
        return f"  ... ({conta(deletions, 'deletion')} truncated)"
    return f"  ... ({conta(deletions, 'deletion')}, {conta(additions, 'addition')} truncated)"


def compact_diff(diff: str, max_lines: int) -> str:
    result: list[str] = []
    current_file = ""
    added = removed = 0
    hunk: HunkHeader | None = None
    hunk_shown = 0
    skipped_add = skipped_del = 0
    leading: list[str] = []
    leading_total = 0
    leading_cap = max_lines // 10
    truncado = False

    def descarregar_contexto() -> None:
        nonlocal leading_total
        sobra = max(0, leading_cap - leading_total)
        manter = min(len(leading), sobra)
        pular = len(leading) - manter
        result.extend(leading[pular:])
        leading_total += manter
        leading.clear()

    def nota_de_corte() -> None:
        nonlocal skipped_add, skipped_del, truncado
        nota = hunk_truncation_note(skipped_del, skipped_add)
        if nota is not None:
            result.append(nota)
            truncado = True
            skipped_del = skipped_add = 0

    for linha in linhas(diff):
        if linha.startswith("diff --"):
            descarregar_contexto()
            nota_de_corte()
            if current_file and (added > 0 or removed > 0):
                result.append(f"  +{added} -{removed}")
            current_file = diff_header_path(linha)
            result.append(f"\n{current_file}")
            added = removed = 0
            hunk = None
            hunk_shown = 0
        else:
            cabecalho = parse_hunk_header(linha)
            if cabecalho is not None:
                descarregar_contexto()
                nota_de_corte()
                hunk = cabecalho
                hunk_shown = 0
                result.append(linha)
            elif hunk is not None:
                if hunk.exhausted():
                    hunk = None
                    continue
                if linha.startswith("\\"):
                    continue
                largura = hunk.prefix_width
                markers = linha[:largura].encode("utf-8")[:largura]
                is_add = 0x2B in markers
                is_del = 0x2D in markers
                hunk.consume(markers)
                if is_add or is_del:
                    if is_add:
                        added += 1
                    if is_del:
                        removed += 1
                    if hunk_shown < MAX_HUNK_LINES:
                        descarregar_contexto()
                        result.append(linha)
                        hunk_shown += 1
                    elif is_del:
                        skipped_del += 1
                    else:
                        skipped_add += 1
                    leading.clear()
                elif hunk_shown > 0:
                    if hunk_shown < MAX_HUNK_LINES:
                        result.append(linha)
                        hunk_shown += 1
                elif leading_total < leading_cap:
                    if len(leading) == MAX_LEADING_CONTEXT:
                        leading.pop(0)
                    leading.append(linha)
                if hunk.exhausted():
                    hunk = None
                    descarregar_contexto()
        if max(0, len(result) - leading_total) >= max_lines:
            result.append("\n... (more changes truncated)")
            truncado = True
            break

    descarregar_contexto()
    nota = hunk_truncation_note(skipped_del, skipped_add)
    if nota is not None:
        result.append(nota)
        truncado = True
    if current_file and (added > 0 or removed > 0):
        result.append(f"  +{added} -{removed}")
    if truncado:
        result.append(f"[full diff: {pelo_filtro('git diff --no-compact')}]")
    return "\n".join(result)
