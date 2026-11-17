"""Regras avaliadas sobre o estado do sistema, com pendente, disparando e resolvido.

## Por que existe

Tudo que deu errado no delegation-core ate aqui foi achado porque alguem
perguntou. As 284 notas com carimbo desatualizado de 26/09 estavam la
enquanto a saude dizia `unindexed: 2`; o `reindex.log` ficou parado 25 dias;
a sentinela `no_auto_reindex` ficou esquecida desde 31/08. Nada disso gritou.

O grafana resolve isso com o `ngalert` (`pkg/services/ngalert/eval`,
`schedule`, `notifications`): regra avaliada em intervalo, estado com periodo
de espera, e aviso so na transicao. Este modulo e o nucleo desse desenho.

## Estados, por sujeito

Uma regra devolve os sujeitos que estao errados agora (uma nota, um processo,
um disco). Cada par (regra, sujeito):

- aparece pela primeira vez: **pendente**
- continua aparecendo por `para_s` segundos: **disparando**, e gera evento "aberto"
- some: se estava disparando, gera evento "resolvido"; se so pendente, some calado

O periodo de espera e o que separa um tropeco de um problema: um reindex que
ficou 30 s atrasado nao e alerta, um que ficou 2 h e.

## Criterio de lego

Recebe regras (funcoes) e um contexto qualquer; guarda estado num JSON e
devolve eventos. Nao sabe o que e vault, config, daemon, nem como avisar.
Quem avisa e quem liga isto ao sistema recebe os eventos.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

SEVERIDADES = ("info", "aviso", "critico")


@dataclass
class Disparo:
    sujeito: str
    mensagem: str
    detalhe: dict = field(default_factory=dict)


@dataclass
class Regra:
    nome: str
    avaliar: Callable[[object], list[Disparo]]
    severidade: str = "aviso"
    para_s: float = 0.0
    descricao: str = ""


class MotorDeAlertas:
    def __init__(self, caminho_estado: str | Path, regras: list[Regra]):
        self.caminho = Path(caminho_estado)
        self.regras = {r.nome: r for r in regras}
        self._trava = threading.Lock()
        try:
            d = json.loads(self.caminho.read_text(encoding="utf-8"))
            self._estado = d if isinstance(d, dict) else {}
        except (OSError, ValueError):
            self._estado = {}
        self._estado.setdefault("alertas", {})
        self._estado.setdefault("eventos", [])

    def _gravar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_name(self.caminho.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(self._estado, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def avaliar(self, contexto: object, agora: float | None = None,
                manter_eventos: int = 200) -> dict:
        """Roda todas as regras; devolve os eventos desta rodada e os alertas abertos.

        Regra que levanta excecao vira um alerta dela mesma (`regra_quebrada`),
        em vez de derrubar a avaliacao das outras: uma regra quebrada e um
        problema real, e calado seria o pior jeito de tratar.
        """
        agora = time.time() if agora is None else agora
        vistos: dict[str, Disparo] = {}
        for r in self.regras.values():
            try:
                disparos = r.avaliar(contexto) or []
            except Exception as e:  # noqa: BLE001
                disparos = [Disparo(f"regra:{r.nome}", f"a regra {r.nome} quebrou: {type(e).__name__}: {e}")]
                r = Regra("regra_quebrada", r.avaliar, "aviso", 0.0)
            for d in disparos:
                vistos[f"{r.nome}|{d.sujeito}"] = (r, d)

        eventos = []
        with self._trava:
            alertas = self._estado["alertas"]
            for chave, (r, d) in vistos.items():
                a = alertas.get(chave)
                if a is None:
                    a = alertas[chave] = {"regra": r.nome, "sujeito": d.sujeito, "severidade": r.severidade,
                                          "estado": "pendente", "desde": agora}
                a.update(mensagem=d.mensagem, detalhe=d.detalhe, visto_em=agora)
                if a["estado"] == "pendente" and agora - a["desde"] >= r.para_s:
                    a["estado"] = "disparando"
                    a["disparou_em"] = agora
                    eventos.append({"tipo": "aberto", "em": agora, **_publico(a)})
            for chave in [c for c in alertas if c not in vistos]:
                a = alertas.pop(chave)
                if a["estado"] == "disparando":
                    eventos.append({"tipo": "resolvido", "em": agora, "durou_s": round(agora - a["disparou_em"]),
                                    **_publico(a)})
            self._estado["eventos"] = (self._estado["eventos"] + eventos)[-manter_eventos:]
            self._estado["avaliado_em"] = agora
            self._gravar()
            abertos = [_publico(a) for a in alertas.values() if a["estado"] == "disparando"]
            pendentes = [_publico(a) for a in alertas.values() if a["estado"] == "pendente"]
        ordem = {s: i for i, s in enumerate(reversed(SEVERIDADES))}
        abertos.sort(key=lambda a: (ordem.get(a["severidade"], 9), a["regra"], a["sujeito"]))
        return {"eventos": eventos, "abertos": abertos, "pendentes": pendentes}

    def abertos(self) -> list[dict]:
        with self._trava:
            return [_publico(a) for a in self._estado["alertas"].values() if a["estado"] == "disparando"]

    def eventos(self, limite: int = 50) -> list[dict]:
        with self._trava:
            return list(reversed(self._estado["eventos"][-limite:]))


def _publico(a: dict) -> dict:
    return {k: a[k] for k in ("regra", "sujeito", "severidade", "estado", "mensagem", "detalhe", "desde")
            if k in a}
