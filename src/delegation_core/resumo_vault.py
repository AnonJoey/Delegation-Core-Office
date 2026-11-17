"""O resumo de inicio de sessao em niveis: cada nota mostra o quanto cabe, em vez de so o caminho.

O resumo antigo do hook de inicio listava os caminhos que mudaram. Com `resumo_niveis_enabled`,
cada nota recente aparece com um trecho (L0, ate 256 bytes; L1, ate 500) tirado do `abstract:` ou
`summary:` do frontmatter ou da primeira prosa do corpo, e as fixadas (`pinned: true`) sao
aprofundadas antes das demais. A conta de quanto cabe e `resumo_inicial.atribuir_niveis`:
cobertura primeiro, nenhuma nota some enquanto couber ao menos o seu titulo.

O texto de uma nota e dado de memoria, nao instrucao: vai entre os marcadores de `cerca_nao_confiavel`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .cabeca_da_nota import dividir
from .cerca_nao_confiavel import AVISO, FIM, INICIO, escapar
from .resumo_inicial import CustoDaNota, Nivel, Orcamento, atribuir_niveis, trecho_da_nota

ORCAMENTO_PADRAO = 6000
LIMITE_DE_LEITURA = 64 * 1024
CABECALHO = "Notes changed since your last session (excerpts, deepest first for pinned notes):"


def _bytes(texto: str) -> int:
    return len(texto.encode("utf-8"))


def _titulo(rel: str, mtime: float) -> str:
    return f"- `{rel}` ({datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')})"


def _citar(texto: str) -> str:
    return "\n".join("  > " + linha if linha.strip() else "  >" for linha in escapar(texto).splitlines())


class _Nota:
    def __init__(self, rel: str, mtime: float, texto: str):
        fm, corpo = dividir(texto)
        self.titulo = _titulo(rel, mtime)
        t = trecho_da_nota(fm, corpo)
        self.fixada = fm.get("pinned") is True
        corpo = corpo.strip()
        self.formas = {Nivel.SO_TITULO: self.titulo}
        if t.l0 is not None:
            self.formas[Nivel.L0] = self.titulo + "\n" + _citar(t.l0)
            self.formas[Nivel.L1] = self.titulo + "\n" + _citar(t.l1 or t.l0)
            self.formas[Nivel.L2] = self.titulo + "\n" + _citar(corpo or t.l1 or t.l0)

    def custo(self) -> CustoDaNota:
        if Nivel.L0 not in self.formas:
            return CustoDaNota(self.fixada, _bytes(self.formas[Nivel.SO_TITULO]) + 1, None)
        c0, c1, c2 = (_bytes(self.formas[n]) + 1 for n in (Nivel.L0, Nivel.L1, Nivel.L2))
        c1 = max(c0, c1)
        return CustoDaNota(self.fixada, _bytes(self.titulo) + 1, (c0, c1, max(c1, c2)))

    def texto(self, nivel: Nivel) -> str:
        return self.formas[nivel] if nivel in self.formas else self.formas[Nivel.SO_TITULO]


def renderizar(vault: Path, notas: list[tuple[float, Path]], orcamento: int = ORCAMENTO_PADRAO) -> str:
    """As notas (mtime, caminho), da mais nova para a mais antiga, com o quanto de cada uma couber em `orcamento` bytes."""
    lidas: list[_Nota] = []
    for mtime, p in notas:
        try:
            with Path(p).open("rb") as f:
                texto = f.read(LIMITE_DE_LEITURA).decode("utf-8", errors="replace")
            rel = Path(p).relative_to(vault).as_posix()
        except (OSError, ValueError):
            continue
        lidas.append(_Nota(rel, mtime, texto))
    if not lidas:
        return ""
    # fixadas primeiro, e dentro de cada grupo a ordem de chegada (a mais nova antes)
    lidas.sort(key=lambda n: not n.fixada)
    abertura = f"{CABECALHO}\n\n> **Security boundary:** {AVISO}\n\n{INICIO}\n"
    fechamento = f"{FIM}\n"
    prefixo = _bytes(abertura)
    teto = max(0, orcamento - _bytes(fechamento))

    def omitidas_inteiro(a_partir: int) -> int:
        return sum(_bytes(n.titulo) + 1 for n in lidas[a_partir:]) + _bytes("Not shown:\n")

    def so_contagem(n: int) -> int:
        return _bytes(f"- ...and {n} more note(s) not shown\n")

    plano = atribuir_niveis([n.custo() for n in lidas], Orcamento(prefixo, teto, 0, 0), omitidas_inteiro, so_contagem)
    corpo = [n.texto(nivel) for n, nivel in zip(lidas, plano.niveis) if nivel != Nivel.OMITIDA]
    fora = lidas[plano.omitidas_a_partir:]
    if fora:
        folga = teto - prefixo - sum(_bytes(x) + 1 for x in corpo)
        lista = "Not shown:\n" + "\n".join(n.titulo for n in fora)
        corpo.append(lista if _bytes(lista) + 1 <= folga else f"- ...and {len(fora)} more note(s) not shown")
    return abertura + "\n".join(corpo) + "\n" + fechamento
