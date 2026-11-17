"""Porte de `src/core/toml_filter.rs` do RTK (Apache 2.0) para Python.

Fiel ao original nos pontos que mudam a saida:

- Ordem dos 8 estagios: strip_ansi, replace (linha a linha, regras em cadeia),
  match_output (curto-circuito no texto inteiro, com `unless`), strip OU keep
  de linhas, truncate_lines_at (`...` no fim, contando caracteres), head/tail
  (com a linha "... (N lines omitted)"), max_lines (com "... (N lines
  truncated)") e on_empty.
- Linhas como `str::lines()` do Rust: separa em `\\n`, tira um `\\r` do fim de
  cada linha e nao gera linha vazia depois do ultimo `\\n`.
- Filtros em ordem alfabetica de nome (o `BTreeMap` do Rust) e o primeiro que
  casa com o comando vence.
- `match_command` sem ancora (`^`) em todo ramo de topo e ignorado com aviso,
  como no RTK: sem isso, `timeout 5 /usr/bin/liquibase` ativaria o filtro do
  liquibase.
- Substituicao no estilo Rust (`$1`, `${1}`, `$nome`, `$$`) convertida para a
  do Python.

Fora do porte: o filtro por projeto (`.rtk/filters.toml`), que o RTK so carrega
depois de uma confirmacao de confianca; aqui so ha o arquivo do usuario,
`~/.delegation_core/filters.toml`, com o mesmo esquema.
"""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("filtros_saida")

DIR_EMBUTIDOS = Path(__file__).parent / "rtk"
_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_CAMPOS = {"description", "match_command", "strip_ansi", "replace", "match_output",
           "strip_lines_matching", "keep_lines_matching", "truncate_lines_at", "head_lines",
           "tail_lines", "max_lines", "on_empty", "filter_stderr"}


class ErroDeFiltro(ValueError):
    pass


@dataclass
class Filtro:
    nome: str
    match: re.Pattern
    descricao: str = ""
    strip_ansi: bool = False
    replace: list = field(default_factory=list)          # [(re, substituicao)]
    match_output: list = field(default_factory=list)     # [(re, mensagem, re|None)]
    strip: list = field(default_factory=list)
    keep: list = field(default_factory=list)
    truncate_lines_at: int | None = None
    head_lines: int | None = None
    tail_lines: int | None = None
    max_lines: int | None = None
    on_empty: str | None = None
    filter_stderr: bool = False
    origem: str = "builtin"


def _linhas(texto: str) -> list[str]:
    """`str::lines()` do Rust."""
    partes = texto.split("\n")
    if partes and partes[-1] == "":
        partes.pop()
    return [p[:-1] if p.endswith("\r") else p for p in partes]


def _truncar(linha: str, maximo: int) -> str:
    if len(linha) <= maximo:
        return linha
    if maximo < 3:
        return "..."
    return linha[: maximo - 3] + "..."


_REF_RUST = re.compile(r"\$\$|\$\{(\w+)\}|\$(\d+|[A-Za-z_]\w*)")


def substituicao_rust(rep: str) -> str:
    """`$1`, `${1}`, `$nome` -> `\\g<...>`; `$$` -> `$`; barra invertida literal."""
    rep = rep.replace("\\", "\\\\")

    def troca(m):
        if m.group(0) == "$$":
            return "$"
        return "\\g<" + (m.group(1) or m.group(2)) + ">"
    return _REF_RUST.sub(troca, rep)


def _ramos_de_topo(padrao: str) -> list[str]:
    ramos, inicio, prof, em_classe, escapado = [], 0, 0, False, False
    for i, c in enumerate(padrao):
        if escapado:
            escapado = False
            continue
        if c == "\\":
            escapado = True
        elif c == "[" and not em_classe:
            em_classe = True
        elif c == "]" and em_classe:
            em_classe = False
        elif c == "(" and not em_classe:
            prof += 1
        elif c == ")" and not em_classe:
            prof = max(0, prof - 1)
        elif c == "|" and not em_classe and prof == 0:
            ramos.append(padrao[inicio:i])
            inicio = i + 1
    ramos.append(padrao[inicio:])
    return ramos


def _sem_flags(ramo: str) -> str:
    if not ramo.startswith("(?"):
        return ramo
    fim = ramo.find(")", 2)
    if fim == -1 or not all(c in "imsuxU-" for c in ramo[2:fim]):
        return ramo
    return ramo[fim + 1:]


def ancorado(padrao: str) -> bool:
    return all(_sem_flags(r).startswith("^") for r in _ramos_de_topo(padrao))


def _re(p: str, onde: str) -> re.Pattern:
    try:
        return re.compile(p)
    except re.error as e:
        raise ErroDeFiltro(f"{onde}: invalid regex {p!r}: {e}") from None


def compilar(nome: str, d: dict, origem: str = "builtin") -> Filtro:
    desconhecidos = set(d) - _CAMPOS
    if desconhecidos:
        raise ErroDeFiltro(f"filter {nome!r}: unknown fields {sorted(desconhecidos)}")
    if "match_command" not in d:
        raise ErroDeFiltro(f"filter {nome!r}: match_command is required")
    if d.get("strip_lines_matching") and d.get("keep_lines_matching"):
        raise ErroDeFiltro("strip_lines_matching and keep_lines_matching are mutually exclusive")
    return Filtro(
        nome=nome, descricao=d.get("description") or "", origem=origem,
        match=_re(d["match_command"], f"{nome}.match_command"),
        strip_ansi=bool(d.get("strip_ansi", False)),
        replace=[(_re(r["pattern"], f"{nome}.replace"), substituicao_rust(r["replacement"]))
                 for r in d.get("replace", [])],
        match_output=[(_re(r["pattern"], f"{nome}.match_output"), r["message"],
                       _re(r["unless"], f"{nome}.unless") if r.get("unless") else None)
                      for r in d.get("match_output", [])],
        strip=[_re(p, f"{nome}.strip") for p in d.get("strip_lines_matching", [])],
        keep=[_re(p, f"{nome}.keep") for p in d.get("keep_lines_matching", [])],
        truncate_lines_at=d.get("truncate_lines_at"), head_lines=d.get("head_lines"),
        tail_lines=d.get("tail_lines"), max_lines=d.get("max_lines"),
        on_empty=d.get("on_empty"), filter_stderr=bool(d.get("filter_stderr", False)),
    )


def aplicar(f: Filtro, saida: str) -> str:
    """Os 8 estagios, na ordem do `apply_filter_with_info` do RTK."""
    linhas = _linhas(saida)
    if f.strip_ansi:
        linhas = [_ANSI.sub("", l) for l in linhas]
    if f.replace:
        novas = []
        for l in linhas:
            for padrao, rep in f.replace:
                l = padrao.sub(rep, l)
            novas.append(l)
        linhas = novas
    if f.match_output:
        texto = "\n".join(linhas)
        for padrao, mensagem, salvo in f.match_output:
            if padrao.search(texto):
                if salvo is not None and salvo.search(texto):
                    continue
                return mensagem
    if f.strip:
        linhas = [l for l in linhas if not any(p.search(l) for p in f.strip)]
    elif f.keep:
        linhas = [l for l in linhas if any(p.search(l) for p in f.keep)]
    if f.truncate_lines_at is not None:
        linhas = [_truncar(l, f.truncate_lines_at) for l in linhas]
    total = len(linhas)
    h, t = f.head_lines, f.tail_lines
    if h is not None and t is not None:
        if total > h + t:
            linhas = linhas[:h] + [f"... ({total - h - t} lines omitted)"] + linhas[total - t:]
    elif h is not None:
        if total > h:
            linhas = linhas[:h] + [f"... ({total - h} lines omitted)"]
    elif t is not None and total > t:
        omitidas = total - t
        linhas = [f"... ({omitidas} lines omitted)"] + linhas[omitidas:]
    if f.max_lines is not None and len(linhas) > f.max_lines:
        cortadas = len(linhas) - f.max_lines
        linhas = linhas[: f.max_lines] + [f"... ({cortadas} lines truncated)"]
    resultado = "\n".join(linhas)
    if not resultado.strip() and f.on_empty is not None:
        return f.on_empty
    return resultado


def _ler(texto: str, origem: str) -> tuple[list[Filtro], dict]:
    try:
        dados = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        raise ErroDeFiltro(f"TOML parse error in {origem}: {e}") from None
    if dados.get("schema_version", 1) != 1:
        raise ErroDeFiltro(f"unsupported schema_version in {origem}")
    filtros = []
    for nome in sorted(dados.get("filters", {})):
        d = dados["filters"][nome]
        if not ancorado(d.get("match_command", "")):
            logger.warning("filter %r in %s: match_command %r is not anchored on every branch; skipped",
                           nome, origem, d.get("match_command"))
            continue
        filtros.append(compilar(nome, d, origem))
    return filtros, dados.get("tests", {})


def _texto_embutido() -> str:
    """Como o build.rs: todos os .toml em ordem alfabetica de arquivo, num texto so."""
    partes = ["schema_version = 1\n"]
    for p in sorted(DIR_EMBUTIDOS.glob("*.toml")):
        partes.append(f"# --- {p.name} ---\n" + p.read_text(encoding="utf-8") + "\n")
    return "\n".join(partes)


_CACHE: dict = {}


def carregar_embutidos() -> tuple[list[Filtro], dict]:
    if "embutidos" not in _CACHE:
        _CACHE["embutidos"] = _ler(_texto_embutido(), "builtin")
    return _CACHE["embutidos"]


def arquivo_do_usuario() -> Path:
    from .. import config
    return config.CONFIG_DIR / "filters.toml"


def carregar() -> list[Filtro]:
    """Os do usuario primeiro (vencem), depois os embutidos. Arquivo quebrado: aviso, nao queda."""
    filtros: list[Filtro] = []
    arq = arquivo_do_usuario()
    if arq.is_file():
        try:
            filtros += _ler(arq.read_text(encoding="utf-8"), str(arq))[0]
        except ErroDeFiltro as e:
            logger.warning("%s", e)
    return filtros + carregar_embutidos()[0]


def achar(comando: str, filtros: list[Filtro] | None = None) -> Filtro | None:
    for f in carregar() if filtros is None else filtros:
        if f.match.search(comando):
            return f
    return None


def verificar() -> dict:
    """Roda os casos `[[tests.*]]` embutidos, como `rtk verify`."""
    filtros, testes = carregar_embutidos()
    por_nome = {f.nome: f for f in filtros}
    resultados = []
    for nome in sorted(testes):
        for caso in testes[nome]:
            f = por_nome.get(nome)
            if f is None:
                resultados.append({"filter": nome, "test": caso.get("name"), "passed": False,
                                   "actual": "", "expected": "", "error": "filter not loaded"})
                continue
            atual = aplicar(f, caso["input"]).rstrip("\n")
            esperado = caso["expected"].rstrip("\n")
            resultados.append({"filter": nome, "test": caso.get("name"), "passed": atual == esperado,
                               "actual": atual, "expected": esperado})
    sem_teste = sorted(set(por_nome) - set(testes))
    return {"total": len(resultados), "passed": sum(r["passed"] for r in resultados),
            "failed": [r for r in resultados if not r["passed"]], "filters": len(filtros),
            "without_tests": sem_teste}
