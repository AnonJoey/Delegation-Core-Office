"""Pedidos de aprovacao humana: um arquivo JSON, gravado de forma atomica.

Cada pedido amarra cliente, ferramenta e o hash dos argumentos. A aprovacao vale
uma vez, so para aqueles argumentos, e vence em `validade_h` horas: aprovar
"apagar a nota X" nao pode virar licenca para apagar a nota Y.

O que a pessoa ve para decidir e uma previa dos argumentos, cortada e com
segredo coberto (pacote `segredos`). O livro-caixa guarda so o hash; aqui a
previa existe porque ninguem aprova o que nao consegue ler.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from ..arquivos_json import ler_json

ESTADOS = ("pending", "approved", "denied", "used", "expired")


def hash_args(argumentos: dict | None) -> str:
    texto = json.dumps(argumentos or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def previa(argumentos: dict | None, limite: int = 160) -> dict:
    from ..segredos import redigir
    saida = {}
    for k, v in sorted((argumentos or {}).items()):
        t = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
        t, _ = redigir(t)
        saida[k] = t if len(t) <= limite else t[:limite] + f"... (+{len(t) - limite} chars)"
    return saida


def _agora() -> datetime:
    return datetime.now().replace(microsecond=0)


class Aprovacoes:
    def __init__(self, caminho: Path, validade_h: float = 24.0, relogio=_agora):
        self.caminho = Path(caminho)
        self.validade = timedelta(hours=validade_h)
        self._relogio = relogio
        self._trava = threading.Lock()

    # ── leitura e escrita ────────────────────────────────────────────────────

    def _ler(self) -> list[dict]:
        return ler_json(self.caminho, list)

    def _gravar(self, pedidos: list[dict]) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.caminho.with_suffix(".tmp")
        tmp.write_text(json.dumps(pedidos, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.caminho)

    def _vencer(self, pedidos: list[dict]) -> bool:
        agora = self._relogio().isoformat()
        mudou = False
        for p in pedidos:
            if p["status"] in ("pending", "approved") and p["expires"] < agora:
                p["status"] = "expired"
                mudou = True
        return mudou

    # ── o que o middleware usa ───────────────────────────────────────────────

    def consumir_ou_pedir(self, cliente: str, ferramenta: str, argumentos: dict | None) -> tuple[bool, dict]:
        """(True, pedido) se havia aprovacao valida, que fica gasta.
        (False, pedido) com o pedido pendente, novo ou ja existente."""
        h = hash_args(argumentos)
        with self._trava:
            pedidos = self._ler()
            self._vencer(pedidos)
            for p in pedidos:
                if (p["client"], p["tool"], p["args_hash"]) != (cliente, ferramenta, h):
                    continue
                if p["status"] == "approved":
                    p["status"] = "used"
                    p["used"] = self._relogio().isoformat()
                    self._gravar(pedidos)
                    return True, p
                if p["status"] == "pending":
                    self._gravar(pedidos)
                    return False, p
            agora = self._relogio()
            novo = {
                "id": "apr_" + uuid.uuid4().hex[:8],
                "client": cliente, "tool": ferramenta, "args_hash": h,
                "args_preview": previa(argumentos),
                "status": "pending", "created": agora.isoformat(),
                "expires": (agora + self.validade).isoformat(),
                "decided": None, "decided_by": None, "reason": "",
            }
            pedidos.append(novo)
            self._gravar(pedidos)
            return False, novo

    # ── o que a pessoa usa (CLI) ─────────────────────────────────────────────

    def listar(self, status: str = "pending") -> list[dict]:
        with self._trava:
            pedidos = self._ler()
            if self._vencer(pedidos):
                self._gravar(pedidos)
        if status != "all":
            pedidos = [p for p in pedidos if p["status"] == status]
        return sorted(pedidos, key=lambda p: p["created"], reverse=True)

    def decidir(self, pedido_id: str, aprovar: bool, por: str = "cli", motivo: str = "") -> dict | None:
        """None se o id nao existe. Um pedido que nao esta pendente volta como esta."""
        with self._trava:
            pedidos = self._ler()
            self._vencer(pedidos)
            achados = [p for p in pedidos if p["id"] == pedido_id or p["id"].startswith(pedido_id)]
            if len(achados) != 1:
                return None
            p = achados[0]
            if p["status"] == "pending":
                p["status"] = "approved" if aprovar else "denied"
                p["decided"] = self._relogio().isoformat()
                p["decided_by"] = por
                p["reason"] = motivo
            self._gravar(pedidos)
            return p

    def limpar(self, manter_dias: int = 30) -> int:
        """Apaga pedidos decididos ha mais de N dias. Devolve quantos saíram."""
        corte = (self._relogio() - timedelta(days=manter_dias)).isoformat()
        with self._trava:
            pedidos = self._ler()
            ficam = [p for p in pedidos if p["status"] in ("pending", "approved") or p["created"] >= corte]
            if len(ficam) != len(pedidos):
                self._gravar(ficam)
            return len(pedidos) - len(ficam)
