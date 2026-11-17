"""Revisoes do config.json: cada gravacao guarda a versao anterior, e da para voltar.

Trazido do Paperclip, onde toda mudanca de configuracao de agente vira uma
revisao com reversao. Aqui o motivo e o mesmo em escala menor: trocar
`llama_device` ou `default_search_scope` e facil, lembrar o valor antigo
depois que algo piorou, nao.

- `Config.save()` chama `guardar_anterior()` antes de substituir o arquivo. Se o
  conteudo nao mudou, nada se grava.
- Ficam as `MANTER` mais recentes, em `config_history/`, com permissao 0600: a
  copia tem o `server_token`, como o proprio config.
- Tudo que sai daqui para fora (ferramenta MCP, `diff` no terminal) passa por
  `mascarar`, que esconde token e segredo.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .config import REVISOES_MANTER as MANTER  # noqa: E402,F401  (um numero so, onde a gravacao mora)

#: Chaves cujo valor nunca aparece em listagem, diff nem export. Por nome
#: inteiro ou por sufixo, nunca por substring: `max_tokens` contem "token" e e
#: so um numero (um export de teste esvaziou esse campo quando a regra era
#: substring).
SECRETAS = frozenset({"server_token", "client_tokens", "token", "secret", "password", "api_key"})
SUFIXOS_SECRETOS = ("_token", "_secret", "_password", "_api_key", "_apikey")


def _dir() -> Path:
    from . import config
    return config.CONFIG_DIR / "config_history"


def chave_secreta(chave: str) -> bool:
    c = chave.lower()
    return c in SECRETAS or c.endswith(SUFIXOS_SECRETOS)


def mascarar(valor, chave: str = ""):
    if chave_secreta(chave) and valor not in (None, "", {}, []):
        return "***"
    if isinstance(valor, dict):
        return {k: mascarar(v, k) for k, v in valor.items()}
    if isinstance(valor, list):
        return [mascarar(v) for v in valor]
    return valor


#: Mora em config.py: o config grava o historico ao salvar, e o historico
#: precisa do config para achar o arquivo. Com a funcao aqui, os dois se
#: importavam (o ciclo que tests/test_sem_ciclos_de_import.py proibe).
from .config import guardar_revisao_anterior as guardar_anterior  # noqa: E402,F401


def listar_arquivos() -> list[Path]:
    """Mais nova primeiro."""
    d = _dir()
    return sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []


def _ler(p: Path) -> dict:
    try:
        dados = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def diferencas(antes: dict, depois: dict) -> list[dict]:
    """Chaves que mudaram de `antes` para `depois`, ja mascaradas."""
    saida = []
    for k in sorted(set(antes) | set(depois)):
        if antes.get(k) != depois.get(k):
            saida.append({"key": k, "before": mascarar(antes.get(k), k), "after": mascarar(depois.get(k), k)})
    return saida


def historico(limite: int = 10) -> list[dict]:
    """Revisoes, mais nova primeiro. `revision` 1 e a anterior a config atual.

    `changes` diz o que mudou DESSA revisao para a seguinte (a seguinte da 1 e a atual).
    """
    from . import config
    arquivos = listar_arquivos()
    seguinte = _ler(config.CONFIG_FILE)
    saida = []
    for i, arq in enumerate(arquivos, start=1):
        esta = _ler(arq)
        if i <= limite:
            saida.append({
                "revision": i, "saved_before": _quando(arq),
                "changes": diferencas(esta, seguinte),
            })
        seguinte = esta
    return saida


def _quando(arq: Path) -> str:
    try:
        return datetime.strptime(arq.stem, "%Y%m%dT%H%M%S%f").isoformat(timespec="seconds")
    except ValueError:
        return arq.stem


def reverter(revisao: int) -> dict:
    """Volta o config.json para a revisao N (1 = a anterior). A atual vira revisao tambem.

    Grava pelo `Config.save()`, que e atomico e guarda a versao de agora no
    historico: reverter tambem se desfaz.
    """
    from . import config
    arquivos = listar_arquivos()
    if not 1 <= revisao <= len(arquivos):
        raise ValueError(f"revision {revisao} does not exist (1..{len(arquivos)})")
    dados = _ler(arquivos[revisao - 1])
    if not dados:
        raise ValueError(f"revision {revisao} is unreadable")
    antes = _ler(config.CONFIG_FILE)
    known = {k: v for k, v in dados.items() if k in config.Config.__dataclass_fields__}
    config.Config(**known).save()
    return {"reverted_to": revisao, "changes": diferencas(antes, dados)}


def cmd_config(args) -> int:
    if args.acao == "history":
        revs = historico(args.limit)
        if not revs:
            print("no config revisions yet (one is kept every time the config changes)")
        for r in revs:
            print(f"#{r['revision']}  saved {r['saved_before']}")
            for c in r["changes"]:
                print(f"    {c['key']}: {json.dumps(c['before'])} -> {json.dumps(c['after'])}")
        return 0
    if args.acao == "revert":
        try:
            r = reverter(args.revision)
        except ValueError as e:
            print(str(e))
            return 1
        print(f"config reverted to revision {r['reverted_to']}. Restart the daemon for "
              f"settings read at startup. Changed: {', '.join(c['key'] for c in r['changes']) or 'nothing'}")
        return 0
    return 1


def registrar(sub) -> dict:
    p = sub.add_parser("config", help="Config revisions: history and revert")
    s = p.add_subparsers(dest="acao", required=True)
    h = s.add_parser("history")
    h.add_argument("--limit", type=int, default=10)
    r = s.add_parser("revert", help="revert to revision N (1 = the one before the current config)")
    r.add_argument("revision", type=int)
    return {"config": cmd_config}
