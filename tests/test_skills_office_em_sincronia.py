"""As tres copias de `scripts/office/` nao podem divergir em silencio.

## Por que ha tres copias, e por que isso esta CERTO

`skills/docx`, `skills/pptx` e `skills/xlsx` carregam a mesma pasta
`scripts/office/`, identica byte a byte: 39 arquivos em 12 grupos, 5.622 linhas
redundantes medidas em 24/09/2026.

O reflexo e chamar isso de duplicacao e extrair um pacote comum. Tres medidas
mostram que a extracao QUEBRARIA as tres skills:

1. `installer.install_skills` copia **pasta a pasta**:
   `for pasta in origem.iterdir(): copytree(pasta, destino)`. Cada skill chega
   sozinha em `~/.claude/skills/<nome>/`.
2. O `SKILL.md` invoca por caminho relativo: `python scripts/office/unpack.py`.
3. `pack.py` faz `from validators import ...`, import nu que so resolve porque
   `validators/` esta ao lado do script.

Nao ha instalacao de pacote, nem ajuste de `sys.path`, nem garantia de que o
`delegation-core` exista na maquina onde a skill roda. **Vendoring e a resposta
correta para "tem que rodar sozinho sem passo de instalacao"**, e as tres copias
sao vendoring, nao descuido.

## Entao qual e o problema de verdade

Nao a duplicacao: a **divergencia silenciosa**. Corrigir `merge_runs.py` numa
copia e esquecer as outras duas produz tres skills que se comportam diferente
sem ninguem anunciar, e o sintoma aparece meses depois num documento torto.

Este teste guarda exatamente isso, e nada mais. Ele nao pede que a duplicacao
acabe; pede que as copias continuem iguais enquanto existirem.

## Quando este teste falhar

Ele falha em dois casos, e a acao e oposta:

- **Alguem corrigiu uma copia e esqueceu as outras.** Copie a correcao para as
  tres. Foi para isto que o teste existe.
- **Alguem precisou que uma skill divergisse de proposito.** Entao o vendoring
  deixou de ser identico e o teste precisa de uma lista de excecoes explicita,
  com o motivo escrito. Afrouxar sem escrever o motivo devolve o problema.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / "skills"
FAMILIA = ("docx", "pptx", "xlsx")
REFERENCIA = "docx"


def _office(skill: str) -> Path:
    return SKILLS / skill / "scripts" / "office"


def _arquivos(raiz: Path) -> dict[str, str]:
    """Caminho relativo -> md5, para todo arquivo sob `raiz`."""
    return {
        str(f.relative_to(raiz)): hashlib.md5(f.read_bytes()).hexdigest()
        for f in sorted(raiz.rglob("*"))
        if f.is_file() and "__pycache__" not in f.parts
    }


@pytest.mark.skipif(not _office(REFERENCIA).is_dir(),
                    reason="a familia office nao esta neste checkout")
@pytest.mark.parametrize("skill", [s for s in FAMILIA if s != REFERENCIA])
def test_a_copia_nao_divergiu_da_referencia(skill):
    """Cada copia tem os mesmos arquivos e o mesmo conteudo que a de `docx`."""
    esperado = _arquivos(_office(REFERENCIA))
    obtido = _arquivos(_office(skill))

    faltando = sorted(set(esperado) - set(obtido))
    sobrando = sorted(set(obtido) - set(esperado))
    assert not faltando, f"{skill} nao tem: {faltando}"
    assert not sobrando, f"{skill} tem a mais: {sobrando}"

    diferentes = sorted(nome for nome, h in esperado.items() if obtido[nome] != h)
    assert not diferentes, (
        f"{skill} divergiu de {REFERENCIA} em: {diferentes}. "
        "As tres copias sao vendoring deliberado e precisam continuar iguais; "
        "leve a correcao para as tres, ou declare a excecao com o motivo.")


@pytest.mark.skipif(not _office(REFERENCIA).is_dir(),
                    reason="a familia office nao esta neste checkout")
def test_a_familia_nao_encolheu_sem_aviso():
    """Se alguem apagar uma skill da familia, este teste passa a mentir.

    Sem esta guarda, remover `xlsx` faria a parametrizacao rodar sobre uma
    skill so e o arquivo continuaria verde, dando a impressao de que a
    sincronia esta conferida quando nao ha mais o que conferir.
    """
    presentes = [s for s in FAMILIA if _office(s).is_dir()]
    assert presentes == list(FAMILIA), (
        f"a familia office mudou: esperado {list(FAMILIA)}, presente {presentes}")
