"""Cache do compress: so reusa com entrada identica, troca de modelo invalida, ruim nao entra."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import delegation_core.server as server
from delegation_core import cache_resultado


def _motor(monkeypatch, tmp_path, resposta="Decisao: migrar o servico de busca em outubro de 2026."):
    chamadas = []
    modelo = tmp_path / "m.gguf"
    if not modelo.exists():
        modelo.write_bytes(b"v1")

    class Motor:
        cfg = SimpleNamespace(is_cpu_budget=False, route=lambda **k: "local", synthesis_lang="pt",
                              llama_model=str(modelo))

        async def invoke(self, prompt, system="", **k):
            chamadas.append(prompt)
            return resposta

        def budget(self, task, requested=0):
            return requested

    async def direto(nome, fazer):
        return await fazer(Motor())

    monkeypatch.setattr(server, "_engine", Motor())
    monkeypatch.setattr(server, "_run_or_queue", direto)
    return chamadas, modelo


def _c(texto, fonte="email"):
    return json.loads(asyncio.run(server.compress(source=fonte, raw_content=texto, use_local=True)))


def test_segunda_chamada_identica_vem_do_cache(monkeypatch, tmp_path):
    chamadas, _ = _motor(monkeypatch, tmp_path)
    texto = "texto longo " * 100
    a, b = _c(texto), _c(texto)
    assert len(chamadas) == 1 and a["cached"] is False and b["cached"] is True
    assert a["compressed"] == b["compressed"]
    _c(texto + "!")
    _c(texto, fonte="outra")
    assert len(chamadas) == 3, "um byte diferente, ou outra fonte, e outra chave"


def test_trocar_o_modelo_invalida(monkeypatch, tmp_path):
    import os
    chamadas, modelo = _motor(monkeypatch, tmp_path)
    texto = "texto " * 100
    _c(texto)
    modelo.write_bytes(b"versao 2 maior")
    _c(texto)
    assert len(chamadas) == 2


def test_resultado_ruim_nao_entra(monkeypatch, tmp_path):
    chamadas, _ = _motor(monkeypatch, tmp_path, resposta="ok")
    texto = "texto " * 100
    _c(texto)
    _c(texto)
    assert len(chamadas) == 2


def test_limite_de_entradas(monkeypatch):
    monkeypatch.setattr(cache_resultado, "MAXIMO", 3)
    for i in range(5):
        cache_resultado.gravar(f"k{i}", "v")
    assert cache_resultado.ler("k0") is None and cache_resultado.ler("k4") == "v"
    assert cache_resultado.limpar() == 3
