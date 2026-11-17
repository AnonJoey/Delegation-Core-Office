"""Perguntas em aberto: o que ainda nao se sabe, com a evidencia de cada lado.

Trazido do REA (`record_unknown`, `update_unknown`, `list_unknowns`,
`verify_unknown_resolution`). O vault guarda o que foi decidido e o que foi
feito; o que ainda e duvida ficava espalhado em fim de nota ou se perdia. Aqui
cada duvida tem:

- severidade e assunto;
- notas que apoiam e notas que contradizem (caminhos do vault);
- proximos passos sugeridos para responder;
- uma revisao, e toda mudanca exige a revisao esperada: dois agentes nao
  sobrescrevem a atualizacao um do outro em silencio.

Responder exige evidencia: pelo menos uma nota do vault que exista. "Nao achei
nada contra" nao fecha pergunta, que e a regra do REA e a do usuario (falta de
evidencia nao e um "nao").
"""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from pathlib import Path
from .arquivos_json import gravar_json, ler_json

SEVERIDADES = ("low", "medium", "high")
ESTADOS = ("open", "investigating", "answered", "wont_answer")
ABERTOS = ("open", "investigating")

_TRAVA = threading.Lock()


class ErroDePergunta(ValueError):
    pass


def _arquivo() -> Path:
    from . import config
    return config.CONFIG_DIR / "open_questions.json"


def _ler() -> list[dict]:
    return ler_json(_arquivo(), list)


def _travado():
    """Trava de thread e de processo: daemon e CLI gravam o mesmo arquivo."""
    from contextlib import ExitStack
    from .locking import arquivo_travado
    pilha = ExitStack()
    pilha.enter_context(_TRAVA)
    pilha.enter_context(arquivo_travado(_arquivo()))
    return pilha


def _gravar(itens: list[dict]) -> None:
    gravar_json(_arquivo(), itens)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _notas(raiz: Path, caminhos) -> list[str]:
    """Normaliza e confere: cada caminho tem que ser uma nota do vault que existe."""
    from .notes import resolve_in_vault
    saida = []
    for c in caminhos or []:
        c = str(c).strip()
        if not c:
            continue
        p = resolve_in_vault(Path(raiz), c)
        if p is None or not p.is_file():
            raise ErroDePergunta(f"evidence must be an existing vault note: {c}")
        saida.append(p.relative_to(Path(raiz).resolve()).as_posix())
    return sorted(set(saida))


def _achar(itens, qid):
    achados = [i for i in itens if i["id"] == qid or i["id"].startswith(qid)]
    if len(achados) != 1:
        raise ErroDePergunta(f"question not found: {qid}")
    return achados[0]


def registrar(raiz: Path, pergunta: str, severidade: str = "medium", assunto: str = "",
              apoio=None, contra=None, passos=None, autor: str = "") -> dict:
    if not pergunta.strip():
        raise ErroDePergunta("question is required")
    if severidade not in SEVERIDADES:
        raise ErroDePergunta(f"severity must be one of {', '.join(SEVERIDADES)}")
    item = {
        "id": "q_" + uuid.uuid4().hex[:8], "question": pergunta.strip(), "severity": severidade,
        "topic": assunto.strip(), "status": "open", "revision": 1,
        "supporting": _notas(raiz, apoio), "contradicting": _notas(raiz, contra),
        "probes": [str(p).strip() for p in passos or [] if str(p).strip()],
        "by": autor, "created": _agora(), "updated": _agora(), "resolution": None,
    }
    with _travado():
        itens = _ler()
        itens.append(item)
        _gravar(itens)
    return item


def atualizar(raiz: Path, qid: str, revisao_esperada: int, *, estado: str = "", severidade: str = "",
              apoio=None, contra=None, passos=None, autor: str = "") -> dict:
    with _travado():
        itens = _ler()
        q = _achar(itens, qid)
        if q["revision"] != revisao_esperada:
            raise ErroDePergunta(f"conflict: question is at revision {q['revision']}, not {revisao_esperada}. "
                                 "Re-read it with question_list and retry.")
        if estado:
            if estado not in ("open", "investigating", "wont_answer"):
                raise ErroDePergunta("status: open, investigating or wont_answer (answer with question_resolve)")
            q["status"] = estado
        if severidade:
            if severidade not in SEVERIDADES:
                raise ErroDePergunta(f"severity must be one of {', '.join(SEVERIDADES)}")
            q["severity"] = severidade
        if apoio:
            q["supporting"] = sorted(set(q["supporting"]) | set(_notas(raiz, apoio)))
        if contra:
            q["contradicting"] = sorted(set(q["contradicting"]) | set(_notas(raiz, contra)))
        if passos:
            q["probes"] = [str(p).strip() for p in passos if str(p).strip()]
        q["revision"] += 1
        q["updated"] = _agora()
        q.setdefault("history", []).append({"when": q["updated"], "by": autor, "revision": q["revision"]})
        _gravar(itens)
        return q


def responder(raiz: Path, qid: str, revisao_esperada: int, resposta: str, evidencia, autor: str = "") -> dict:
    notas = _notas(raiz, evidencia)
    if not notas:
        raise ErroDePergunta("an answer needs at least one vault note as evidence; "
                             "absence of contrary evidence does not answer a question")
    if not resposta.strip():
        raise ErroDePergunta("answer is required")
    with _travado():
        itens = _ler()
        q = _achar(itens, qid)
        if q["revision"] != revisao_esperada:
            raise ErroDePergunta(f"conflict: question is at revision {q['revision']}, not {revisao_esperada}")
        if q["status"] not in ABERTOS:
            raise ErroDePergunta(f"question is already {q['status']}")
        q["status"] = "answered"
        q["revision"] += 1
        q["updated"] = _agora()
        q["resolution"] = {"answer": resposta.strip(), "evidence": notas, "by": autor, "when": q["updated"]}
        _gravar(itens)
        return q


def listar(estado: str = "open", assunto: str = "", raiz: Path | None = None) -> list[dict]:
    itens = _ler()
    if estado == "open":
        itens = [i for i in itens if i["status"] in ABERTOS]
    elif estado != "all":
        itens = [i for i in itens if i["status"] == estado]
    if assunto:
        itens = [i for i in itens if assunto.lower() in (i["topic"] + " " + i["question"]).lower()]
    ordem = {s: n for n, s in enumerate(reversed(SEVERIDADES))}
    itens = sorted(itens, key=lambda i: (ordem[i["severity"]], i["created"]))
    if raiz is not None:
        # Evidencia que sumiu do vault (nota esquecida, renomeada) aparece, nao some em silencio.
        for i in itens:
            todas = i["supporting"] + i["contradicting"] + ((i.get("resolution") or {}).get("evidence") or [])
            perdidas = [c for c in todas if not (Path(raiz) / c).is_file()]
            if perdidas:
                i["missing_evidence"] = perdidas
    return itens
