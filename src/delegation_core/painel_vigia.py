"""O que o painel mostra na aba Vigia: alertas, agenda, recordacao e uso.

Le o estado que os sistemas ja gravam (alertas.json, agenda.json,
recordacao.sqlite3, livro.sqlite3), e nao os objetos vivos, a nao ser para
rodar uma tarefa agora. Assim a aba funciona com o painel dentro do daemon (o
padrao) e degrada para "so leitura" se um dia ele rodar separado.
"""

from __future__ import annotations

import time
from pathlib import Path
from .arquivos_json import ler_json


def _json(caminho: Path) -> dict:
    return ler_json(caminho, dict)


def _vigia_vivo():
    from .ligacao_painel import servidor
    return getattr(servidor(), "_vigia", None)


def estado(cfg, config_dir: Path | None = None, dias: int = 7) -> dict:
    from .config import CONFIG_DIR

    base = Path(config_dir or CONFIG_DIR)
    alertas = _json(base / "alertas.json")
    abertos = [a for a in alertas.get("alertas", {}).values() if a.get("estado") == "disparando"]
    eventos = list(reversed(alertas.get("eventos", [])[-20:]))

    vivo = _vigia_vivo()
    if vivo is not None:
        tarefas = vivo.agenda.proximas()
    else:
        tarefas = [{"nome": n, **e} for n, e in _json(base / "agenda.json").items()]

    desde = time.time() - dias * 86400
    recordacao = uso = None
    try:
        from .sonho_vault import registro
        r = registro(cfg)
        if r is not None:
            recordacao = {"totais": r.estatisticas(), "mais_lembradas": r.mais_lembradas(desde=desde, limite=8),
                          "lacunas": r.lacunas(desde=desde)[:8], "abertas_por_posicao": r.aberturas_por_posicao(desde=desde)}
    except Exception as e:  # noqa: BLE001
        recordacao = {"erro": str(e)}
    try:
        from .livro_mcp import livro
        lv = livro(cfg)
        if lv is not None:
            rel = lv.relatorio(desde=desde)
            uso = {"chamadas": rel["chamadas"], "ferramentas": rel["ferramentas"][:10],
                   "tokens_entregues_estimados": rel["tokens_entregues_estimados"],
                   "tokens_apontados_teto": rel["tokens_apontados_teto"]}
    except Exception as e:  # noqa: BLE001
        uso = {"erro": str(e)}
    # o mesmo arquivo que o hook de inicio de sessao le (atencao.py): o que o
    # agente ve ao abrir a sessao, a pessoa ve aqui
    at = _json(base / "atencao.json")
    atencao = {"itens": at.get("itens") or [], "gerado_em": at.get("gerado_em"), "erros": at.get("erros") or {}}
    return {"atencao": atencao,
            "alertas": {"abertos": abertos, "eventos": eventos, "avaliado_em": alertas.get("avaliado_em")},
            "agenda": {"tarefas": tarefas, "ao_vivo": vivo is not None},
            "recordacao": recordacao, "uso": uso, "dias": dias}


def rodar(nome: str) -> dict:
    vivo = _vigia_vivo()
    if vivo is None:
        return {"error": "the scheduler runs inside the daemon; this dashboard is not attached to it"}
    return vivo.rodar(nome)
