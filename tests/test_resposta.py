"""Resposta com citacao conferida: so volta a afirmacao cuja citacao esta na fonte."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import delegation_core.server as server
from delegation_core import sonho_vault
from delegation_core.resposta import Fonte, janela, responder
from delegation_core.resposta.responder import conferir

F = [Fonte("Fixes/porta.md", "O daemon **escuta** na porta 8787 desde a migracao de agosto, por causa do conflito."),
     Fonte("Decisions/gpu.md", "Decidimos rodar o BGE-m3 na CPU porque os dois modelos nao cabem na placa de 16 GB.")]


def modelo(d):
    return lambda system, prompt: (json.dumps(d) if "numbered sources" in system else "")


def claim(t, n, q):
    return {"text": t, "source": n, "quote": q}


def test_so_fica_o_que_a_citacao_prova():
    r = responder("qual porta?", F, modelo({"found": True, "claims": [
        claim("A porta e 8787.", 1, "o daemon escuta na porta 8787 desde a migracao"),     # caixa, negrito
        claim("E 8797.", 1, "o daemon escuta na porta 8797 desde a migracao"),             # inventada
        claim("BGE na CPU.", 1, "rodar o BGE-m3 na CPU porque os dois"),                  # fonte errada
        claim("Fonte 9.", 9, "qualquer coisa com cinco palavras aqui"),
        claim("Curta.", 2, "na CPU"),
        claim("A porta e 8787.", 1, "escuta na porta 8787 desde a"),                     # repetida
        claim("", 1, "o daemon escuta na porta"), "lixo"]}))
    assert r["found"] and [c["text"] for c in r["claims"]] == ["A porta e 8787."]
    assert r["claims"][0]["source"] == "Fixes/porta.md"
    assert [d["reason"] for d in r["dropped"]] == [
        "citacao nao esta na fonte", "citacao nao esta na fonte", "fonte inexistente",
        "citacao curta demais para provar algo", "repetida", "sem texto ou citacao"]
    assert r["answer"] == "A porta e 8787."


def test_modelo_diz_que_achou_mas_nada_confere():
    r = responder("x", F, modelo({"found": True, "claims": [claim("inventado", 2, "isto nao esta em lugar nenhum mesmo")]}))
    assert r["found"] is False and r["model_said_found"] is True and r["answer"] == ""


def test_resposta_nao_json_e_sem_fontes():
    assert responder("x", F, lambda s, p: "desculpe, nao sei")["found"] is False
    assert responder("x", [], lambda s, p: 1 / 0)["found"] is False     # nem pergunta


def test_aspas_curvas_e_citacao_com_aspas():
    ok, _ = conferir([claim("ok", 1, "“o daemon escuta na porta 8787”")], F)
    assert len(ok) == 1


def test_janela_vai_para_os_termos():
    texto = "a" * 3000 + " porta 8787 do daemon " + "b" * 3000
    j = janela(texto, ["porta", "daemon"], 500)
    assert "porta 8787" in j and len(j) <= 500
    assert janela("curto", ["x"], 500) == "curto"
    assert janela("é" * 2000, ["zzz"], 100) == "é" * 100
    # acento nao desloca a posicao
    t = "ação " * 400 + " configuração do llama " + "x" * 2000
    assert "configuração do llama" in janela(t, ["configuracao", "llama"], 300)
    # so o termo acentuado casa: sem dobrar o acento, a janela caia no comeco
    t = "x" * 3000 + " a configuração nova " + "y" * 3000
    assert "configuração nova" in janela(t, ["configuracao"], 300)


def test_ask_vault(tmp_path, monkeypatch):
    raiz = tmp_path / "v"
    (raiz / "Fixes").mkdir(parents=True)
    (raiz / "Fixes" / "porta.md").write_text(F[0].texto)
    cfg = SimpleNamespace(vault=raiz)

    async def busca_falsa(**k):
        return json.dumps({"sources": [{"path": "Fixes/porta.md", "superseded_by": [{"by": "Fixes/nova.md"}]},
                                       {"path": "Fixes/sumiu.md"}], "facts": [{"subject": "daemon"}]})
    monkeypatch.setattr(server, "search_vault", busca_falsa)
    monkeypatch.setattr(server, "_vault", SimpleNamespace(cfg=cfg))
    monkeypatch.setattr(sonho_vault, "perguntar_local", lambda cfg, max_tokens, tarefa: modelo(
        {"found": True, "claims": [claim("Porta 8787.", 1, "escuta na porta 8787 desde a migracao")]}))
    r = json.loads(asyncio.run(server.ask_vault(question="qual porta?")))
    assert r["found"] and r["claims"][0]["source_superseded_by"] == ["Fixes/nova.md"]
    assert r["sources"] == ["Fixes/porta.md"] and r["facts"] == [{"subject": "daemon"}]

    def quebra(cfg, max_tokens, tarefa):
        def p(s, q):
            raise ConnectionError("llama fora")
        return p
    monkeypatch.setattr(sonho_vault, "perguntar_local", quebra)
    assert json.loads(asyncio.run(server.ask_vault(question="x")))["error_type"] == "failure"
