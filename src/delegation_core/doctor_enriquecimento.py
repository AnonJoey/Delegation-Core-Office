"""Checagens do `doctor` para os sistemas do enriquecimento de 27/09.

Cada sistema novo degrada em silencio por desenho: sem reordenador a busca fica
densa, sem dados de OCR a imagem vira so metadado, sem daemon a agenda nao
roda. Degradar em silencio e o certo para a ferramenta e o errado para quem
administra, e o `doctor` e onde isso aparece. Mesmo formato das checagens de
`doctor.py`: {check, status (ok/warn/error/skip), detail, fix}.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path


def _situacao_no_daemon(cfg) -> dict | None:
    """O estado da busca hibrida como o DAEMON o ve, ou None se nao houver daemon.

    Perguntar a este processo daria a resposta errada: o reordenador carrega no
    daemon, e a memoria livre da placa vista daqui ja desconta o que o proprio
    daemon ocupa. E o erro que o check_gpu_visivel ja cometeu uma vez, olhando
    para a CLI em vez do daemon (26/09); este nasceu com a mesma falha e foi
    corrigido antes do commit, no teste contra o daemon do fork.
    """
    try:
        from . import daemon
        if not daemon.is_listening(cfg):
            return None
        hb = daemon.call_tool(cfg, "heartbeat")
        return hb.get("hybrid_search") if isinstance(hb, dict) else None
    except Exception:  # noqa: BLE001 - sem daemon, cai para a previsao local
        return None


def check_busca_hibrida(cfg) -> dict:
    from . import busca_hibrida
    from .ranqueamento.rerank import MODELO_PADRAO

    nome = "hybrid_search"
    if not busca_hibrida.ligado(cfg):
        return {"check": nome, "status": "skip", "detail": "busca_hibrida=false: search is dense only"}
    no_daemon = _situacao_no_daemon(cfg)
    if no_daemon:
        if no_daemon.get("reordenador_carregado"):
            return {"check": nome, "status": "ok",
                    "detail": f"daemon: hybrid + rerank active, {no_daemon.get('notas_no_indice_lexico')} notes in the lexical index"}
        if no_daemon.get("motivo_sem_reordenador"):
            return {"check": nome, "status": "warn",
                    "detail": f"daemon: search stays dense ({no_daemon['motivo_sem_reordenador']})",
                    "fix": "see busca_reordenador_* in config.json; the reason above names what is missing"}
    if not getattr(cfg, "busca_reordenar", True):
        return {"check": nome, "status": "warn",
                "detail": "reranker disabled, so search stays dense (fusion without it measured worse)",
                "fix": "set busca_reordenar=true"}
    modelo = getattr(cfg, "busca_reordenador_modelo", "") or MODELO_PADRAO
    if not busca_hibrida._modelo_no_cache(modelo):
        return {"check": nome, "status": "warn",
                "detail": f"reranker {modelo} not downloaded: search stays dense",
                "fix": f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{modelo}')\""}
    disp = getattr(cfg, "busca_reordenador_dispositivo", "auto") or "auto"
    if disp == "auto":
        livre = busca_hibrida._gpu_livre_mb()
        if livre < 1500:
            return {"check": nome, "status": "warn",
                    "detail": f"predicted from this process: only {livre} MiB free on the GPU (needs 1500), search would stay dense",
                    "fix": "free GPU memory, or set busca_reordenador_dispositivo=cpu (about 6 s per search)"}
        return {"check": nome, "status": "ok",
                "detail": f"predicted from this process: hybrid + rerank on GPU ({livre} MiB free), {modelo}"}
    return {"check": nome, "status": "ok", "detail": f"predicted from this process: hybrid + rerank on {disp}, {modelo}"}


def check_ocr() -> dict:
    from .extractor import tessdata_padrao
    from .imagens import idiomas_disponiveis

    if not shutil.which("tesseract"):
        return {"check": "ocr", "status": "warn",
                "detail": "tesseract not installed: images are indexed by date and size only",
                "fix": "install tesseract (pacman -S tesseract / apt install tesseract-ocr), then delegation-core ocr-setup"}
    idiomas = set(idiomas_disponiveis(tessdata_padrao()))
    faltam = [i for i in ("por", "eng") if i not in idiomas]
    if faltam:
        return {"check": "ocr", "status": "warn",
                "detail": f"OCR language data missing: {', '.join(faltam)}",
                "fix": "delegation-core ocr-setup"}
    return {"check": "ocr", "status": "ok", "detail": f"tesseract with {', '.join(sorted(idiomas - {'osd'}))}"}


def check_agenda(cfg, config_dir: Path | None = None) -> dict:
    from .config import CONFIG_DIR

    if not getattr(cfg, "agenda_enabled", True):
        return {"check": "scheduler", "status": "skip", "detail": "agenda_enabled=false"}
    arq = Path(config_dir or CONFIG_DIR) / "agenda.json"
    if not arq.is_file():
        return {"check": "scheduler", "status": "warn",
                "detail": "no scheduler state yet: the daemon has not run with the scheduler",
                "fix": "restart the daemon (delegation-core service install)"}
    try:
        estado = json.loads(arq.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"check": "scheduler", "status": "warn", "detail": f"agenda.json unreadable: {e}",
                "fix": f"delete {arq}; the daemon rebuilds it"}
    falhando = {n: e.get("ultimo_erro", "") for n, e in estado.items() if int(e.get("falhas_seguidas", 0)) >= 2}
    if falhando:
        return {"check": "scheduler", "status": "error",
                "detail": "; ".join(f"{n} failing: {erro[:80]}" for n, erro in falhando.items()),
                "fix": "schedule_list shows the error; logs(source='server', grep='agenda') shows context"}
    rodaram = sum(1 for e in estado.values() if e.get("execucoes"))
    return {"check": "scheduler", "status": "ok", "detail": f"{len(estado)} task(s), {rodaram} have run, none failing"}


def check_alertas(config_dir: Path | None = None) -> dict:
    from .config import CONFIG_DIR

    arq = Path(config_dir or CONFIG_DIR) / "alertas.json"
    if not arq.is_file():
        return {"check": "alerts", "status": "ok", "detail": "no alerts evaluated yet"}
    try:
        alertas = json.loads(arq.read_text(encoding="utf-8")).get("alertas", {})
    except ValueError:
        return {"check": "alerts", "status": "warn", "detail": "alertas.json unreadable", "fix": f"delete {arq}"}
    abertos = [a for a in alertas.values() if a.get("estado") == "disparando"]
    if not abertos:
        return {"check": "alerts", "status": "ok", "detail": "no alert firing"}
    criticos = [a for a in abertos if a.get("severidade") == "critico"]
    return {"check": "alerts", "status": "error" if criticos else "warn",
            "detail": "; ".join(a.get("mensagem", "")[:90] for a in abertos[:4]),
            "fix": "alerts() lists them; each message names what to look at"}


def _integridade_do_banco_do_historico(raiz: Path) -> tuple[bool, str]:
    """`PRAGMA quick_check` no banco do historico, aberto so para leitura."""
    import sqlite3

    banco = raiz / "versoes.sqlite3"
    if not banco.is_file():
        return True, "no database yet"
    try:
        con = sqlite3.connect(f"file:{banco}?mode=ro", uri=True, timeout=10)
        try:
            linhas = con.execute("PRAGMA quick_check(3)").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return False, f"{type(e).__name__}: {e}"
    resposta = "; ".join(str(l[0]).splitlines()[0] for l in linhas)
    return resposta == "ok", resposta


def check_historico(cfg) -> dict:
    if not getattr(cfg, "historico_enabled", True):
        return {"check": "note_history", "status": "skip", "detail": "historico_enabled=false"}
    raiz = Path(cfg.vault) / ".historico"
    if not raiz.is_dir():
        return {"check": "note_history", "status": "ok", "detail": "no snapshot yet (first one runs on the next pass)"}
    t0 = time.monotonic()
    disco = sum(f.stat().st_size for f in (raiz / "objetos").rglob("*") if f.is_file()) if (raiz / "objetos").is_dir() else 0
    mb = disco / 1e6
    integro, resposta = _integridade_do_banco_do_historico(raiz)
    if not integro:
        # Visto em 2026-11-04: o agendador falhou 166 vezes seguidas com "database disk image is
        # malformed" e este check dizia "ok", porque so media o tamanho dos objetos. A causa foi um
        # sync (rsync) que levava o banco vivo e o -wal de uma maquina para outra.
        return {"check": "note_history", "status": "error",
                "detail": f"versoes.sqlite3 failed its integrity check: {resposta[:160]}",
                "fix": ("stop the daemon (delegation-core service stop) and keep a copy of "
                        ".historico/versoes.sqlite3*; rebuild with `sqlite3 versoes.sqlite3 .recover | "
                        "sqlite3 novo.sqlite3`, put the new file in place with NO -wal or -shm beside it, "
                        "start the daemon. First make sure no sync tool (rsync, Syncthing, OneDrive) copies "
                        ".historico/versoes.sqlite3*: it is per-machine state, and a copied -wal is what "
                        "damages it. The blobs in .historico/objetos are safe to sync")}
    status = "warn" if mb > 1000 else "ok"
    r = {"check": "note_history", "status": status, "detail": f"{mb:.0f} MB of note versions, database integrity ok"}
    if status == "warn":
        r["fix"] = "schedule_run('podar-historico') keeps the newest 50 versions per note"
    r["detail"] += f" (measured in {time.monotonic() - t0:.1f} s)"
    return r


def check_fatos(cfg) -> dict:
    """Quantas notas vivas ainda nao passaram pela extracao de fatos (ou mudaram depois dela)."""
    if not getattr(cfg, "fatos_enabled", True):
        return {"check": "facts", "status": "skip", "detail": "fatos_enabled=false"}
    from . import fatos_vault

    arm = fatos_vault.armazem(cfg)
    st = arm.estatisticas()
    pend = len(fatos_vault.pendentes(cfg))
    r = {"check": "facts", "status": "ok",
         "detail": f"{st['facts']} facts from {st['notes']} notes; {pend} note(s) pending extraction"}
    # a tarefa noturna faz 40 por noite: acima de 3 noites de fila, algo nao esta rodando
    if pend > 120:
        r["status"] = "warn"
        r["fix"] = "schedule_run('fatos-noturno') extracts 40 notes per run (~8 min of local model)"
    return r


def check_atencao(config_dir: Path | None = None, agora: float | None = None) -> dict:
    """atencao.json e reescrito a cada 10 min pela tarefa de alertas; velho = hook mostrando coisa velha."""
    from .config import CONFIG_DIR

    arq = Path(config_dir or CONFIG_DIR) / "atencao.json"
    if not arq.is_file():
        return {"check": "attention", "status": "ok", "detail": "not composed yet (the alerts task writes it)"}
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
    except ValueError:
        return {"check": "attention", "status": "warn", "detail": "atencao.json unreadable", "fix": f"delete {arq}"}
    idade = (agora or time.time()) - float(d.get("gerado_em") or 0)
    r = {"check": "attention", "status": "ok",
         "detail": f"{len(d.get('itens') or [])} item(s), composed {idade / 60:.0f} min ago"}
    if d.get("erros"):
        r["status"] = "warn"
        r["detail"] += "; failing sources: " + ", ".join(sorted(d["erros"]))
        r["fix"] = "logs(source='server', grep='atencao')"
    elif idade > 3600:
        r["status"] = "warn"
        r["fix"] = "the alerts task has not run for an hour: schedule_list, or is the daemon down?"
    return r


def check_codigo(cfg) -> dict:
    if not getattr(cfg, "codigo_enabled", True):
        return {"check": "code_links", "status": "skip", "detail": "codigo_enabled=false"}
    from . import codigo_vault

    em_disco = codigo_vault.grafos_em_disco(cfg)
    if not em_disco:
        return {"check": "code_links", "status": "ok", "detail": "no code graph built"}
    t0 = time.monotonic()
    idx = codigo_vault.indice(cfg)
    return {"check": "code_links", "status": "ok",
            "detail": f"{len(idx.grafos())} of {len(em_disco)} graph(s) indexed ({time.monotonic() - t0:.1f} s)"}


def todas(cfg) -> list[dict]:
    return [check_busca_hibrida(cfg), check_ocr(), check_agenda(cfg), check_alertas(), check_historico(cfg),
            check_fatos(cfg), check_atencao(), check_codigo(cfg)]
