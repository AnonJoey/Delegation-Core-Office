"""Tarefas recorrentes por cron, com estado em disco e contagem de falha.

## Por que existe

O delegation-core so sabia agendar uma vez (`local_task_submit` com
`run_after`). Tudo que precisa acontecer de novo dependia de alguem lembrar,
ou de um hook de sessao do Claude Code, que so roda quando alguem abre o
Claude Code. Nesta maquina o `reindex.log` ficou parado de 01/09 a 26/09 sem
que nada avisasse.

O openclaw (`src/cron/`, com `failure-alerts.ts`) e o hermes
(`cron/scheduler.py`) tem agenda propria com alerta de falha. Esta traz o
nucleo disso.

## Regras

- **Primeira vez que uma tarefa aparece nao dispara.** A ancora e o momento em
  que ela foi vista; a primeira execucao e o proximo horario depois disso.
  Sem isso, subir o daemon dispararia toda tarefa de uma vez.
- **Atraso nao vira rajada.** Se o daemon ficou fora durante varios horarios, a
  tarefa roda uma vez so e a ancora pula para agora. Doze reindex seguidos
  depois de uma noite desligado nao servem a ninguem.
- **Falha conta.** `falhas_seguidas` volta a zero no primeiro sucesso; e o que
  o alerta de falha le.

## Criterio de lego

Recebe tarefas e um executor por chamada; guarda estado num JSON. Nao sabe o
que cada acao faz, nem o que e daemon, vault ou MCP.
"""

from __future__ import annotations

import json
import os
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .cron import Cron, CronInvalido


@dataclass
class Tarefa:
    nome: str
    cron: str
    acao: str
    argumentos: dict = field(default_factory=dict)
    ligada: bool = True

    def expressao(self) -> Cron:
        return Cron.ler(self.cron)


def tarefas_de_config(lista: list[dict]) -> tuple[list[Tarefa], list[str]]:
    """Le a lista da config. Tarefa com cron invalido fica de fora e vira erro legivel."""
    ok, erros = [], []
    nomes = set()
    for i, d in enumerate(lista or []):
        try:
            t = Tarefa(nome=str(d["nome"]), cron=str(d["cron"]), acao=str(d["acao"]),
                       argumentos=dict(d.get("argumentos") or {}), ligada=bool(d.get("ligada", True)))
            t.expressao()
        except (KeyError, TypeError, ValueError, CronInvalido) as e:
            erros.append(f"tarefa {i}: {e}")
            continue
        if t.nome in nomes:
            erros.append(f"tarefa {i}: nome repetido '{t.nome}'")
            continue
        nomes.add(t.nome)
        ok.append(t)
    return ok, erros


class Agenda:
    def __init__(self, caminho_estado: str | Path, tarefas: list[Tarefa]):
        self.caminho = Path(caminho_estado)
        self.tarefas = {t.nome: t for t in tarefas}
        self._trava = threading.Lock()
        self._estado = self._ler()

    # ── estado ─────────────────────────────────────────────────────────────

    def _ler(self) -> dict:
        try:
            d = json.loads(self.caminho.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            return {}

    def _gravar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_name(self.caminho.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self._estado, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def estado(self, nome: str) -> dict:
        with self._trava:
            return dict(self._estado.get(nome, {}))

    # ── quando ─────────────────────────────────────────────────────────────

    def devidas(self, agora: datetime | None = None) -> list[Tarefa]:
        """As tarefas cujo proximo horario depois da ancora ja passou."""
        agora = agora or datetime.now()
        saida = []
        mudou = False
        with self._trava:
            for t in self.tarefas.values():
                if not t.ligada:
                    continue
                e = self._estado.setdefault(t.nome, {})
                if "ancora" not in e:
                    e["ancora"] = agora.isoformat(timespec="seconds")
                    mudou = True
                    continue
                if e.get("rodando"):
                    continue
                ancora = datetime.fromisoformat(e["ancora"])
                if t.expressao().proxima(ancora) <= agora:
                    saida.append(t)
            if mudou:
                self._gravar()
        return saida

    def proximas(self, agora: datetime | None = None) -> list[dict]:
        agora = agora or datetime.now()
        saida = []
        with self._trava:
            for t in self.tarefas.values():
                e = self._estado.get(t.nome, {})
                base = datetime.fromisoformat(e["ancora"]) if "ancora" in e else agora
                saida.append({
                    **asdict(t),
                    "proxima": t.expressao().proxima(base).isoformat(timespec="minutes") if t.ligada else None,
                    **{k: v for k, v in e.items() if k != "ancora"},
                })
        return sorted(saida, key=lambda d: d["proxima"] or "9999")

    # ── executar ───────────────────────────────────────────────────────────

    def executar(self, tarefa: Tarefa, executor: Callable[[dict], object],
                 agora: datetime | None = None) -> dict:
        """Roda uma vez, registra resultado e duracao, e move a ancora para agora."""
        agora = agora or datetime.now()
        with self._trava:
            e = self._estado.setdefault(tarefa.nome, {})
            e["rodando"] = True
            e["ancora"] = agora.isoformat(timespec="seconds")
            self._gravar()
        t0 = time.monotonic()
        try:
            resultado = executor(dict(tarefa.argumentos))
            erro = None
        except Exception as ex:  # noqa: BLE001 - a agenda registra, nao propaga
            resultado = None
            erro = f"{type(ex).__name__}: {ex}"
            detalhe = traceback.format_exc(limit=3)
        dur = round(time.monotonic() - t0, 2)
        with self._trava:
            e = self._estado.setdefault(tarefa.nome, {})
            e.pop("rodando", None)
            e["ultima_execucao"] = agora.isoformat(timespec="seconds")
            e["ultima_duracao_s"] = dur
            e["execucoes"] = int(e.get("execucoes", 0)) + 1
            if erro is None:
                e["ultimo_status"] = "ok"
                e["falhas_seguidas"] = 0
                e.pop("ultimo_erro", None)
                e.pop("ultimo_detalhe", None)
                e["ultimo_resultado"] = _resumo(resultado)
            else:
                e["ultimo_status"] = "erro"
                e["falhas_seguidas"] = int(e.get("falhas_seguidas", 0)) + 1
                e["ultimo_erro"] = erro
                e["ultimo_detalhe"] = detalhe
            self._gravar()
            return dict(e)

    def destravar_orfas(self) -> list[str]:
        """Tarefa marcada como rodando quando o processo morreu nunca mais rodaria. Solta."""
        soltas = []
        with self._trava:
            for nome, e in self._estado.items():
                if e.pop("rodando", None):
                    e["ultimo_status"] = "interrompida"
                    soltas.append(nome)
            if soltas:
                self._gravar()
        return soltas


def _resumo(r: object, limite: int = 500) -> object:
    """O resultado cabe no estado se for pequeno; senao so o tamanho vai."""
    try:
        s = json.dumps(r, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(r)
    return r if len(s) <= limite else {"resumo": s[:limite] + "...", "tamanho": len(s)}
