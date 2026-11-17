"""Dedup entre turnos no proxy: o `_cross_turn_dedup_messages` do `ContentRouter` do Headroom.

Um agente de terminal mostra os mesmos bytes de arquivo varias vezes na conversa (`cat foo.py`,
depois `sed -n 75,100p foo.py`, depois `git diff`, depois `cat foo.py` de novo). Nenhum compressor
por bloco ve isso: a redundancia esta ENTRE blocos. Aqui um trecho de um resultado de ferramenta
que ja apareceu igual num resultado anterior vira um ponteiro curto para o original, que continua
na mesma requisicao (`headroom_py/transforms/cross_turn_dedup.py`, copiado do Headroom).

Duas garantias, as do original:
- seguro para o cache do provedor: o bloco k so e comparado com blocos anteriores, entao anexar um
  turno nunca muda os bytes de um turno anterior;
- sem perda: so vira ponteiro o que esta IGUAL num bloco anterior ainda presente, e a primeira
  ocorrencia nunca e reescrita.

Roda DEPOIS da compressao por bloco, sobre as formas finais. Bloco com `cache_control` e resultado
de ferramenta que precisa ficar byte a byte (busca na web, `view`, recuperacao do original) so
servem de referencia, nunca sao reescritos.

Diferencas deliberadas em relacao ao Headroom:
- cobre os resultados de ferramenta do formato Anthropic (`tool_result`, texto ou lista com um bloco
  de texto) e as mensagens `role: tool` do OpenAI Chat; nao cobre o texto `role: user` de agentes
  que leem arquivos por bloco de codigo (`_is_user_read_observation`) nem o OpenAI Responses;
- `recall_output` (a recuperacao do delegation-core) entra na lista de ferramentas protegidas, no
  lugar do `headroom_retrieve`;
- nao ha contagem de mensagens congeladas: a transformacao e determinista e so olha para tras, entao
  o prefixo ja em cache nao muda;
- o desembrulho de chamadas `tool_call` do Hermes nao e portado.
"""

from __future__ import annotations

from ..compressao.headroom_py.transforms.cross_turn_dedup import DedupBlock, dedup_blocks

#: Resultados que o modelo copia byte a byte ou que sao a propria recuperacao.
PROTEGIDAS = frozenset({"WebSearch", "WebFetch", "web_search", "web_fetch", "headroom_retrieve", "view",
                        "recall_output"})


def _apelidos(nome) -> tuple:
    """Grafias equivalentes de um nome de ferramenta (`mcp__srv__x` e `mcp_srv_x` e `x`)."""
    if not isinstance(nome, str):
        return ()
    apelidos = [nome]
    minusculo = nome.lower()
    if minusculo == "headroom_headroom_retrieve":
        apelidos.append("headroom_retrieve")
    elif minusculo.startswith("mcp__"):
        partes = nome.split("__", 2)
        if len(partes) == 3 and partes[1] and partes[2]:
            apelidos += [f"mcp_{partes[1]}_{partes[2]}", partes[2]]
    elif minusculo.startswith("mcp_"):
        partes = nome.split("_", 2)
        if len(partes) == 3 and partes[1] and partes[2]:
            apelidos += [f"mcp__{partes[1]}__{partes[2]}", partes[2]]
    return tuple(dict.fromkeys(apelidos))


def protegida(nome) -> bool:
    minusculas = {p.lower() for p in PROTEGIDAS}
    return any(a in PROTEGIDAS or a.lower() in minusculas for a in _apelidos(nome))


def mapa_de_ferramentas(mensagens: list) -> dict:
    """`tool_call_id` -> nome da ferramenta, pelas chamadas das mensagens do assistente."""
    mapa: dict = {}
    for m in mensagens:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if isinstance(tc, dict):
                nome = (tc.get("function") or {}).get("name", "")
                if tc.get("id") and nome:
                    mapa[tc["id"]] = nome
        conteudo = m.get("content", [])
        if isinstance(conteudo, list):
            for b in conteudo:
                if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id") and b.get("name"):
                    mapa[b["id"]] = b["name"]
    return mapa


def dedup_mensagens(mensagens: list) -> tuple[list, int, int]:
    """(mensagens com os trechos repetidos trocados por ponteiros, trechos dobrados, caracteres a menos).
    Nunca levanta: qualquer erro devolve as mensagens como vieram."""
    try:
        locais: list = []
        blocos: list[DedupBlock] = []
        protegidos = {tid for tid, nome in mapa_de_ferramentas(mensagens).items() if protegida(nome)}
        for i, msg in enumerate(mensagens):
            if not isinstance(msg, dict):
                continue
            conteudo = msg.get("content")
            if isinstance(conteudo, list):
                for bi, bloco in enumerate(conteudo):
                    if not isinstance(bloco, dict) or bloco.get("type") != "tool_result":
                        continue
                    tc = bloco.get("content")
                    prot = "cache_control" in bloco or bloco.get("tool_use_id") in protegidos
                    if isinstance(tc, str) and tc:
                        locais.append((i, bi, None))
                        blocos.append(DedupBlock(text=tc, turn=i, protected=prot))
                    elif isinstance(tc, list):
                        # Um unico sub-bloco de texto e a forma comum; varios ou misturados ficam como estao.
                        textos = [(si, sub) for si, sub in enumerate(tc)
                                  if isinstance(sub, dict) and sub.get("type") == "text"
                                  and isinstance(sub.get("text"), str) and sub.get("text")]
                        if len(textos) == 1:
                            si, sub = textos[0]
                            locais.append((i, bi, si))
                            blocos.append(DedupBlock(text=sub["text"], turn=i, protected=prot))
            elif isinstance(conteudo, str) and conteudo and msg.get("role") in ("tool", "function"):
                prot = "cache_control" in msg or msg.get("tool_call_id") in protegidos
                locais.append((i, None, None))
                blocos.append(DedupBlock(text=conteudo, turn=i, protected=prot))

        if len(blocos) < 2:
            return mensagens, 0, 0
        dobrados, stats = dedup_blocks(blocos)
        if not stats.get("spans_folded"):
            return mensagens, 0, 0

        novas = list(mensagens)
        tocadas: dict = {}
        for (mi, bi, si), antigo, novo in zip(locais, blocos, dobrados):
            if antigo.protected or novo.text == antigo.text:
                continue
            if mi not in tocadas:
                origem = novas[mi]
                copia = dict(origem)
                if isinstance(origem.get("content"), list):
                    copia["content"] = [dict(b) if isinstance(b, dict) else b for b in origem["content"]]
                tocadas[mi] = copia
                novas[mi] = copia
            m = tocadas[mi]
            if bi is None:
                m["content"] = novo.text
            elif si is None:
                m["content"][bi]["content"] = novo.text
            else:
                bloco = dict(m["content"][bi])
                subs = [dict(s) if isinstance(s, dict) else s for s in bloco.get("content", [])]
                subs[si] = dict(subs[si])
                subs[si]["text"] = novo.text
                bloco["content"] = subs
                m["content"][bi] = bloco
        return novas, int(stats["spans_folded"]), int(stats["chars_removed"])
    except Exception:  # noqa: BLE001 - dedup e acessorio: o que falha vai como veio
        return mensagens, 0, 0
