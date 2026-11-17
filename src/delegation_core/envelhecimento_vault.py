"""Liga `envelhecimento/` ao vault: o que esfria, o que expira, e o que se faz com isso.

O pacote `envelhecimento` nao sabe o que e vault. Este modulo le o `cfg`, lista as notas,
monta o plano e o aplica por caminhos que o delegation-core ja tinha:

- **Expirar e esquecer** passam por `memoria.esquecer`: a nota vai para `.lixeira/<data>/`,
  sai do indice e o texto inteiro fica no historico. `vault_note_restore` a traz de volta.
- **Compactar** guarda o texto inteiro no historico e regrava a nota como resumo mais fatos
  duraveis (`compactar`). Tambem volta com `vault_note_restore`.
- A varredura **nunca** apaga de verdade, e por padrao so mostra o plano (`aplicar=False`).

## O que conta como "episodico"

Um vault de notas nao tem camada. As pastas de `envelhecimento_pastas` (padrao: so `Sessions`,
onde estao as transcricoes e os resumos de sessao) valem como episodicas; o resto do vault
conta como semantico e nunca esfria. A validade `expires_at:` do frontmatter, ao contrario,
vale no vault inteiro.

A idade de uma nota vem da data dela (`facetas.data_da_nota`: nome do arquivo, frontmatter ou
mtime) e nao do mtime puro, porque os passes de relink e manutencao reescrevem notas e
renovariam a idade de tudo.

Desligado por padrao: `envelhecimento_enabled=false` na config.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, time as hora
from pathlib import Path

from .cabeca_da_nota import frontmatter_de, ler_cabeca
from .envelhecimento import Parametros, lambda_da_meia_vida
from .envelhecimento.acessos import Acessos
from .envelhecimento.compactacao import compactar
from .envelhecimento.varredura import Nota, Plano, planejar

logger = logging.getLogger(__name__)

PASTAS_PADRAO = ("Sessions",)
_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_LINHA_COMPACTED = re.compile(r"^compacted:.*$", re.MULTILINE)
_ACESSOS: dict[str, Acessos] = {}


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "envelhecimento_enabled", False))


def acessos(cfg) -> Acessos | None:
    if not ligado(cfg):
        return None
    from .config import CONFIG_DIR

    caminho = str(Path(getattr(cfg, "envelhecimento_path", "") or CONFIG_DIR / "acessos.sqlite3"))
    if caminho not in _ACESSOS:
        _ACESSOS[caminho] = Acessos(caminho)
    return _ACESSOS[caminho]


def pastas(cfg) -> list[str]:
    return list(getattr(cfg, "envelhecimento_pastas", None) or PASTAS_PADRAO)


def parametros(cfg) -> Parametros:
    meia_vida = float(getattr(cfg, "envelhecimento_meia_vida_dias", 35.0) or 35.0)
    if not meia_vida > 0:
        meia_vida = 35.0
    limiar = float(getattr(cfg, "envelhecimento_limiar_frio", 0.20))
    return Parametros(lamb=lambda_da_meia_vida(meia_vida), limiar_frio=limiar)


# ── leitura do uso ─────────────────────────────────────────────────────────


def registrar_leituras(cfg, caminhos) -> None:
    """Cada nota devolvida por uma leitura ou busca conta como um acesso. Nunca levanta."""
    try:
        a = acessos(cfg)
        if a is None:
            return
        agora = int(time.time() * 1_000_000)
        for rel in dict.fromkeys(c for c in caminhos if c):
            a.registrar(rel, agora)
    except Exception as e:  # noqa: BLE001 - contar uso nao pode derrubar a leitura
        logger.warning("envelhecimento nao registrou a leitura: %s", e)


def depois_de_restaurar(cfg, rel: str, resultado: dict) -> None:
    """Quem foi buscar a nota no historico a quer viva: restaurar conta como leitura, para a varredura
    seguinte nao a compactar de novo. Chamada por quem restaura (a ferramenta e o painel); no-op desligado."""
    if "error" not in resultado:
        registrar_leituras(cfg, [rel])


def votar(vault, nota: str, voto: str) -> dict:
    """`record_feedback`: helpful, not_helpful, stale ou wrong movem a saliencia da nota."""
    from . import memoria

    cfg = vault.cfg
    a = acessos(cfg)
    if a is None:
        return {"error": "envelhecimento desligado (envelhecimento_enabled=false)"}
    p, erro = memoria.resolver_unica(vault, nota)
    if erro:
        return erro
    rel = p.relative_to(Path(cfg.vault)).as_posix()
    try:
        nova = a.votar(rel, voto, parametros(cfg))
    except ValueError as e:
        return {"error": str(e), "kind": "invalid"}
    return {"status": "ok", "path": rel, "vote": voto, "salience": nova}


# ── montar as notas ────────────────────────────────────────────────────────


def _em_us(v) -> int | None:
    """Um instante de frontmatter (data, data e hora ou texto ISO) em microssegundos; None se nao der."""
    try:
        if isinstance(v, datetime):
            return int(v.timestamp() * 1_000_000)
        if isinstance(v, date):
            return int(datetime.combine(v, hora.min).timestamp() * 1_000_000)
        if isinstance(v, str) and v.strip():
            return int(datetime.fromisoformat(v.strip().replace("Z", "+00:00")).timestamp() * 1_000_000)
    except (ValueError, OverflowError, OSError):
        return None
    return None


def _data_em_us(rel: str, cabeca: str, mtime: float) -> int:
    from .facetas import data_da_nota

    d = data_da_nota(rel, cabeca[:600], mtime)
    try:
        return int(datetime.strptime(d, "%Y-%m-%d").timestamp() * 1_000_000)
    except ValueError:
        return int(mtime * 1_000_000)


def notas_para_varrer(cfg) -> list[Nota]:
    """Toda nota do vault como candidata. So as pastas episodicas esfriam; as demais so podem expirar."""
    from .listagem_vault import notas_do_vault

    a = acessos(cfg)
    usos = a.todas() if a is not None else {}
    episodicas = set(pastas(cfg))
    raiz = Path(cfg.vault)
    saida = []
    for rel in notas_do_vault(cfg):
        episodica = rel.split("/")[0] in episodicas
        p = raiz / rel
        cabeca = ler_cabeca(p)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if cabeca is None:
            continue
        if not episodica and "expires_at" not in cabeca:
            continue  # uma nota semantica so interessa se tiver validade
        fm = frontmatter_de(cabeca)
        expira = _em_us(fm.get("expires_at")) if "expires_at" in fm else None
        if not episodica and expira is None:
            continue
        uso = usos.get(rel) or {}
        compactada = fm.get("compacted") is True
        saida.append(Nota(
            caminho=rel, camada="episodic" if episodica else "semantic",
            atualizada_em_us=_data_em_us(rel, cabeca, mtime), acessos=int(uso.get("total") or 0),
            ultimo_acesso_us=uso.get("ultimo_us"), frontmatter=fm, expira_em_us=expira,
            saliencia=uso.get("saliencia"),
            compactada_em_us=int(mtime * 1_000_000) if compactada else None))
    return saida


# ── aplicar ────────────────────────────────────────────────────────────────


def texto_compactado(texto: str) -> str:
    """A nota inteira regravada como resumo mais fatos, com `compacted: true` no frontmatter."""
    m = _FRONTMATTER.match(texto)
    bruto, corpo = (m.group(1), texto[m.end():]) if m else ("", texto)
    fm = frontmatter_de(texto) if m else {}
    _, novo_corpo = compactar(fm, corpo)
    if _LINHA_COMPACTED.search(bruto):
        bruto = _LINHA_COMPACTED.sub("compacted: true", bruto, count=1)
    else:
        bruto = (bruto + "\n" if bruto else "") + "compacted: true"
    return "---\n" + bruto + "\n---\n\n" + novo_corpo


def _compactar_nota(vault, rel: str) -> dict:
    from . import memoria
    from .historico_vault import abrir
    from .notewriter import save_note

    cfg = vault.cfg
    p = Path(cfg.vault) / rel
    antigo = p.read_bytes()
    # CRLF vira LF antes de separar o frontmatter: nota do Windows perdia titulo e data na
    # versao compactada (CI de 17/11/2026). Os bytes originais seguem para o historico.
    novo = texto_compactado(antigo.decode("utf-8", errors="replace").replace("\r\n", "\n"))
    if len(novo.encode("utf-8")) >= len(antigo):
        return {"path": rel, "skipped": "compaction would not make the note smaller"}
    memoria._guardar_versao(cfg, rel, antigo, "antes de compactar (envelhecimento)")
    r = save_note(vault, rel, novo)
    if "error" in r:
        return {"path": rel, "error": r["error"]}
    h = abrir(cfg)
    if h is not None:
        h.registrar(rel, novo, origem="compactada (envelhecimento)")
    return {"path": rel, "status": "compacted", "bytes_before": len(antigo), "bytes_after": r.get("bytes")}


def _esquecer_nota(vault, rel: str, motivo: str) -> dict:
    from . import memoria

    r = memoria.esquecer(vault, rel, motivo, autor="envelhecimento")
    if "error" in r:
        return {"path": rel, "error": r["error"]}
    a = acessos(vault.cfg)
    if a is not None:
        a.esquecer(rel)
    return {"path": rel, "status": "forgotten", "trash": r.get("trash")}


def _linha(f) -> dict:
    return {"path": f.caminho, "retention": round(f.retencao, 4), "age_days": round(f.idade_dias, 1), "accesses": f.acessos}


def varrer(vault, *, aplicar: bool = False, limite: int = 200, agora_us: int | None = None) -> dict:
    """Planeja a varredura e, com `aplicar`, executa no maximo `limite` notas por categoria."""
    cfg = vault.cfg
    if not ligado(cfg):
        return {"error": "envelhecimento desligado (envelhecimento_enabled=false)"}
    agora = int(time.time() * 1_000_000) if agora_us is None else agora_us
    compactar_frias = bool(getattr(cfg, "envelhecimento_compactar", True))
    plano: Plano = planejar(notas_para_varrer(cfg), parametros(cfg), agora, compactar_frias=compactar_frias)
    limite = max(1, int(limite))
    relatorio = {
        "dry_run": not aplicar, "evaluated": plano.avaliadas, "compact_cold": compactar_frias,
        "expired": [{"path": e.caminho, "expired_at_us": e.expirou_em_us} for e in plano.expiradas],
        "to_compact": [_linha(f) for f in plano.compactar], "to_forget": [_linha(f) for f in plano.esquecer],
    }
    if not aplicar:
        return relatorio
    feitos: list[dict] = []
    for e in plano.expiradas[:limite]:
        feitos.append(_esquecer_nota(vault, e.caminho, "expirada (expires_at <= agora)"))
    for f in plano.compactar[:limite]:
        feitos.append(_compactar_nota(vault, f.caminho))
    for f in plano.esquecer[:limite]:
        feitos.append(_esquecer_nota(vault, f.caminho, f"fria (retencao {f.retencao:.3f})"))
    relatorio["applied"] = feitos
    relatorio["remaining"] = (max(0, len(plano.expiradas) - limite) + max(0, len(plano.compactar) - limite)
                              + max(0, len(plano.esquecer) - limite))
    return relatorio
