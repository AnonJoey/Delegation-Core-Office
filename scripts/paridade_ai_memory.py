"""Paridade do porte do ai-memory com o codigo original, compilado.

Uso: python scripts/paridade_ai_memory.py [-n CASOS] [--so grupo,grupo] [--semente N] [-v] [--mutacoes]

As funcoes puras do ai-memory (decaimento, minerador de fatos, compactacao, trechos, niveis do
resumo, autoridade, escolha de passagem) estao copiadas, sem alteracao, em
`scripts/oraculo_ai_memory` e compiladas num programa que le um caso por linha de JSON. Este script
sorteia os casos, roda o oraculo e o porte em Python, e compara o resultado. Construir o oraculo:

    cd scripts/oraculo_ai_memory && cargo +1.95 build --release

(`AI_MEMORY_ORACULO` aponta para outro binario.) Os casos sao sorteados para quebrar um porte: texto
com espaco Unicode e fim de linha misto, UTF-8 de varios bytes no limite do corte, caminhos Windows,
frontmatter com tipo errado, orcamentos que cabem por um byte.

`--mutacoes` injeta, um a um, defeitos conhecidos no porte e confere que a paridade os acusa: uma
paridade que nao falha quando o porte erra nao prova nada.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import subprocess
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from delegation_core.envelhecimento import compactacao as _compactacao  # noqa: E402
from delegation_core.envelhecimento import fatos_duraveis as _fatos  # noqa: E402
from delegation_core.envelhecimento import retencao as _ret  # noqa: E402
from delegation_core.envelhecimento import varredura as _var  # noqa: E402
from delegation_core.passagem import caminhos as _cam  # noqa: E402
from delegation_core.ranqueamento import autoridade as _aut  # noqa: E402
from delegation_core.resumo_inicial import niveis as _niv  # noqa: E402
from delegation_core.resumo_inicial import trecho as _tre  # noqa: E402
from delegation_core import texto_bytes as _tb  # noqa: E402

ORACULO = Path(os.environ.get("AI_MEMORY_ORACULO", RAIZ / "scripts/oraculo_ai_memory/target/release/oraculo-ai-memory"))

CAMADAS = ["working", "episodic", "semantic", "procedural"]


# ── sorteio ─────────────────────────────────────────────────────────────────

URLS = ["https://github.com/akitaonrails/ai-memory/issues/776", "http://x.io/p?q=1&r=2).", "(https://e.com/a)", "https://ünicode.com/é",
        "see https://a.b/c, and", "https://a.b/c\"d", "http://[::1]:8080/x"]
CAMINHOS = ["crates/ai-memory-store/src/ops.rs", "src/delegation_core/server.py", "./a/b.txt", "docs/ação.md", "C:/x/y.rs", "~/x/y.json",
            "a/b/c.tar.gz", "x/y", "dir/sub/arquivo.final.v2.toml", "(src/lib.rs)", "/var/lib/app/state.done"]
ARQUIVOS = ["ops.rs", "lib.rs", "config.yaml", "Makefile", "a.PY", "x.tsx", "foo.bar", "_x.sh", "z.proto", "readme.MD"]
CODIGOS = ["E0433", "E12", "E99999", "HTTP 500", "HTTP500", "HTTP\t404", "http 500", "HTTP  500", "E0001x"]
SPANS = ["`run_sweep_with_compaction`", "`a b`", "``", "`x\ny`", "`" + "z" * 130 + "`", "`ação`", "`  `"]
CONSTANTES = ["AI_MEMORY_AUTH_TOKEN", "ABC_1", "A_B", "A__B", "a_B", "X_Y_Z_9"]
IDENTS = ["snake_case_name", "camelCase", "HTTPServer", "a_b", "some_ID", "x", "ação_nome", "fooBar9", "lowerUPPER"]
PROSA = ["We talked about the plan.", "Falamos sobre isso, em português.", "Vamos rever depois.", "Everyone agreed it was subtle.",
         "Resumo: tudo certo.", "ação de revisão pendente", "texto simples sem nada"]
SEPS = [" ", " ", " ", "\n", "\n\n", "\r\n", "\t", "\u00a0", "\u2028", "\x1c", "\x85", "  ", ", ", "; ", ": "]
ERROS = ["error[E0433]: failed to resolve: use of undeclared crate `bar`", "TypeError: Cannot read properties of undefined",
         "thread 'main' panicked at src/x.rs:1:1:", "FAILED. 3 passed; 1 failed", "ERROR:  cannot execute UPDATE in a read-only transaction",
         "ERRO:  valor duplicado", "Traceback (most recent call last):", "fatal: not a git repository", "ERR! code ELIFECYCLE",
         "error: short diagnostic `bar`", "ERRO: " + "ação " * 40 + "`fim`", "MyException: boom", "FATAL: x"]
VERSOES = ["v2.6.3-rc1", "192.0.2.11", "1.95", "python3.12.4", "20.20.0", "v2.6.3", "1.2.3.4", "0.0.0+build.5"]


def juntar(rng: random.Random, pecas: list[str], n: int) -> str:
    saida = []
    for _ in range(n):
        saida.append(rng.choice(pecas))
        saida.append(rng.choice(SEPS))
    return "".join(saida)


def sujar(rng: random.Random, texto: str) -> str:
    """Troca ou apaga um caractere, as vezes: a fronteira entre casar e nao casar."""
    if not texto or rng.random() > 0.3:
        return texto
    i = rng.randrange(len(texto))
    return texto[:i] + rng.choice(["", "\u00e7", "\U0001F600", "_", ".", "/", "`", "\u3000", "\u200b", "\x1f"]) + texto[i + 1:]


def corpo_de_fatos(rng: random.Random) -> str:
    pecas = URLS + CAMINHOS + ARQUIVOS + CODIGOS + SPANS + CONSTANTES + IDENTS + PROSA
    return sujar(rng, juntar(rng, pecas, rng.randint(0, 40)))


def corpo_de_residuo(rng: random.Random) -> str:
    pecas = ERROS + VERSOES + URLS + CAMINHOS + ARQUIVOS + CODIGOS + CONSTANTES + PROSA
    return sujar(rng, juntar(rng, pecas, rng.randint(0, 30)))


TITULOS = ["# Titulo", "## Context", "---", "# ", "#sem espaco"]
METADADOS = ["**Status:** accepted", "**Date**: 2026-10-01", "- **Owner:** Alice", "Status:** Accepted", "**Package manager:** pnpm",
             "**Status:** accepted   <!-- proposed | accepted -->", "__Author__: x", "**A B C D:** nao", "**Status.** x", "*Tags:* a"]
FRASES = ["Use nextest.", "Readers blocked the writer under load.", "Ação importante para a equipe inteira.", "Rule one. Rule two.",
          "Uma frase um pouco mais longa para ocupar espaco no trecho e forcar o corte em bytes depois." * 3, "- item de lista", "* outro item",
          "x" * 300, "ação " * 130]
RODAPES = [_compactacao.RODAPE, _compactacao.RODAPE_AI_MEMORY, "_Extractively compacted from a cold episodic page"]


def corpo_de_nota(rng: random.Random) -> str:
    blocos = []
    for _ in range(rng.randint(0, 8)):
        r = rng.random()
        if r < 0.15:
            blocos.append(rng.choice(TITULOS))
        elif r < 0.3:
            blocos.append(rng.choice(METADADOS))
        elif r < 0.35:
            blocos.append(rng.choice(RODAPES))
        else:
            quebra = rng.choice(["\n", "\n", "\n", "\r\n", "\r", "\x0b", "\x0c", "\x1c", "\x85", "\u2028", "\u2029"])
            blocos.append(quebra.join(rng.choice(FRASES + PROSA + METADADOS) for _ in range(rng.randint(1, 4))))
    sep = rng.choice(["\n\n", "\n\n", "\n\n\n", "\r\n\r\n", "\n \n"])
    return sujar(rng, sep.join(blocos))


VOCABULARIO_DE_ETIQUETAS = ["canonical", "source-of-truth", "active", "do-not-answer-from", "test-fixture", "superseded", "historical", "Canonical",
                            "HISTORICAL", "do_not_answer_from", " active ", "outra", "source_of_truth", "Superseded"]


def frontmatter(rng: random.Random) -> object:
    r = rng.random()
    if r < 0.08:
        return None
    if r < 0.12:
        return rng.choice([[], "texto", 7])
    fm = {}
    if rng.random() < 0.5:
        fm["tags"] = rng.sample(VOCABULARIO_DE_ETIQUETAS, rng.randint(0, 3))
    for chave in ("abstract", "summary", "title", "tags"):
        if chave in fm:
            continue
        if rng.random() < 0.5:
            fm[chave] = rng.choice([
                "Um resumo curto.", "  Com espacos  \n nas pontas ", "", "   \n\t", 7, None, ["a"], True, "ação " * 60, "x" * 400,
                "Resumo com\nquebra", ["Canonical", "ACTIVE", "do_not_answer_from", "historical", "Superseded", " Test-Fixture "], ["x", 1, None]])
    return fm


def caso_retencao(rng: random.Random) -> dict:
    params = {"lambda": rng.choice([0.02, 0.02, 0.005, 0.1, 0.0, 0.3]), "sigma": rng.choice([0.6, 0.6, 0.0, 1.5]),
              "mu": rng.choice([0.04, 0.04, 0.0, 0.2]), "salience_default": rng.choice([1.0, 1.0, 0.5, 1.5]),
              "cold_threshold": 0.2, "hard_delete_after_days": 180,
              "tier_lambda": {c: rng.choice([None, None, 0.01, 0.05, 0.4]) for c in CAMADAS}}
    return {"op": "retencao", "params": params, "tier": rng.choice(CAMADAS), "age_days": rng.choice([0.0, rng.uniform(0, 900), rng.uniform(0, 60)]),
            "access_count": rng.choice([0, 1, rng.randint(0, 600)]), "days_since_access": rng.choice([None, 0.0, rng.uniform(0, 500)]),
            "salience": rng.choice([None, 0.25, 0.5, 1.0, 2.0, rng.uniform(0.25, 2.0)]), "distinct_actors": rng.choice([0, 1, 2, rng.randint(0, 80)]),
            "breadth_weight": rng.choice([0.0, 0.0, 0.3, 1.0, -1.0, rng.uniform(0, 2)])}


def caso_fria(rng: random.Random) -> dict:
    """Uma nota diante da varredura: camada, pin (campo e frontmatter), idade na borda do limiar, nota do futuro."""
    params = caso_retencao(rng)["params"]
    params["cold_threshold"] = rng.choice([0.2, 0.2, 0.2, 0.0, 0.5, 1.0, 1.5, 2.0])
    agora = rng.randint(1_700_000_000_000_000, 1_800_000_000_000_000)
    dias = rng.choice([0, 0.5, 5, 30, 80.4, 80.5, 90, 120, 400, rng.uniform(0, 700), rng.uniform(78, 83), -rng.uniform(0, 40)])
    atualizada = agora - int(dias * 86_400_000_000)
    ultimo = rng.choice([None, None, agora, agora - rng.randint(0, 90 * 86_400_000_000), agora + rng.randint(0, 5 * 86_400_000_000)])
    fm = rng.choice([{}, {}, {"pinned": True}, {"pinned": False}, {"pinned": "true"}, {"pinned": 1}, {"pinned": None}, {"x": 1}, [], "nao", None])
    no_limiar = rng.random() < 0.06
    if no_limiar:
        # retencao exatamente igual ao limiar: nota de hoje, nunca lida, saliencia 1.0
        params["salience_default"] = 1.0
        params["cold_threshold"] = 1.0
        atualizada, ultimo, fm = agora, None, {}
    caso = {"op": "fria", "params": params, "tier": rng.choice(["episodic", "episodic", "episodic"] + CAMADAS), "pinned": rng.random() < 0.15,
            "updated_us": atualizada, "access_count": rng.choice([0, 0, 1, 3, rng.randint(0, 400)]), "last_access_us": ultimo,
            "frontmatter_json": json.dumps(fm) if rng.random() < 0.96 else rng.choice(["nao e json", "", "{\"pinned\": true", "{\"pinned\": true} lixo"]),
            "salience": rng.choice([None, None, 0.25, 0.5, 2.0, rng.uniform(0.25, 2.0)]), "compacted_us": rng.choice([None, None, None, agora - 1]),
            "distinct_actors": rng.choice([0, 1, 2, rng.randint(0, 30)]), "breadth_weight": rng.choice([0.0, 0.0, 0.3, 1.0, -1.0]), "now_us": agora}
    if no_limiar:
        caso.update({"tier": "episodic", "pinned": False, "access_count": 0, "salience": None, "frontmatter_json": "{}", "distinct_actors": 0,
                     "breadth_weight": 0.0, "compacted_us": None})
    return caso


MARCADORES_SESSAO = ["last time", "last session", "yesterday", "what did we", "when we", "previously", "última sessão", "ultima sessao",
                     "sessão anterior", "onde paramos ontem", "decisão anterior", "上次", "之前", "的会话", "会话里", "历史会话", "我们当时"]
RUIDO_SESSAO = ["unknown snowfall", "known issue", "user_sessions 异常会话", "sessão", "antes", "ontem", "git commit", "the session", "lark-cli 1011",
                "O que FIZEMOS", "ÚLTIMA SESSÃO", "Previously.", "wHeN wE", "when  we", "when\twe", "when-we", "xwhen we", "when wex", "İstanbul last time"]
VIZINHOS_EXOTICOS = ["", " ", "\u2166", "\u093f", "\u0301", "é", "ß", "\u00b2", "\u0663", "\u200b", "\u3007", "\u02b0", "\u1d2c", "\U00010140", "_", "-"]


def caso_sessao(rng: random.Random) -> dict:
    partes = [rng.choice(RUIDO_SESSAO) for _ in range(rng.randint(0, 2))]
    if rng.random() < 0.7:
        m = rng.choice(MARCADORES_SESSAO)
        if rng.random() < 0.5:
            m = rng.choice([m, m.upper(), m.title(), sujar(rng, m)])
        partes.insert(rng.randint(0, len(partes)), rng.choice(VIZINHOS_EXOTICOS) + m + rng.choice(VIZINHOS_EXOTICOS))
    return {"op": "sessao", "query": rng.choice([" ", "", "\n", ", "]).join(partes)}


def caso_salience(rng: random.Random) -> dict:
    return {"op": "salience", "params": caso_retencao(rng)["params"], "current": rng.choice([None, 0.25, 0.5, 1.0, 1.75, 2.0, 3.0, -1.0]),
            "kind": rng.choice(["helpful", "not_helpful", "stale", "wrong"])}


def caso_niveis_borda(rng: random.Random) -> dict:
    """Uma nota cujo corpo passa do L1 por `d` bytes, ao lado de uma que ainda espera o seu L1: a folga de 128 decide."""
    d = rng.choice([126, 127, 128, 129, 130])
    espera = {"privileged": False, "title_only": 20, "tiers": [100, 900, 1000]}
    curta = {"privileged": False, "title_only": 20, "tiers": [100, 100, 100 + d]}
    paginas = [espera, curta] if rng.random() < 0.5 else [curta, espera]
    sala = rng.randint(130, 700)
    return {"op": "niveis", "pages": paginas,
            "budget": {"prefix": 100, "content_ceiling": 300 + sala, "recent_full": 0, "recent_first": 0},
            "omitted_base": 40, "listed": 30, "count_only": rng.randint(0, 100)}


def caso_niveis(rng: random.Random) -> dict:
    if rng.random() < 0.2:
        return caso_niveis_borda(rng)
    paginas = []
    for _ in range(rng.randint(0, 14)):
        if rng.random() < 0.15:
            tiers = None
        else:
            l0 = rng.randint(20, 400)
            l1 = l0 + rng.choice([0, 0, rng.randint(1, 600)])
            l2 = l1 + rng.choice([0, rng.randint(0, 200), rng.randint(0, 6000)])
            tiers = [l0, l1, l2]
        paginas.append({"privileged": rng.random() < 0.3, "title_only": rng.randint(5, 60), "tiers": tiers})
    teto = rng.choice([rng.randint(0, 800), rng.randint(500, 6000), rng.randint(2000, 20000)])
    return {"op": "niveis", "pages": paginas,
            "budget": {"prefix": rng.randint(0, 400), "content_ceiling": teto, "recent_full": rng.choice([0, rng.randint(0, 900)]),
                       "recent_first": rng.randint(0, 200)},
            "omitted_base": rng.randint(0, 80), "listed": rng.randint(0, 60), "count_only": rng.randint(0, 100)}


SEGMENTOS = ["repo", "api", "src", "Repo", "repo-outro", "repositorio", "ação", "a b", "x%y", "a_b", ".", "..", ""]
UNIDADES = ["C:", "c:", "D:", "//srv", "//SRV", "/", ""]


def caminho(rng: random.Random) -> str:
    base = rng.choice(UNIDADES)
    partes = [rng.choice(SEGMENTOS) for _ in range(rng.randint(0, 4))]
    sep = rng.choice(["/", "/", "\\"])
    p = base + sep + sep.join(partes) if base not in ("", "/") else (base + sep.join(partes) if base == "/" else sep.join(partes))
    return p + rng.choice(["", "", "/", "//", "\\", "/\\"])


def caso_escolher(rng: random.Random) -> dict:
    ids = set()
    handoffs = []
    for _ in range(rng.randint(0, 6)):
        hid = "".join(rng.choice("0123456789abcdef") for _ in range(32))
        if hid in ids:
            continue
        ids.add(hid)
        handoffs.append({"id": hid, "manual": rng.random() < 0.3, "criado": rng.choice([1000, 2000, 3000, rng.randint(0, 5000)]),
                         "cwd": rng.choice([None, caminho(rng), caminho(rng)]), "dono": rng.choice([None, None, "u:a", "u:b"])})
    dono = rng.choice([{"kind": "any"}, {"kind": "unattributed"}, {"kind": "user", "user": "u:a"}])
    return {"op": "escolher", "handoffs": handoffs, "filtro": rng.choice([None, caminho(rng)]), "dono": dono}


def sortear(grupo: str, rng: random.Random) -> dict:
    if grupo == "retencao":
        return rng.choice([caso_retencao, caso_retencao, caso_salience, lambda r: {"op": "lambda", "dias": r.choice([1.0, 35.0, 180.0, r.uniform(0.1, 400)])}])(rng)
    if grupo == "fria":
        return caso_fria(rng)
    if grupo == "sessao":
        return caso_sessao(rng)
    if grupo == "fatos":
        return {"op": "tokens", "body": corpo_de_fatos(rng)}
    if grupo == "residuo":
        return {"op": "residuo", "body": corpo_de_residuo(rng), "max": rng.choice([0, 1, 3, 8, 16, 64])}
    if grupo == "compactar":
        return {"op": "compactar", "frontmatter": frontmatter(rng), "body": rng.choice([corpo_de_nota(rng), corpo_de_fatos(rng)])}
    if grupo == "trecho":
        r = rng.random()
        if r < 0.15:
            return {"op": "meta", "line": rng.choice(METADADOS + FRASES[:3] + [sujar(rng, rng.choice(METADADOS))])}
        if r < 0.25:
            return {"op": "prosa", "body": corpo_de_nota(rng)}
        if r < 0.35:
            return {"op": "truncar", "input": rng.choice(FRASES + PROSA + ["", "é" * 40, "\U0001F600" * 30]), "max": rng.choice([0, 1, 2, 3, 4, 5, 7, 16, 100, 256, 500])}
        return {"op": "trecho", "frontmatter": frontmatter(rng), "body": corpo_de_nota(rng)}
    if grupo == "niveis":
        return caso_niveis(rng)
    if grupo == "autoridade":
        r = rng.random()
        if r < 0.1:
            return {"op": "limite", "limit": rng.choice([0, 1, 5, 10, 100, 1000, rng.randint(0, 5000)])}
        if r < 0.2:
            return {"op": "rank", "rank": rng.choice([0.0, -0.5, -3.2, 0.7, 12.0, rng.uniform(-9, 9)]), "mult": rng.choice([0.55, 1.0, 1.5, rng.uniform(0.55, 1.5)])}
        fm = frontmatter(rng)
        return {"op": "autoridade", "path": rng.choice(["a.md", "_lint/x.md", "investigations/y.md", "sessions/z.md"]),
                "kind": rng.choice(["rule", "decision", "procedure", "gotcha", "preference", "concept", "slot", "session", "outro", ""]),
                "tier": rng.choice(CAMADAS + ["x"]), "pinned": rng.random() < 0.3,
                "frontmatter": json.dumps(fm if fm is not None else {}) if rng.random() < 0.95 else rng.choice(["nao e json", "[]", "null"]),
                "bonus": rng.choice([0.25, 0.0, 0.5])}
    if grupo == "cwd":
        r = rng.random()
        if r < 0.3:
            return {"op": "cwd_normalizar", "p": caminho(rng)}
        if r < 0.45:
            return {"op": "cwd_dentro", "a": caminho(rng), "d": caminho(rng)}
        if r < 0.6:
            a = caminho(rng)
            return {"op": "cwd_dentro", "a": a, "d": a + rng.choice(["/api", "-outro", "sitorio", "x", "/", "//api", "\\api", "", "/ação", "%", "/.."])}
        if r < 0.75:
            return {"op": "casa", "handoff_cwd": rng.choice([None, caminho(rng)]), "filtro": rng.choice([None, caminho(rng)])}
        return {"op": "chave", "manual": rng.random() < 0.5, "criado": rng.randint(0, 9999), "cwd": rng.choice([None, caminho(rng)]),
                "id": "".join(rng.choice("0123456789abcdef") for _ in range(32))}
    if grupo == "escolher":
        return caso_escolher(rng)
    raise ValueError(grupo)


GRUPOS = ["retencao", "fria", "sessao", "fatos", "residuo", "compactar", "trecho", "niveis", "autoridade", "cwd", "escolher"]


# ── o porte, chamado como o oraculo e chamado ───────────────────────────────

def _params(d: dict) -> _ret.Parametros:
    return _ret.Parametros(lamb=d["lambda"], sigma=d["sigma"], mu=d["mu"], saliencia_padrao=d["salience_default"],
                           limiar_frio=d["cold_threshold"], apagar_apos_dias=d["hard_delete_after_days"],
                           lambda_por_camada={k: v for k, v in d["tier_lambda"].items() if v is not None})


def _fm_de_json(texto: str):
    """O frontmatter como o oraculo o le: JSON estrito, e o que nao for JSON conta como ausente."""
    def recusa(_nome):
        raise ValueError("constante nao JSON")
    try:
        return json.loads(texto, parse_constant=recusa)
    except ValueError:
        return None


def porte(c: dict):
    op = c["op"]
    if op == "sessao":
        return {"valor": _aut.eh_pergunta_de_sessao(c["query"])}
    if op == "fria":
        n = _var.Nota("x.md", c["tier"], c["updated_us"], c["pinned"], c["access_count"], c["last_access_us"], _fm_de_json(c["frontmatter_json"]),
                      None, c["salience"], c["compacted_us"], c["distinct_actors"])
        f = _var.entrada_fria(n, _params(c["params"]), c["now_us"], c["breadth_weight"])
        if f is None:
            return {"fria": False}
        return {"fria": True, "retention": f.retencao, "age_days": f.idade_dias, "access_count": f.acessos, "compacted": f.compactada}
    if op == "retencao":
        return {"valor": _ret.pontuacao(_params(c["params"]), c["tier"], c["age_days"], c["access_count"], c["days_since_access"], c["salience"],
                                       c["distinct_actors"], c["breadth_weight"])}
    if op == "salience":
        return {"valor": _ret.saliencia_depois_do_voto(_params(c["params"]), c["current"], c["kind"])}
    if op == "lambda":
        return {"valor": _ret.lambda_da_meia_vida(c["dias"])}
    if op == "tokens":
        return {"valor": _fatos.minerar_fatos(c["body"])}
    if op == "residuo":
        return {"valor": _fatos.residuo(c["body"], c["max"])}
    if op == "compactar":
        fm, corpo = _compactacao.compactar(c["frontmatter"], c["body"], rodape=_compactacao.RODAPE_AI_MEMORY)
        return {"frontmatter": fm, "body": corpo}
    if op == "trecho":
        t = _tre.trecho_da_nota(c["frontmatter"], c["body"])
        return {"l0": t.l0, "l1": t.l1}
    if op == "prosa":
        return {"valor": _tre.prosa_de_abertura(c["body"])}
    if op == "meta":
        return {"valor": _tre.eh_campo_de_metadado(c["line"])}
    if op == "truncar":
        return {"valor": _tb.truncar_utf8(c["input"], c["max"])}
    if op == "niveis":
        notas = [_niv.CustoDaNota(p["privileged"], p["title_only"], tuple(p["tiers"]) if p["tiers"] is not None else None) for p in c["pages"]]
        b = c["budget"]
        n = len(notas)
        plano = _niv.atribuir_niveis(notas, _niv.Orcamento(b["prefix"], b["content_ceiling"], b["recent_full"], b["recent_first"]),
                                     lambda de: c["omitted_base"] + c["listed"] * (n - de), lambda _n: c["count_only"])
        nomes = {_niv.Nivel.OMITIDA: "omitted", _niv.Nivel.SO_TITULO: "title_only", _niv.Nivel.L0: "l0", _niv.Nivel.L1: "l1", _niv.Nivel.L2: "l2"}
        return {"tiers": [nomes[x] for x in plano.niveis], "omitted_from": plano.omitidas_a_partir, "recent_reserve": plano.reserva_de_recentes}
    if op == "autoridade":
        try:
            fm = json.loads(c["frontmatter"])
        except ValueError:
            fm = None
        a = _aut.autoridade_da_nota(c["path"], c["kind"], c["tier"], c["pinned"], fm)
        return {"factor": a.fator, "session_penalty": a.penalidade_de_sessao, "factor_recall": a.fator_para(True, c["bonus"]),
                "factor_normal": a.fator_para(False, c["bonus"])}
    if op == "rank":
        return {"valor": _aut.multiplicar_posto(c["rank"], c["mult"])}
    if op == "limite":
        return {"valor": _aut.limite_de_candidatos(c["limit"])}
    if op == "cwd_normalizar":
        return {"valor": _cam.normalizar_cwd(c["p"])}
    if op == "cwd_dentro":
        return {"valor": _cam.cwd_dentro(c["a"], c["d"])}
    if op == "casa":
        return {"valor": _cam.casa_com_cwd(c["handoff_cwd"], c["filtro"])}
    if op == "chave":
        k = _cam.chave_de_escolha(c["manual"], c["criado"], c["cwd"], bytes.fromhex(c["id"]))
        return {"valor": [k[0], k[1], k[2], k[3].hex()]}
    if op == "escolher":
        d = c["dono"]
        filtro = None if d["kind"] == "any" else ("sem_dono",) if d["kind"] == "unattributed" else ("usuario", d["user"])
        cand = [_cam.Candidata(bytes.fromhex(h["id"]), h["manual"], h["criado"], h["cwd"], h["dono"]) for h in c["handoffs"]]
        e = _cam.escolher(cand, c["filtro"], filtro)
        return {"valor": None if e is None else e.id.hex()}
    raise ValueError(op)


# ── comparar ────────────────────────────────────────────────────────────────

def igual(a, b) -> bool:
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(igual(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(igual(x, y) for x, y in zip(a, b))
    return a == b and type(a) is type(b)


def rodar_oraculo(casos: list[dict]) -> list[dict]:
    entrada = "\n".join(json.dumps(c, ensure_ascii=False) for c in casos) + "\n"
    p = subprocess.run([str(ORACULO)], input=entrada.encode("utf-8"), capture_output=True)
    if p.returncode != 0:
        sys.exit(f"o oraculo falhou ({p.returncode}): {p.stderr.decode('utf-8', 'replace')[-800:]}")
    return [json.loads(x) for x in p.stdout.decode("utf-8").split("\n") if x]


def conferir(grupos: list[str], n: int, semente: int, verboso: bool) -> dict[str, tuple[int, int]]:
    rng = random.Random(semente)
    resultado = {}
    for g in grupos:
        casos = [sortear(g, rng) for _ in range(n)]
        esperado = rodar_oraculo(casos)
        diferentes = []
        for c, e in zip(casos, esperado):
            try:
                o = porte(c)
            except Exception as x:  # noqa: BLE001 - o porte levantar e uma diferenca
                o = {"erro_do_porte": f"{type(x).__name__}: {x}"}
            if not igual(o, e):
                diferentes.append((c, e, o))
        resultado[g] = (n - len(diferentes), n)
        if diferentes and verboso:
            for c, e, o in diferentes[:3]:
                print(f"  [{g}] caso: {json.dumps(c, ensure_ascii=False)[:400]}\n     esperado: {json.dumps(e, ensure_ascii=False)[:300]}\n     porte:    {json.dumps(o, ensure_ascii=False, default=str)[:300]}")
    return resultado


# ── mutacoes ────────────────────────────────────────────────────────────────

def _sub(modulo, nome, nova):
    antiga = getattr(modulo, nome)
    setattr(modulo, nome, nova)
    return lambda: setattr(modulo, nome, antiga)


def _mut_retencao_sigma():
    orig = _ret.pontuacao
    return _sub(_ret, "pontuacao", lambda p, *a, **k: orig(_ret.Parametros(**{**p.__dict__, "sigma": p.sigma * 1.01}), *a, **k))


def _mut_saliencia_sem_piso():
    return _sub(_ret, "saliencia_depois_do_voto", lambda p, atual, voto: (p.saliencia_padrao if atual is None else atual) - 0.25 if voto == "stale" else 1.0)


def _mut_fatos_sem_minimo():
    return _sub(_fatos, "MIN_TOKEN_BYTES", 1)


def _mut_fatos_ordem():
    return _sub(_fatos, "PADROES", list(reversed(_fatos.PADROES)))


def _mut_fatos_sem_limite():
    return _sub(_fatos, "MAX_TOKENS", 5)


def _mut_trecho_ignora_metadado():
    return _sub(_tre, "eh_campo_de_metadado", lambda linha: False)


def _mut_trecho_l0_do_resumo():
    return _sub(_tre, "BRIEF_L0_MAX_BYTES", 255)


def _mut_niveis_folga():
    return _sub(_niv, "FOLGA_CORPO_CURTO", 127)


def _mut_niveis_sem_privilegio():
    orig = _niv.CustoDaNota
    return _sub(_niv, "CustoDaNota", lambda priv, t, n: orig(False, t, n))


def _mut_autoridade_teto():
    return _sub(_aut, "TETO", 1.4)


def _mut_autoridade_historical():
    orig = _aut.etiquetas_de
    return _sub(_aut, "etiquetas_de", lambda fm: [e for e in orig(fm) if e != "historical"])


def _mut_autoridade_fixada():
    orig = _aut.autoridade_da_nota
    return _sub(_aut, "autoridade_da_nota", lambda c, t, ca, fix, fm=None: orig(c, t, ca, False, fm))


def _mut_fria_camada_qualquer():
    return _sub(_var, "e_decaivel", lambda n: not n.fixada and not (isinstance(n.frontmatter, dict) and n.frontmatter.get("pinned") is True))


def _mut_fria_ignora_pin_do_frontmatter():
    return _sub(_var, "e_decaivel", lambda n: n.camada == "episodic" and not n.fixada)


def _mut_fria_pin_verdadeiro_qualquer():
    return _sub(_var, "e_decaivel", lambda n: n.camada == "episodic" and not n.fixada and not (isinstance(n.frontmatter, dict) and n.frontmatter.get("pinned")))


def _mut_fria_idade_negativa():
    return _sub(_var, "dias_decorridos", lambda agora, antes: (agora - antes) / _var.US_POR_DIA)


def _mut_fria_limiar_inclusivo():
    orig = _var.entrada_fria
    return _sub(_var, "entrada_fria", lambda n, p, agora, peso=0.0: orig(n, _ret.Parametros(**{**p.__dict__, "limiar_frio": p.limiar_frio * (1 + 1e-9)}), agora, peso))


def _mut_niveis_sem_saturacao():
    return _sub(_niv, "_sub_sat", lambda a, b: a - b)


def _mut_sessao_sem_fronteira():
    return _sub(_aut, "eh_pergunta_de_sessao", lambda q: any(m in q.lower() for m in _aut._SESSAO_ZH + _aut._SESSAO_EN + _aut._SESSAO_PT))


def _mut_sessao_so_isalpha():
    return _sub(_aut, "eh_alfabetico", lambda c: c.isalpha())


def _mut_cwd_sem_fronteira():
    return _sub(_cam, "cwd_dentro", lambda a, d: _cam.normalizar_cwd(d).startswith(_cam.normalizar_cwd(a)))


def _mut_cwd_sem_minuscula():
    return _sub(_cam, "normalizar_cwd", lambda p: p.replace("\\", "/").rstrip("/") or "/")


def _mut_escolha_sem_manual():
    return _sub(_cam, "chave_de_escolha", lambda manual, criada, cwd, i: (False, criada, 0, bytes(i)))


def _mut_linhas_splitlines():
    return _sub(_tre, "linhas", lambda t: t.splitlines())


def _mut_truncar_por_caractere():
    return _sub(_tb, "truncar_utf8", lambda t, m: t if len(t) <= m else t[: max(m - 1, 0)] + "…")


def _mut_compactar_sem_rodape():
    orig = _compactacao.compactar
    return _sub(_compactacao, "compactar", lambda fm, corpo, rodape="": orig(fm, corpo, rodape=""))


MUTACOES = {
    "retencao:sigma": ("retencao", _mut_retencao_sigma),
    "retencao:saliencia_sem_piso": ("retencao", _mut_saliencia_sem_piso),
    "varredura:camada_qualquer": ("fria", _mut_fria_camada_qualquer),
    "varredura:ignora_pin_do_frontmatter": ("fria", _mut_fria_ignora_pin_do_frontmatter),
    "varredura:pin_verdadeiro_qualquer": ("fria", _mut_fria_pin_verdadeiro_qualquer),
    "varredura:idade_negativa": ("fria", _mut_fria_idade_negativa),
    "varredura:limiar_deslocado": ("fria", _mut_fria_limiar_inclusivo),
    "fatos:sem_tamanho_minimo": ("fatos", _mut_fatos_sem_minimo),
    "fatos:ordem_das_classes": ("fatos", _mut_fatos_ordem),
    "fatos:limite_de_quantidade": ("fatos", _mut_fatos_sem_limite),
    "trecho:ignora_metadado": ("trecho", _mut_trecho_ignora_metadado),
    "trecho:limite_do_l0": ("trecho", _mut_trecho_l0_do_resumo),
    "niveis:folga_do_corpo_curto": ("niveis", _mut_niveis_folga),
    "niveis:sem_privilegio": ("niveis", _mut_niveis_sem_privilegio),
    "autoridade:teto": ("autoridade", _mut_autoridade_teto),
    "autoridade:ignora_historical": ("autoridade", _mut_autoridade_historical),
    "autoridade:ignora_fixada": ("autoridade", _mut_autoridade_fixada),
    "niveis:sem_saturacao": ("niveis", _mut_niveis_sem_saturacao),
    "sessao:sem_fronteira_de_palavra": ("sessao", _mut_sessao_sem_fronteira),
    "sessao:alfabetico_so_isalpha": ("sessao", _mut_sessao_so_isalpha),
    "cwd:sem_fronteira_de_componente": ("cwd", _mut_cwd_sem_fronteira),
    "cwd:sem_minuscula_de_unidade": ("cwd", _mut_cwd_sem_minuscula),
    "escolha:manual_nao_vence": ("escolher", _mut_escolha_sem_manual),
    "texto:linhas_por_splitlines": ("trecho", _mut_linhas_splitlines),
    "texto:truncar_por_caractere": ("trecho", _mut_truncar_por_caractere),
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-n", type=int, default=2000, help="casos por grupo")
    ap.add_argument("--so", help=f"grupos separados por virgula: {','.join(GRUPOS)}")
    ap.add_argument("--semente", type=int, default=20261017)
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--mutacoes", action="store_true", help="injeta defeitos conhecidos e confere que a paridade os acusa")
    args = ap.parse_args()
    if not ORACULO.exists():
        sys.exit(f"falta o oraculo: {ORACULO}\n  cd scripts/oraculo_ai_memory && cargo +1.95 build --release")
    grupos = args.so.split(",") if args.so else GRUPOS

    if not args.mutacoes:
        r = conferir(grupos, args.n, args.semente, args.v)
        total_ok = sum(a for a, _ in r.values())
        total = sum(b for _, b in r.values())
        for g, (a, b) in r.items():
            print(f"{g:<11} {a:>6} de {b:<6} {'ok' if a == b else 'DIFERENTE'}")
        print(f"\n{total_ok} de {total} casos iguais ao original")
        return 0 if total_ok == total else 1

    falhou = 0
    for nome, (grupo, injetar) in MUTACOES.items():
        if args.so and grupo not in grupos:
            continue
        desfazer = injetar()
        try:
            a, b = conferir([grupo], max(args.n // 2, 400), args.semente, False)[grupo]
        finally:
            desfazer()
        pego = a < b
        falhou += 0 if pego else 1
        print(f"{'pego' if pego else 'NAO PEGO':<9} {nome:<36} {b - a} de {b} casos diferentes")
    print(f"\n{len(MUTACOES) - falhou if not args.so else '?'} mutacoes pegas, {falhou} nao")
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
