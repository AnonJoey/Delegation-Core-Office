"""Recuperacao automatica do original no proxy (CCR do Headroom, item 6.3.3).

Quando o proxy comprime um resultado de ferramenta com perda, o texto termina com um ponteiro
(`Retrieve more: hash=...`, `Retrieve original: hash=...` ou `<<ccr:...`) e o original fica na
guarda (`compressao.ccr.Guarda`). Antes, so o MCP (`recall_output`) devolvia o original: um agente
sem o MCP via o ponteiro e nao tinha como segui-lo.

Aqui, como no Headroom (`headroom/ccr/tool_injection.py`, `response_handler.py`):
1. se o pedido tem ponteiro cujo hash esta de fato na guarda, o proxy acrescenta uma ferramenta
   de recuperacao (`delegation_core_retrieve`) a lista de ferramentas;
2. se o modelo chama essa ferramenta, o proxy busca o original, devolve o resultado ao provedor
   numa continuacao e entrega ao cliente so a resposta final. O cliente nunca ve a chamada.

Onde este porte difere do original, de proposito:
- Streaming: o original segura a resposta ate o fim (ou ate 10 KB) e so entao decide; se a
  chamada vem depois dos primeiros 10 KB, o texto ja enviado sai de novo. Aqui cada bloco do
  cliente segue na hora; so os blocos da nossa ferramenta ficam retidos, e a continuacao e
  emendada no mesmo fluxo com os indices de bloco renumerados.
- Nenhuma instrucao e escrita no `system`: a descricao da ferramenta ja explica o ponteiro, e o
  `system` fica identico byte a byte (cache de prompt do provedor).
- OpenAI Responses (`/v1/responses`) nao recebe a ferramenta: sem tratar a chamada nesse formato,
  injetar so deixaria o cliente com uma chamada de ferramenta que ele nao conhece.

Iguais ao original: ate 3 rodadas; chamada mista (a nossa junto com uma ferramenta do cliente)
volta ao cliente sem mudanca, porque nao da para montar a continuacao sem o resultado da outra;
falha na continuacao devolve o que havia.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, AsyncIterator, Awaitable, Callable

NOME = "delegation_core_retrieve"
MAX_RODADAS = 3
_DESCRICAO = ("Retrieve the original, uncompressed content of a tool output that the proxy compressed to "
              "save tokens. Use it when the compressed result is not enough. The hash is in markers like "
              "'Retrieve more: hash=abc123', 'Retrieve original: hash=abc123' or '<<ccr:abc123'.")
_PROPRIEDADES = {"hash": {"type": "string",
                          "description": "The hash from the marker, e.g. 'abc123' from 'hash=abc123'."}}

#: Os tres ponteiros que os compressores do delegation-core escrevem (diff, busca, log: 24 hex;
#: SmartCrusher: `<<ccr:` com 12; ciclo do Read: "Retrieve original").
MARCADORES = (
    re.compile(r"Retrieve more: hash=([a-f0-9]{12,24})"),
    re.compile(r"Retrieve original: hash=([a-f0-9]{12,24})"),
    re.compile(r"<<ccr:([a-f0-9]{12,24})\b"),
)

#: Formatos tratados: o caminho do pedido e o nome interno.
FORMATOS = {"/v1/messages": "anthropic", "/v1/chat/completions": "openai_chat"}


def _guarda():
    from ..compressao.ccr import Guarda
    return Guarda()


def buscar_original(h: str) -> str | None:
    return _guarda().get(h)


# ── pedido ─────────────────────────────────────────────────────────────────

def _textos(valor) -> list[str]:
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    return []


def hashes(corpo: dict, existe: Callable[[str], bool] | None = None) -> list[str]:
    """Os hashes dos ponteiros nas mensagens, so os que a guarda tem (o original pede o mesmo:
    marcador com a mesma forma pode vir de outra ferramenta, e anunciar hash que nao e nosso faz
    o modelo pedir uma recuperacao que vai falhar)."""
    existe = existe or (lambda h: buscar_original(h) is not None)
    vistos: list[str] = []
    for texto in _textos(corpo.get("messages")):
        for padrao in MARCADORES:
            for h in padrao.findall(texto):
                if h not in vistos:
                    vistos.append(h)
    return [h for h in vistos if _seguro(existe, h)]


def _seguro(existe, h) -> bool:
    try:
        return bool(existe(h))
    except Exception:  # noqa: BLE001 - guarda indisponivel: nao anuncia (mesmo caminho do original)
        return False


def definicao(formato: str) -> dict:
    esquema = {"type": "object", "properties": _PROPRIEDADES, "required": ["hash"]}
    if formato == "anthropic":
        return {"name": NOME, "description": _DESCRICAO, "input_schema": esquema}
    return {"type": "function", "function": {"name": NOME, "description": _DESCRICAO, "parameters": esquema}}


def _nome_da_ferramenta(t: dict) -> str | None:
    return t.get("name") or (t.get("function") or {}).get("name")


def injetar(corpo: dict, formato: str) -> dict:
    """O corpo com a ferramenta de recuperacao no fim da lista (o fim mexe menos no cache)."""
    ferramentas = list(corpo.get("tools") or [])
    if any(isinstance(t, dict) and _nome_da_ferramenta(t) == NOME for t in ferramentas):
        return corpo
    return dict(corpo, tools=ferramentas + [definicao(formato)])


def conteudo_do_resultado(h: str, buscar: Callable[[str], str | None] = buscar_original) -> str:
    """O texto que volta ao modelo, no formato do original (JSON com o hash e o conteudo)."""
    try:
        texto = buscar(h) if h else None
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"Retrieval failed: {type(e).__name__}", "hash": h}, indent=2)
    if texto is None:
        return json.dumps({"error": "No saved original for this hash.", "hash": h}, indent=2)
    return json.dumps({"hash": h, "original_content": texto}, indent=2, ensure_ascii=False)


# ── resposta inteira (sem streaming) ───────────────────────────────────────

def chamadas(resposta: dict, formato: str) -> tuple[list[tuple[str, str]], int]:
    """([(id, hash)] das chamadas a nossa ferramenta, quantas chamadas a outras ferramentas)."""
    nossas, outras = [], 0
    if formato == "anthropic":
        for b in resposta.get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                if b.get("name") == NOME:
                    entrada = b.get("input") if isinstance(b.get("input"), dict) else {}
                    nossas.append((b.get("id", ""), str(entrada.get("hash", ""))))
                else:
                    outras += 1
        return nossas, outras
    escolhas = resposta.get("choices")
    msg = (escolhas[0] or {}).get("message", {}) if isinstance(escolhas, list) and escolhas else {}
    for c in (msg or {}).get("tool_calls") or []:
        f = (c or {}).get("function") or {}
        if f.get("name") == NOME:
            try:
                args = json.loads(f.get("arguments") or "{}")
            except ValueError:
                args = {}
            nossas.append((c.get("id", ""), str((args or {}).get("hash", ""))))
        else:
            outras += 1
    return nossas, outras


def _mensagem_do_assistente(resposta: dict, formato: str) -> dict:
    if formato == "anthropic":
        return {"role": "assistant", "content": resposta.get("content", [])}
    msg = resposta["choices"][0].get("message", {})
    return {"role": "assistant", "content": msg.get("content"), "tool_calls": msg.get("tool_calls")}


def _resultados(formato: str, pares: list[tuple[str, str]]) -> list[dict]:
    if formato == "anthropic":
        return [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "content": c} for i, c in pares]}]
    return [{"role": "tool", "tool_call_id": i, "content": c} for i, c in pares]


def continuacao(corpo: dict, assistente: dict, formato: str, nossas: list[tuple[str, str]],
                buscar: Callable[[str], str | None] = buscar_original) -> dict:
    pares = [(i, conteudo_do_resultado(h, buscar)) for i, h in nossas]
    mensagens = list(corpo.get("messages") or []) + [assistente] + _resultados(formato, pares)
    return dict(corpo, messages=mensagens)


Enviar = Callable[[dict], Awaitable[dict | None]]


async def resolver(resposta: dict, corpo: dict, formato: str, enviar: Enviar,
                   buscar: Callable[[str], str | None] = buscar_original) -> tuple[dict, int]:
    """(resposta final, rodadas feitas). `enviar(corpo)` devolve a resposta JSON da continuacao,
    ou None se ela falhou: ai volta a ultima resposta que havia, como no original."""
    atual, rodadas = resposta, 0
    while rodadas < MAX_RODADAS:
        nossas, outras = chamadas(atual, formato)
        if not nossas or outras:
            break
        rodadas += 1
        corpo = continuacao(corpo, _mensagem_do_assistente(atual, formato), formato, nossas, buscar)
        nova = await enviar(corpo)
        if not isinstance(nova, dict):
            break
        atual = nova
    return atual, rodadas


# ── streaming ──────────────────────────────────────────────────────────────

def _quadros(buf: bytearray) -> list[bytes]:
    """Tira de `buf` os quadros SSE completos (terminados em linha em branco)."""
    saida = []
    while True:
        m = re.search(rb"\r?\n\r?\n", buf)
        if not m:
            return saida
        saida.append(bytes(buf[:m.end()]))
        del buf[:m.end()]


def _dados(quadro: bytes) -> tuple[str | None, Any]:
    """(nome do evento, payload JSON ou o texto cru do data) de um quadro SSE."""
    evento, linhas = None, []
    for linha in quadro.decode("utf-8", "replace").splitlines():
        if linha.startswith("event:"):
            evento = linha[6:].strip()
        elif linha.startswith("data:"):
            linhas.append(linha[5:].lstrip(" "))
    texto = "\n".join(linhas)
    if not linhas:
        return evento, None
    try:
        return evento, json.loads(texto)
    except ValueError:
        return evento, texto


def _quadro_anthropic(dados: dict, evento: str | None) -> bytes:
    nome = evento or dados.get("type", "")
    return f"event: {nome}\ndata: {json.dumps(dados, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


#: Blocos que este porte sabe remontar a partir dos eventos para devolver na continuacao. Bloco
#: de outro tipo (servidor, citacoes de busca...) impede a recuperacao: o turno vai ao cliente.
_REMONTAVEIS = {"text", "thinking", "redacted_thinking", "tool_use"}
_ACUMULA = {"text_delta": ("text", "text"), "thinking_delta": ("thinking", "thinking"),
            "input_json_delta": ("partial_json", "_partial_json")}


def remontar_bloco(bloco: dict, deltas: list[dict]) -> dict:
    """O bloco como ele e numa resposta inteira, a partir do inicio e dos deltas (como o
    `AnthropicSSEEnvelope` do original)."""
    b = copy.deepcopy(bloco)
    for d in deltas:
        tipo = d.get("type")
        if tipo in _ACUMULA:
            campo, destino = _ACUMULA[tipo]
            b[destino] = b.get(destino, "") + d.get(campo, "")
        elif tipo == "signature_delta":
            b["signature"] = d.get("signature", "")
        elif tipo == "citations_delta":
            b.setdefault("citations", []).append(d.get("citation"))
    parcial = b.pop("_partial_json", None)
    if parcial is not None:
        try:
            b["input"] = json.loads(parcial) if parcial else {}
        except ValueError:
            b["input"] = {}
    return b


AbrirFluxo = Callable[[dict], Awaitable[tuple[int, AsyncIterator[bytes] | None]]]


async def fluxo_anthropic(fonte: AsyncIterator[bytes], corpo: dict, abrir: AbrirFluxo,
                          buscar: Callable[[str], str | None] = buscar_original,
                          relatorio: dict | None = None) -> AsyncIterator[bytes]:
    """O fluxo SSE da Anthropic para o cliente, com as chamadas a nossa ferramenta resolvidas.

    `abrir(corpo)` faz o pedido da continuacao em streaming e devolve (status, bytes)."""
    rel = relatorio if relatorio is not None else {}
    base, primeiro, rodada = 0, True, 0
    while True:
        estado = {"mapa": {}, "nossos": {}, "blocos": {}, "deltas": {}, "ordem": [], "outras": False,
                  "fim": [], "remontavel": True, "erro": False}
        async for saida in _um_fluxo_anthropic(fonte, base, primeiro, estado):
            yield saida
        nossos = estado["nossos"]
        if not nossos:
            return
        pode = (not estado["outras"] and estado["remontavel"] and not estado["erro"] and rodada < MAX_RODADAS)
        if pode:
            conteudo = []
            for idx in estado["ordem"]:
                if idx in nossos:
                    conteudo.append(remontar_bloco(nossos[idx]["bloco"], nossos[idx]["deltas"]))
                else:
                    conteudo.append(remontar_bloco(estado["blocos"][idx], estado["deltas"].get(idx, [])))
            pares = [(c["id"], str((c.get("input") or {}).get("hash", ""))) for c in conteudo
                     if c.get("type") == "tool_use" and c.get("name") == NOME]
            novo = continuacao(corpo, {"role": "assistant", "content": conteudo}, "anthropic", pares, buscar)
            status, prox = await abrir(novo)
            if status == 200 and prox is not None:
                corpo, fonte = novo, prox
                base += len(estado["mapa"])
                primeiro, rodada = False, rodada + 1
                rel["rodadas"] = rodada
                continue
            rel["falhou"] = f"continuacao {status}"
        # Recuo: o cliente recebe o que foi retido, renumerado, e decide (igual ao original).
        prox_idx = base + len(estado["mapa"])
        for idx in sorted(nossos):
            for q, dados, evento in nossos[idx]["quadros"]:
                dados = dict(dados, index=prox_idx)
                yield _quadro_anthropic(dados, evento)
            prox_idx += 1
        for q in estado["fim"]:
            yield q
        return


async def _um_fluxo_anthropic(fonte: AsyncIterator[bytes], base: int, primeiro: bool, est: dict):
    buf = bytearray()

    def para_o_cliente(q: bytes, dados: dict, evento, idx) -> bytes:
        novo = est["mapa"][idx]
        if novo == idx:
            return q   # mesmo indice: os bytes do provedor, intactos
        return _quadro_anthropic(dict(dados, index=novo), evento)

    async for pedaco in fonte:
        buf.extend(pedaco)
        for q in _quadros(buf):
            evento, dados = _dados(q)
            tipo = dados.get("type") if isinstance(dados, dict) else evento
            if not isinstance(dados, dict):
                if not est["nossos"]:
                    yield q
                else:
                    est["fim"].append(q)
                continue
            if tipo == "message_start":
                if primeiro:
                    yield q
            elif tipo == "content_block_start":
                idx, bloco = dados.get("index"), dados.get("content_block") or {}
                est["ordem"].append(idx)
                if bloco.get("type") == "tool_use" and bloco.get("name") == NOME:
                    est["nossos"][idx] = {"bloco": bloco, "deltas": [], "quadros": [(q, dados, evento)]}
                    continue
                est["mapa"][idx] = base + len(est["mapa"])
                est["blocos"][idx] = bloco
                if bloco.get("type") == "tool_use":
                    est["outras"] = True
                if bloco.get("type") not in _REMONTAVEIS:
                    est["remontavel"] = False
                yield para_o_cliente(q, dados, evento, idx)
            elif tipo in ("content_block_delta", "content_block_stop"):
                idx = dados.get("index")
                if idx in est["nossos"]:
                    if tipo == "content_block_delta":
                        est["nossos"][idx]["deltas"].append(dados.get("delta") or {})
                    est["nossos"][idx]["quadros"].append((q, dados, evento))
                    continue
                if tipo == "content_block_delta":
                    est["deltas"].setdefault(idx, []).append(dados.get("delta") or {})
                if idx in est["mapa"]:
                    yield para_o_cliente(q, dados, evento, idx)
                else:
                    yield q
            elif tipo in ("message_delta", "message_stop"):
                if est["nossos"]:
                    est["fim"].append(q)
                else:
                    yield q
            else:
                if tipo == "error":
                    est["erro"] = True
                if est["nossos"]:
                    est["fim"].append(q)
                else:
                    yield q
    if buf:
        if est["nossos"]:
            est["fim"].append(bytes(buf))
        else:
            yield bytes(buf)


def _quadro_openai(dados: dict) -> bytes:
    return f"data: {json.dumps(dados, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


async def fluxo_openai_chat(fonte: AsyncIterator[bytes], corpo: dict, abrir: AbrirFluxo,
                            buscar: Callable[[str], str | None] = buscar_original,
                            relatorio: dict | None = None) -> AsyncIterator[bytes]:
    """O fluxo SSE do OpenAI Chat Completions, com as chamadas a nossa ferramenta resolvidas."""
    rel = relatorio if relatorio is not None else {}
    base, rodada = 0, 0
    while True:
        est = {"nossos": {}, "outras": {}, "mapa": {}, "texto": [], "fim": [], "retidos": [], "erro": False}
        async for saida in _um_fluxo_openai(fonte, base, est):
            yield saida
        if not est["nossos"]:
            return
        if not est["outras"] and not est["erro"] and rodada < MAX_RODADAS:
            chamadas_ = [{"id": n["id"], "type": "function", "function": {"name": NOME, "arguments": n["args"]}}
                         for _, n in sorted(est["nossos"].items())]
            pares = []
            for c in chamadas_:
                try:
                    h = str((json.loads(c["function"]["arguments"] or "{}") or {}).get("hash", ""))
                except ValueError:
                    h = ""
                pares.append((c["id"], h))
            texto = "".join(est["texto"])
            assistente = {"role": "assistant", "content": texto or None, "tool_calls": chamadas_}
            novo = continuacao(corpo, assistente, "openai_chat", pares, buscar)
            status, prox = await abrir(novo)
            if status == 200 and prox is not None:
                corpo, fonte = novo, prox
                base += len(est["mapa"])
                rodada += 1
                rel["rodadas"] = rodada
                continue
            rel["falhou"] = f"continuacao {status}"
        prox_idx = base + len(est["mapa"])
        for idx in sorted(est["nossos"]):
            for dados in est["nossos"][idx]["pedacos"]:
                yield _quadro_openai(dados_com_indice(dados, idx, prox_idx))
            prox_idx += 1
        for q in est["fim"]:
            yield q
        return


def dados_com_indice(dados: dict, de: int, para: int) -> dict:
    d = copy.deepcopy(dados)
    for e in d.get("choices") or []:
        for c in (e.get("delta") or {}).get("tool_calls") or []:
            if c.get("index") == de:
                c["index"] = para
    return d


async def _um_fluxo_openai(fonte: AsyncIterator[bytes], base: int, est: dict):
    buf = bytearray()
    async for pedaco in fonte:
        buf.extend(pedaco)
        for q in _quadros(buf):
            _, dados = _dados(q)
            if dados == "[DONE]" or not isinstance(dados, dict):
                (est["fim"].append(q) if est["nossos"] else None)
                if not est["nossos"]:
                    yield q
                continue
            if "error" in dados:
                est["erro"] = True
            escolhas = dados.get("choices") or []
            nossos_aqui, mudou, fim = [], False, False
            for e in escolhas:
                delta = e.get("delta") or {}
                if isinstance(delta.get("content"), str):
                    est["texto"].append(delta["content"])
                manter = []
                for c in delta.get("tool_calls") or []:
                    i = c.get("index")
                    nome = (c.get("function") or {}).get("name")
                    if i not in est["nossos"] and i not in est["outras"]:
                        if nome == NOME:
                            est["nossos"][i] = {"id": c.get("id", ""), "args": "", "pedacos": []}
                        else:
                            est["outras"][i] = True
                            est["mapa"][i] = base + len(est["mapa"])
                    if i in est["nossos"]:
                        est["nossos"][i]["args"] += (c.get("function") or {}).get("arguments") or ""
                        nossos_aqui.append(i)
                        mudou = True
                        continue
                    novo = est["mapa"].get(i, i)
                    if novo != i:
                        c = dict(c, index=novo)
                        mudou = True
                    manter.append(c)
                if "tool_calls" in delta:
                    delta["tool_calls"] = manter
                    if not manter:
                        del delta["tool_calls"]
                if e.get("finish_reason") is not None and est["nossos"]:
                    fim = True
            for i in nossos_aqui:
                pedaco_nosso = copy.deepcopy(_original_do_quadro(q))
                for e in pedaco_nosso.get("choices") or []:
                    d = e.get("delta") or {}
                    d["tool_calls"] = [c for c in d.get("tool_calls") or [] if c.get("index") == i]
                    d.pop("content", None)
                    e.pop("finish_reason", None)
                est["nossos"][i]["pedacos"].append(pedaco_nosso)
            if fim:
                est["fim"].append(_quadro_openai(dados) if mudou else q)
                continue
            vazio = all(not (e.get("delta") or {}) and e.get("finish_reason") is None for e in escolhas)
            if nossos_aqui and vazio and not dados.get("usage"):
                continue   # o pedaco so trazia a nossa chamada
            yield _quadro_openai(dados) if mudou else q
    if buf:
        if est["nossos"]:
            est["fim"].append(bytes(buf))
        else:
            yield bytes(buf)


def _original_do_quadro(q: bytes) -> dict:
    _, dados = _dados(q)
    return dados if isinstance(dados, dict) else {}
