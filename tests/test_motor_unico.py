"""So o engine fala com o modelo local.

Todo pedido de geracao passa pelo DelegationEngine, que aplica orcamento,
fila, arbitro de GPU, idioma e deteccao de resposta vazia. Um modulo que
chamasse /v1/chat/completions por conta propria pularia tudo isso. A regra
estava escrita no docs/MAPA.md sem teste; agora tem.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _quem_chama_o_modelo() -> list[str]:
    achados = []
    for pasta in (RAIZ / "src" / "delegation_core", RAIZ / "hooks"):
        for arq in pasta.rglob("*.py"):
            rel = arq.relative_to(RAIZ).as_posix()
            if rel.startswith("src/delegation_core/graph/"):
                continue
            # O proxy repassa ao provedor (OpenAI) o pedido do agente do usuario,
            # nao gera nada no modelo local: o caminho aparece como rota.
            if rel.startswith("src/delegation_core/proxy/"):
                continue
            if "/v1/chat/completions" in arq.read_text(encoding="utf-8"):
                achados.append(rel)
    return sorted(achados)


def test_so_o_engine_chama_o_endpoint_do_modelo():
    assert _quem_chama_o_modelo() == ["src/delegation_core/engine.py"]


def test_o_proxy_nao_aponta_para_o_modelo_local():
    """A excecao acima so vale enquanto o upstream do proxy for o provedor."""
    from delegation_core.config import Config
    cfg = Config()
    for url in (cfg.proxy_upstream_anthropic, cfg.proxy_upstream_openai):
        assert url.startswith("https://") and "127.0.0.1" not in url and "localhost" not in url
