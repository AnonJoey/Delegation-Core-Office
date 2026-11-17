"""Liga `fatos/` ao vault: extrai das notas vivas, fora de hora, e responde `vault_facts`.

- Pastas vivas (`fatos_pastas`): decisao, correcao, procedimento, infra,
  projeto, ferramenta. Sessao e transcricao contam o que aconteceu; Reference
  tem 10 mil notas, quase todas geradas ou importadas. Ficam de fora.
- Uma nota so volta ao modelo quando o texto dela ou o prompt muda (assinatura sha1).
- Segredo nunca vira fato: valor que o pacote `segredos` cobriria e descartado.

Desligado com `fatos_enabled=false`.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from .fatos import ArmazemDeFatos, extrair

logger = logging.getLogger(__name__)

PASTAS_PADRAO = ("Decisions", "Fixes", "Infrastructure", "Procedures", "Projects", "Tools")
_ARMAZEM: dict[str, ArmazemDeFatos] = {}


def armazem(cfg) -> ArmazemDeFatos | None:
    if not getattr(cfg, "fatos_enabled", True):
        return None
    from .config import CONFIG_DIR

    caminho = str(Path(getattr(cfg, "fatos_path", "") or CONFIG_DIR / "fatos.sqlite3"))
    if caminho not in _ARMAZEM:
        _ARMAZEM[caminho] = ArmazemDeFatos(caminho)
    return _ARMAZEM[caminho]


def pastas(cfg) -> list[str]:
    return list(getattr(cfg, "fatos_pastas", None) or PASTAS_PADRAO)


def notas_vivas(cfg) -> list[tuple[str, str, str]]:
    """(caminho relativo, texto, data) das notas vivas, a mais nova primeiro."""
    from .facetas import data_da_nota

    raiz = Path(cfg.vault)
    saida = []
    for pasta in pastas(cfg):
        base = raiz / pasta
        if not base.is_dir():
            continue
        for p in base.rglob("*.md"):
            rel = str(p.relative_to(raiz))
            if any(x.startswith((".", "_")) for x in Path(rel).parts):
                continue
            try:
                texto = p.read_text(encoding="utf-8", errors="ignore")
                mtime = p.stat().st_mtime
            except OSError:
                continue
            if "gerado_por:" in texto[:600]:
                continue
            saida.append((rel, texto, data_da_nota(rel, texto[:600], mtime)))
    saida.sort(key=lambda x: (x[2], x[0]), reverse=True)
    return saida


def assinatura(texto: str) -> str:
    """Texto da nota MAIS o prompt: prompt novo e extracao nova, sem apagar nada a mao.

    Pego na troca do primeiro prompt pelo segundo: as 40 notas ja extraidas
    tinham o mesmo texto, entao ficariam com os fatos do prompt velho.
    """
    from .fatos.extracao import SISTEMA

    return hashlib.sha1((SISTEMA + "\0" + texto).encode("utf-8", "ignore")).hexdigest()


def _sem_segredo(cfg, fatos):
    if not getattr(cfg, "redigir_segredos", True):
        return fatos
    from .segredos import redigir

    token = getattr(cfg, "server_token", "") or ""
    extras = (token,) if token else ()
    return [f for f in fatos if not redigir(f.valor, extras)[1] and not redigir(f.citacao, extras)[1]]


def pendentes(cfg) -> list[tuple[str, str, str]]:
    arm = armazem(cfg)
    if arm is None:
        return []
    return [(rel, t, d) for rel, t, d in notas_vivas(cfg) if arm.precisa(rel, assinatura(t))]


def extrair_pendentes(vault, maximo: int = 40, perguntar=None, prazo_s: float = 1800) -> dict:
    """Extrai ate `maximo` notas pendentes, a mais nova primeiro, parando em `prazo_s`."""
    cfg = vault.cfg
    arm = armazem(cfg)
    if arm is None:
        return {"disabled": True}
    vivas = notas_vivas(cfg)
    esquecidas = arm.esquecer_exceto({rel for rel, _, _ in vivas})
    fila = [(rel, t, d) for rel, t, d in vivas if arm.precisa(rel, assinatura(t))]
    if perguntar is None:
        from .engine import modelo_local_liberado, perguntar_local, resultado_adiado
        if not modelo_local_liberado(cfg):
            # Medido: ~13 s por nota com o gemma de 12B (40 notas em 537 s).
            return {**resultado_adiado(len(fila), segundos_por_item=13.0),
                    "forgotten_notes": esquecidas}
        perguntar = perguntar_local(cfg, max_tokens=1800, tarefa="fatos")
    inicio, feitas, fatos_n, falhas = time.time(), [], 0, []
    for rel, texto, data in fila[:max(0, int(maximo))]:
        if time.time() - inicio > prazo_s:
            break
        try:
            fatos = _sem_segredo(cfg, extrair(texto, perguntar, titulo=Path(rel).stem))
        except Exception as e:  # noqa: BLE001 - uma nota ruim nao para a fila
            falhas.append({"note": rel, "error": str(e)[:200]})
            continue
        arm.substituir(rel, data, assinatura(texto), fatos)
        feitas.append(rel)
        fatos_n += len(fatos)
    return {"extracted_notes": len(feitas), "facts": fatos_n, "failed": falhas,
            "pending_left": len(fila) - len(feitas) - len(falhas), "forgotten_notes": esquecidas,
            "seconds": round(time.time() - inicio, 1)}


def para_busca(cfg, consulta: str, limite: int = 3) -> list[dict]:
    """Fatos para anexar a um search_vault: valor atual, de onde veio, e se ha divergencia. Nunca levanta."""
    try:
        arm = armazem(cfg)
        if arm is None:
            return []
        from .ranqueamento.lexico import termos_da_consulta

        grupos = arm.por_termos(termos_da_consulta(consulta), limite)
    except Exception as e:  # noqa: BLE001 - extra da busca, nao pode derruba-la
        logger.debug("fatos na busca falhou: %s", e)
        return []
    saida = []
    for g in grupos:
        topo = g["values"][0]
        item = {"subject": g["subject"], "attribute": g["attribute"], "current": g["current"],
                "from": g["current_from"], "date": topo["date"]}
        if g["divergent"]:
            item["divergent"] = True
            item["other_values"] = [{"value": v["value"], "note": v["note"], "date": v["date"]}
                                    for v in g["values"][1:4]]
        saida.append(item)
    return saida


def extrair_uma(vault, rel: str, perguntar=None) -> dict:
    """Extrai uma nota viva, se o texto (ou o prompt) mudou desde a ultima extracao."""
    from .facetas import data_da_nota

    cfg = vault.cfg
    arm = armazem(cfg)
    if arm is None:
        return {"disabled": True}
    p = Path(cfg.vault) / rel
    texto = p.read_text(encoding="utf-8", errors="ignore")
    if "gerado_por:" in texto[:600] or not arm.precisa(rel, assinatura(texto)):
        return {"note": rel, "skipped": True}
    if perguntar is None:
        from .engine import modelo_local_liberado, perguntar_local
        if not modelo_local_liberado(cfg):
            return {"note": rel, "skipped": "agent_mode"}
        perguntar = perguntar_local(cfg, max_tokens=1800, tarefa="fatos")
    fatos = _sem_segredo(cfg, extrair(texto, perguntar, titulo=Path(rel).stem))
    arm.substituir(rel, data_da_nota(rel, texto[:600], p.stat().st_mtime), assinatura(texto), fatos)
    return {"note": rel, "facts": len(fatos)}


def apos_escrita(vault, rel: str, submeter=None) -> str | None:
    """Agenda a extracao de uma nota recem escrita, se ela esta numa pasta viva. Devolve o job_id."""
    cfg = vault.cfg
    if not getattr(cfg, "fatos_enabled", True) or not getattr(cfg, "fatos_na_escrita", True):
        return None
    from .engine import modelo_local_liberado

    if not modelo_local_liberado(cfg):
        return None  # modo agent: escrever uma nota nao pode acordar o modelo de 10 GB
    partes = Path(rel).parts
    if not partes or partes[0] not in pastas(cfg):
        return None
    if submeter is None:
        from . import jobs
        submeter = SUBMETER_PADRAO or jobs.submit
    return submeter("fatos_nota", extrair_uma, vault, rel)


#: Troca de quem agenda; a suite poe um que nao agenda nada, para uma escrita
#: de teste nunca acordar o modelo local de verdade (conftest.py).
SUBMETER_PADRAO = None
