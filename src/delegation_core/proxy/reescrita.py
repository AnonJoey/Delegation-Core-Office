"""Funcoes puras: acham os resultados de ferramenta numa requisicao e os comprimem.

Tres formatos:
- Anthropic Messages (`/v1/messages`): blocos `tool_result` dentro de
  `messages[].content`, com `content` texto ou lista de blocos `text`;
- OpenAI Chat Completions (`/v1/chat/completions`): mensagens `role: tool`;
- OpenAI Responses (`/v1/responses`): itens `function_call_output` em `input`.

So texto com pelo menos `minimo` caracteres e tocado; imagem e o resto da
requisicao (sistema, pedido do usuario, ferramentas, parametros) nao mudam.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

_MEMO: "OrderedDict[str, str]" = OrderedDict()
_MEMO_MAX = 512
_TRAVA = threading.Lock()


@dataclass
class Relatorio:
    formato: str = ""
    blocos: int = 0
    comprimidos: int = 0
    chars_antes: int = 0
    chars_depois: int = 0
    compressores: dict = field(default_factory=dict)
    #: Trechos trocados por ponteiro pelo dedup entre turnos (proxy/dedup.py).
    trechos_dedup: int = 0
    #: Reads obsoletos trocados por marcador (proxy/leitura.py).
    leituras_obsoletas: int = 0
    #: Como comprimir um texto: `(texto) -> resultado do roteador`. None: o roteador direto, nesta
    #: thread. O servidor do proxy passa o pool do daemon, na classe interativa (6.1.3).
    comprimir: object = field(default=None, repr=False, compare=False)


def comprimir_texto(texto: str, minimo: int, rel: Relatorio) -> str:
    """O mesmo texto sempre vira o mesmo resultado: memo por hash, contexto vazio, vies 1.0."""
    rel.blocos += 1
    rel.chars_antes += len(texto)
    if len(texto) < minimo:
        rel.chars_depois += len(texto)
        return texto
    chave = hashlib.sha256(texto.encode("utf-8")).hexdigest()
    with _TRAVA:
        pronto = _MEMO.get(chave)
        if pronto is not None:
            _MEMO.move_to_end(chave)
    if pronto is None:
        if rel.comprimir is not None:
            r = rel.comprimir(texto)
        else:
            from ..compressao.roteador import comprimir
            r = comprimir(texto, "", "auto", 1.0)
        pronto = r["output"]
        rel.compressores[r["compressor"]] = rel.compressores.get(r["compressor"], 0) + 1
        with _TRAVA:
            _MEMO[chave] = pronto
            while len(_MEMO) > _MEMO_MAX:
                _MEMO.popitem(last=False)
    if pronto != texto:
        rel.comprimidos += 1
    rel.chars_depois += len(pronto)
    return pronto


def _conteudo(valor, minimo, rel):
    """`content` de um tool_result ou de uma mensagem tool: texto ou lista de blocos."""
    if isinstance(valor, str):
        return comprimir_texto(valor, minimo, rel)
    if isinstance(valor, list):
        saida = []
        for b in valor:
            if isinstance(b, dict) and b.get("type") in ("text", "input_text", "output_text") \
                    and isinstance(b.get("text"), str):
                b = dict(b, text=comprimir_texto(b["text"], minimo, rel))
            saida.append(b)
        return saida
    return valor


def anthropic(corpo: dict, minimo: int, rel: Relatorio) -> dict:
    rel.formato = "anthropic"
    msgs = corpo.get("messages")
    if not isinstance(msgs, list):
        return corpo
    novas = []
    for m in msgs:
        if isinstance(m, dict) and isinstance(m.get("content"), list):
            blocos = []
            for b in m["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result" and "content" in b:
                    b = dict(b, content=_conteudo(b["content"], minimo, rel))
                blocos.append(b)
            m = dict(m, content=blocos)
        novas.append(m)
    return dict(corpo, messages=novas)


def openai_chat(corpo: dict, minimo: int, rel: Relatorio) -> dict:
    rel.formato = "openai_chat"
    msgs = corpo.get("messages")
    if not isinstance(msgs, list):
        return corpo
    return dict(corpo, messages=[dict(m, content=_conteudo(m["content"], minimo, rel))
                                 if isinstance(m, dict) and m.get("role") == "tool" and "content" in m else m
                                 for m in msgs])


def openai_responses(corpo: dict, minimo: int, rel: Relatorio) -> dict:
    rel.formato = "openai_responses"
    itens = corpo.get("input")
    if not isinstance(itens, list):
        return corpo
    return dict(corpo, input=[dict(i, output=_conteudo(i["output"], minimo, rel))
                              if isinstance(i, dict) and i.get("type") == "function_call_output" and "output" in i else i
                              for i in itens])


ROTAS = {"/v1/messages": anthropic, "/v1/chat/completions": openai_chat, "/v1/responses": openai_responses}


def _dedup(corpo: dict, rel: Relatorio) -> dict:
    """Dedup entre turnos sobre as formas finais; so os formatos com `messages`."""
    from .dedup import dedup_mensagens
    msgs = corpo.get("messages")
    if not isinstance(msgs, list):
        return corpo
    novas, n, chars = dedup_mensagens(msgs)
    if not n:
        return corpo
    rel.trechos_dedup = n
    rel.chars_depois = max(0, rel.chars_depois - chars)
    return dict(corpo, messages=novas)


def _tamanho(msgs: list) -> int:
    """Caracteres dos resultados de ferramenta em texto (Anthropic e OpenAI Chat)."""
    total = 0
    for m in msgs:
        if not isinstance(m, dict):
            continue
        c = m.get("content")
        if m.get("role") == "tool" and isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            total += sum(len(b["content"]) for b in c if isinstance(b, dict) and b.get("type") == "tool_result"
                         and isinstance(b.get("content"), str))
    return total


def _leitura(corpo: dict, rel: Relatorio, superseded: bool) -> dict:
    """Ciclo de vida do Read, ANTES da compressao por bloco (como no Headroom)."""
    from .leitura import aplicar
    msgs = corpo.get("messages")
    if not isinstance(msgs, list):
        return corpo
    r = aplicar(msgs, superseded=superseded)
    if not r.transforms_applied:
        return corpo
    rel.leituras_obsoletas = len(r.transforms_applied)
    # O bloco substituido entra na compressao por bloco ja como marcador: o livro conta o que ele era.
    # (O `bytes_before` do original so e preenchido no caminho OpenAI, entao a diferenca e medida aqui.)
    rel.chars_antes += max(0, _tamanho(msgs) - _tamanho(r.messages))
    return dict(corpo, messages=r.messages)


def reescrever(caminho: str, corpo: dict, minimo: int, dedup: bool = False, leitura: bool = False,
               superseded: bool = False, comprimir=None) -> tuple[dict, Relatorio]:
    rel = Relatorio(comprimir=comprimir)
    f = ROTAS.get(caminho.rstrip("/"))
    if f is None:
        return corpo, rel
    if leitura and caminho.rstrip("/") in ("/v1/messages", "/v1/chat/completions"):
        corpo = _leitura(corpo, rel, superseded)
    novo = f(corpo, minimo, rel)
    if dedup and rel.formato in ("anthropic", "openai_chat"):
        novo = _dedup(novo, rel)
    return novo, rel
