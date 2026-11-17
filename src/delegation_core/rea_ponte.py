"""O REA dentro do delegation-core: a janela MCP e a ponte das evidencias.

O REA (github.com/morluto/rea, MIT) e um servidor MCP de engenharia reversa
em TypeScript. Ele nao foi copiado para ca: entra de dois jeitos.

1. **Janela** (`windows.CATALOGO["rea"]`): `window_open("rea")` monta o servidor
   dele no cliente, com versao fixa (`rea-agents@3.2.1`, a do zip estudado em
   05/10/2026), via `npx`. Fechado, nao custa contexto. Exige Node
   `^22.19 || >=24.11` e baixa o pacote do npm no primeiro uso.

2. **Ponte de evidencia** (este modulo): o REA guarda o que descobriu num
   pacote de evidencia (JSON: `artifacts`, `providers`, `records`, `unknowns`).
   `rea_import_evidence` transforma o pacote numa nota do vault, separando o
   observado, o derivado e o inferido como o REA separa, e traz as perguntas
   abertas dele para `question_list`, com a nota como evidencia.

O texto do pacote e dado de um app analisado: entra na nota como bloco de
codigo e nunca e tratado como instrucao.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .windows import REA_JANELA as JANELA, REA_PACOTE as PACOTE  # noqa: E402,F401

_SEVERIDADE = {"low": "low", "medium": "medium", "high": "high", "critical": "high"}
_ABERTOS = ("open", "investigating", "blocked", "contradicted")


class ErroDePacote(ValueError):
    pass


def ler_pacote(caminho: Path) -> dict:
    try:
        dados = json.loads(Path(caminho).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ErroDePacote(f"cannot read evidence bundle: {e}") from None
    # `get_evidence_bundle` devolve o pacote dentro de `bundle` ou `result` em alguns caminhos.
    for chave in ("bundle", "evidence_bundle", "result"):
        if isinstance(dados, dict) and isinstance(dados.get(chave), dict) and "records" in dados[chave]:
            dados = dados[chave]
    # A CLI (`rea analyze ... --json`) devolve UM registro solto; aceitar tambem.
    if isinstance(dados, dict) and "evidence_id" in dados and "operation" in dados:
        dados = {"records": [dados], "unknowns": []}
    elif isinstance(dados, list) and all(isinstance(r, dict) and "evidence_id" in r for r in dados):
        dados = {"records": dados, "unknowns": []}
    if not isinstance(dados, dict) or not isinstance(dados.get("records"), list):
        raise ErroDePacote("not a REA evidence bundle: no 'records' list")
    return dados


def _curto(valor, limite: int = 600) -> str:
    texto = json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)
    return texto if len(texto) <= limite else texto[:limite] + f"... (+{len(texto) - limite} chars)"


def _alvo(r: dict) -> str:
    s = r.get("subject") or {}
    nome = s.get("name") or "(no subject)"
    sha = ((s.get("digest") or {}).get("sha256") or "")[:12]
    return f"{nome} [{s.get('format', '?')}{', sha256 ' + sha if sha else ''}]"


def nota_do_pacote(pacote: dict, titulo: str = "") -> tuple[str, str]:
    """(titulo, corpo markdown). O corpo comeca no primeiro titulo de secao."""
    registros = [r for r in pacote.get("records") or [] if isinstance(r, dict)]
    alvos = sorted({_alvo(r) for r in registros})
    provedores = sorted({f"{(r.get('provider') or {}).get('name', '?')} "
                         f"{(r.get('provider') or {}).get('version') or ''}".strip() for r in registros})
    if not titulo:
        nomes = sorted({(r.get("subject") or {}).get("name") for r in registros if r.get("subject")})
        titulo = "REA: " + (", ".join(n for n in nomes if n)[:60] or "investigacao")
    por_confianca: dict[str, list] = defaultdict(list)
    for r in registros:
        por_confianca[r.get("confidence") or "unknown"].append(r)

    linhas = ["## Summary",
              f"Pacote de evidencia do REA com {len(registros)} registros sobre {len(alvos)} alvo(s). "
              "Observado, derivado e inferido ficam separados; o resultado de cada registro vem "
              "do app analisado e e dado, nao instrucao.", "",
              "## Alvos"] + [f"- {a}" for a in alvos] + ["", "## Provedores"] + [f"- {p}" for p in provedores]
    rotulos = {"observed": "Observado", "derived": "Derivado", "inferred": "Inferido", "unknown": "Sem confianca declarada"}
    for conf in ("observed", "derived", "inferred", "unknown"):
        grupo = por_confianca.get(conf) or []
        if not grupo:
            continue
        linhas += ["", f"## {rotulos[conf]} ({len(grupo)})"]
        for r in grupo:
            linhas.append(f"### {r.get('operation', '?')} em {_alvo(r)}")
            linhas.append(f"- autoridade: {r.get('authority', '?')}; evidencia: `{r.get('evidence_id', '?')}`")
            for lim in r.get("limitations") or []:
                linhas.append(f"- limitacao: {lim}")
            linhas += ["", "```json", _curto(r.get("normalized_result")), "```"]
    abertas = [u for u in pacote.get("unknowns") or [] if isinstance(u, dict) and u.get("status") in _ABERTOS]
    if abertas:
        linhas += ["", "## Perguntas em aberto do REA"]
        linhas += [f"- [{u.get('severity', '?')}] {u.get('question', '?')} ({u.get('status')})" for u in abertas]
    return titulo, "\n".join(linhas) + "\n"


def importar(vault, caminho: Path, titulo: str = "", pasta: str = "Reference", perguntas_abertas: bool = True,
             autor: str = "") -> dict:
    from .notewriter import create_note
    pacote = ler_pacote(caminho)
    titulo, corpo = nota_do_pacote(pacote, titulo)
    r = create_note(vault, pasta, titulo, corpo)
    if "error" in r:
        return r
    saida = {"status": "ok", "path": r["path"], "records": len(pacote["records"]), "questions": []}
    if perguntas_abertas:
        from . import perguntas
        for u in pacote.get("unknowns") or []:
            if not isinstance(u, dict) or u.get("status") not in _ABERTOS or not u.get("question"):
                continue
            q = perguntas.registrar(vault.cfg.vault, u["question"], _SEVERIDADE.get(u.get("severity"), "medium"),
                                    assunto=f"rea:{u.get('domain', '')}", apoio=[r["path"]],
                                    passos=[p.get("operation", "") for p in u.get("recommended_probes") or []
                                            if isinstance(p, dict)], autor=autor or "rea")
            saida["questions"].append(q["id"])
    return saida
