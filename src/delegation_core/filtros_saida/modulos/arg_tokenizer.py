"""`src/core/arg_tokenizer.rs` do RTK: separa uma lista de argumentos em flags, valores e posicionais.

So o dialeto POSIX (git, cargo, rg): `-xyz` e um grupo de flags curtas lidas
letra a letra, e so `=` prende um valor a uma flag longa. O dialeto MSBuild
(dotnet) nao e usado por nenhum modulo portado e nao foi trazido.

Cada chamador diz, numa tabela propria, quais flags levam valor
(`takes_value(tipo, nome) -> ValueSpec | None`); o tokenizador so anda pelos
argumentos. `Token.source_index` diz de qual argumento da lista original o
token saiu, e todas as flags curtas de um mesmo grupo dividem um so indice.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Optional, Sequence

DASH_DASH = "dashdash"
LONG = "long"
POSITIONAL = "positional"
SHORT = "short"


@dataclass(frozen=True)
class ValueSpec:
    """Como o valor de uma flag pode ser escrito."""

    #: `--flag=v` apenas: o argumento seguinte nunca e o valor (`-M50`, nao `-M 50`).
    attached_only: bool = False
    #: Com valor separado, so vale para flag curta que e o argumento inteiro (`-n 2`, nao `-pn 2`).
    solo_only: bool = False
    #: Um `--` ainda nao visto pode ser o valor em vez do fim das opcoes.
    claims_dash_dash: bool = False

    @classmethod
    def value(cls) -> "ValueSpec":
        return cls()

    @classmethod
    def attached(cls) -> "ValueSpec":
        return cls(attached_only=True)

    @classmethod
    def solo(cls) -> "ValueSpec":
        return cls(solo_only=True)

    def claiming_dash_dash(self) -> "ValueSpec":
        return replace(self, claims_dash_dash=True)


@dataclass
class Token:
    kind: str
    #: Nome da flag sem os tracos (long/short), texto cru (positional), vazio (dashdash).
    text: str
    #: `--flag=valor`, ou o resto de um grupo curto (`-A3`: Short "A" com attached "3").
    attached: Optional[str] = None
    #: Indice, na lista de tokens, do posicional consumido como valor desta flag (ou o inverso).
    linked: Optional[int] = None
    source_index: int = 0
    double_dash: bool = False

    def value(self, tokens: Sequence["Token"]) -> Optional[str]:
        """O valor da flag: preso (`--f=v`, `-fv`) ou o token seguinte consumido."""
        if self.kind == POSITIONAL:
            return None
        if self.attached is not None:
            return self.attached
        if self.linked is not None and 0 <= self.linked < len(tokens):
            return tokens[self.linked].text
        return None

    def is_free_positional(self) -> bool:
        return self.kind == POSITIONAL and self.linked is None


TakesValue = Callable[[str, str], Optional[ValueSpec]]


def is_digit_run(texto: str) -> bool:
    """Nao vazio e so de digitos ASCII (`-20`, a contagem de `git log -20`)."""
    return bool(texto) and all("0" <= c <= "9" for c in texto)


def dashdash_index(tokens: Sequence[Token]) -> Optional[int]:
    for i, t in enumerate(tokens):
        if t.kind == DASH_DASH:
            return i
    return None


def before_dashdash(tokens: Sequence[Token]) -> Sequence[Token]:
    i = dashdash_index(tokens)
    return tokens if i is None else tokens[:i]


def _sem_valor(_tipo: str, _nome: str) -> None:
    return None


def tokenize(args: Sequence[str]) -> list[Token]:
    """Estrutural: nenhuma flag leva valor. Serve para achar subcomando e fronteira `--`."""
    return tokenize_grammar(args, _sem_valor)


def tokenize_grammar(args: Sequence[str], takes_value: TakesValue = _sem_valor) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    emitiu_dd = False
    n = len(args)

    def ligar_valor(indice_flag: int, indice_valor: int, spec: ValueSpec) -> bool:
        if indice_valor >= n:
            return False
        seguinte = args[indice_valor]
        if seguinte == "--" and not emitiu_dd and not spec.claims_dash_dash:
            return False
        tokens.append(Token(POSITIONAL, seguinte, linked=indice_flag, source_index=indice_valor))
        tokens[indice_flag].linked = len(tokens) - 1
        return True

    while i < n:
        arg = args[i]
        if emitiu_dd:
            tokens.append(Token(POSITIONAL, arg, source_index=i))
            i += 1
            continue
        if arg == "--":
            tokens.append(Token(DASH_DASH, "", source_index=i))
            emitiu_dd = True
            i += 1
            continue
        if arg.startswith("--"):
            resto = arg[2:]
            nome, sep, preso = resto.partition("=")
            attached = preso if sep else None
            indice_flag = len(tokens)
            tokens.append(Token(LONG, nome, attached=attached, source_index=i, double_dash=True))
            i += 1
            if attached is None:
                spec = takes_value(LONG, nome)
                if spec is not None and not spec.attached_only and ligar_valor(indice_flag, i, spec):
                    i += 1
            continue
        if len(arg) > 1 and arg.startswith("-"):
            grupo = arg[1:]
            if is_digit_run(grupo):
                tokens.append(Token(SHORT, grupo, source_index=i))
                i += 1
                continue
            consumiu = False
            origem = i
            for deslocamento, letra in enumerate(grupo):
                indice_flag = len(tokens)
                tokens.append(Token(SHORT, letra, source_index=origem))
                spec = takes_value(SHORT, letra)
                if spec is None:
                    continue
                resto = grupo[deslocamento + 1:]
                if resto:
                    tokens[indice_flag].attached = resto
                else:
                    solo = deslocamento == 0
                    separado = (not spec.attached_only) and (not spec.solo_only or solo)
                    if separado:
                        consumiu = ligar_valor(indice_flag, origem + 1, spec)
                break
            i += 2 if consumiu else 1
            continue
        tokens.append(Token(POSITIONAL, arg, source_index=i))
        i += 1
    return tokens
