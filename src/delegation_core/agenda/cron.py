"""Expressao cron de cinco campos: minuto hora dia-do-mes mes dia-da-semana.

Aceita `*`, lista (`1,15`), intervalo (`9-17`), passo (`*/10`, `8-18/2`) e os
atalhos `@hourly`, `@daily`, `@weekly`, `@monthly`. Dia da semana vai de 0 a 6
com domingo em 0, e 7 tambem e domingo, como no cron do Linux.

A regra classica de dia: se dia-do-mes e dia-da-semana forem ambos restritos,
vale qualquer um dos dois (OU), e nao os dois juntos. E o comportamento do
Vixie cron, e quem escreve `0 9 1 * 1` espera "todo dia 1 e toda segunda".

Funcao pura, sem dependencia: o openclaw e o hermes trazem biblioteca de cron,
e aqui a necessidade cabe em cem linhas testadas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

_ATALHOS = {
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}

_LIMITES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 7)]
_NOMES = ["minuto", "hora", "dia do mes", "mes", "dia da semana"]


class CronInvalido(ValueError):
    pass


def _campo(texto: str, minimo: int, maximo: int, nome: str) -> frozenset[int]:
    valores: set[int] = set()
    for parte in texto.split(","):
        if not parte:
            raise CronInvalido(f"{nome}: item vazio em '{texto}'")
        passo = 1
        if "/" in parte:
            parte, p = parte.split("/", 1)
            if not p.isdigit() or int(p) == 0:
                raise CronInvalido(f"{nome}: passo invalido '{p}'")
            passo = int(p)
        if parte == "*":
            ini, fim = minimo, maximo
        elif "-" in parte:
            a, b = parte.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronInvalido(f"{nome}: intervalo invalido '{parte}'")
            ini, fim = int(a), int(b)
        elif parte.isdigit():
            ini = fim = int(parte)
            if passo > 1:
                fim = maximo
        else:
            raise CronInvalido(f"{nome}: valor invalido '{parte}'")
        if ini < minimo or fim > maximo or ini > fim:
            raise CronInvalido(f"{nome}: {ini}-{fim} fora de {minimo}-{maximo}")
        valores.update(range(ini, fim + 1, passo))
    return frozenset(valores)


@dataclass(frozen=True)
class Cron:
    texto: str
    minutos: frozenset[int]
    horas: frozenset[int]
    dias: frozenset[int]
    meses: frozenset[int]
    semana: frozenset[int]
    dia_restrito: bool
    semana_restrita: bool

    @classmethod
    def ler(cls, texto: str) -> "Cron":
        bruto = (texto or "").strip()
        expr = _ATALHOS.get(bruto.lower(), bruto)
        partes = expr.split()
        if len(partes) != 5:
            raise CronInvalido(f"cron precisa de 5 campos, veio {len(partes)}: '{texto}'")
        campos = [_campo(p, a, b, n) for p, (a, b), n in zip(partes, _LIMITES, _NOMES)]
        semana = frozenset(0 if d == 7 else d for d in campos[4])
        return cls(bruto, campos[0], campos[1], campos[2], campos[3], semana,
                   partes[2] != "*", partes[4] != "*")

    def casa(self, t: datetime) -> bool:
        if t.minute not in self.minutos or t.hour not in self.horas or t.month not in self.meses:
            return False
        dow = (t.weekday() + 1) % 7  # Python: segunda=0; cron: domingo=0
        dia_ok = t.day in self.dias
        sem_ok = dow in self.semana
        if self.dia_restrito and self.semana_restrita:
            return dia_ok or sem_ok
        return dia_ok and sem_ok

    def proxima(self, depois: datetime) -> datetime:
        """O primeiro minuto estritamente depois de `depois` que casa.

        Anda por dia quando o dia nao serve e por hora quando a hora nao serve,
        em vez de minuto a minuto; o pior caso (29 de fevereiro) fica em alguns
        milhares de passos, nao em meio milhao.
        """
        t = depois.replace(second=0, microsecond=0) + timedelta(minutes=1)
        limite = t + timedelta(days=366 * 5)
        while t <= limite:
            if t.month not in self.meses:
                t = (t.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
                continue
            dow = (t.weekday() + 1) % 7
            dia_ok = t.day in self.dias
            sem_ok = dow in self.semana
            dia_serve = (dia_ok or sem_ok) if (self.dia_restrito and self.semana_restrita) else (dia_ok and sem_ok)
            if not dia_serve:
                t = t.replace(hour=0, minute=0) + timedelta(days=1)
                continue
            if t.hour not in self.horas:
                t = t.replace(minute=0) + timedelta(hours=1)
                continue
            if t.minute not in self.minutos:
                t += timedelta(minutes=1)
                continue
            return t
        raise CronInvalido(f"'{self.texto}' nao casa com nenhuma data nos proximos 5 anos")
