"""Liga o pacote `historico` ao vault: onde fica, o que varre, e quando.

O pacote `historico` nao sabe o que e vault. Este modulo sabe, e e o unico que
precisa saber: le o `cfg`, lista as notas, e embrulha as operacoes em lote.

## Quando fotografa

- **Antes e depois** de cada passe em lote (relink, manutencao, rename), por
  `sob_historico`. O antes guarda o estado que o passe vai mudar; o depois
  marca a versao nova com o nome da operacao, para que a pergunta "quem
  mexeu nesta nota" tenha resposta.
- **Sob demanda**, por `fotografar`, que e o que um agendamento chama.

Falha no historico nunca derruba a operacao: guardar a versao anterior e
protecao, e uma protecao que impede o trabalho de acontecer e pior que nenhuma.
Por isso `sob_historico` engole e registra excecao do proprio historico, mas
nunca a da operacao embrulhada.

`historico_enabled = false` na config desliga tudo, e entao nenhuma linha do
pacote roda.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("historico_vault")

_INSTANCIAS: dict[str, object] = {}
_TRAVA = threading.Lock()


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "historico_enabled", True))


def abrir(cfg):
    """O Historico deste vault, um por processo. None se desligado."""
    if not ligado(cfg):
        return None
    from .historico import Historico

    raiz = Path(cfg.vault) / ".historico"
    chave = str(raiz)
    with _TRAVA:
        if chave not in _INSTANCIAS:
            _INSTANCIAS[chave] = Historico(raiz)
        return _INSTANCIAS[chave]


from .listagem_vault import notas_do_vault  # noqa: E402,F401  (nome mantido aqui)


def fotografar(cfg, origem: str = "varredura") -> dict | None:
    h = abrir(cfg)
    if h is None:
        return None
    return h.varrer(cfg.vault, notas_do_vault(cfg), origem=origem)


@contextmanager
def sob_historico(cfg, operacao: str):
    """Fotografa antes e depois da operacao; o historico nunca a derruba."""
    try:
        fotografar(cfg, origem=f"antes de {operacao}")
    except Exception as e:  # noqa: BLE001 - protecao nao pode impedir o trabalho
        logger.warning("historico antes de %s falhou: %s", operacao, e)
    try:
        yield
    finally:
        try:
            fotografar(cfg, origem=operacao)
        except Exception as e:  # noqa: BLE001
            logger.warning("historico depois de %s falhou: %s", operacao, e)


def renomeada(cfg, de: str, para: str) -> None:
    """Leva o historico da nota para o caminho novo. Nunca levanta."""
    try:
        h = abrir(cfg)
        if h is not None:
            h.renomear(de, para)
    except Exception as e:  # noqa: BLE001
        logger.warning("historico nao acompanhou o rename %s -> %s: %s", de, para, e)


def restaurar(vault, rel: str, n: int) -> dict:
    """Volta a nota `rel` para a versao `n` (1 = a mais nova guardada).

    Reversivel por construcao: o texto atual e guardado antes, com origem
    "antes de restaurar", entao desfazer uma restauracao e restaurar de novo.
    Uma nota apagada do disco volta a existir no mesmo caminho.
    """
    from .notes import resolve_in_vault
    from .notewriter import save_note

    cfg = vault.cfg
    h = abrir(cfg)
    if h is None:
        return {"error": "historico desligado (historico_enabled=false)"}
    texto = h.texto(rel, n)
    if texto is None:
        return {"error": f"Version {n} of {rel} not found", "versions": len(h.versoes(rel, limite=10_000))}
    dest = resolve_in_vault(cfg.vault, rel)
    if dest is None:
        return {"error": f"Path outside the vault: {rel}"}
    if dest.is_file():
        h.registrar(rel, dest.read_bytes(), origem="antes de restaurar")
        r = save_note(vault, rel, texto)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(texto, encoding="utf-8")
        folder = rel.split("/")[0]
        if vault.index_note(texto, {"title": dest.stem, "path": rel, "folder": folder}):
            vault.stamp_indexed([rel])
        r = {"status": "ok", "path": rel, "bytes": len(texto.encode("utf-8")), "recreated": True}
    if "error" not in r:
        h.registrar(rel, texto, origem=f"restaurada da versao {n}")
    return r
