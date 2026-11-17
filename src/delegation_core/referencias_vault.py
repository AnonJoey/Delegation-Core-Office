"""Liga `referencias/` ao vault: caminho morto por nota, na busca e numa ferramenta.

- `marcar_mortas(cfg, hits)`: poe `dead_refs` nos acertos da busca que citam
  caminho que nao existe mais. So `stat`, sem busca por nome: a busca nao
  pode ficar mais lenta por isso. Cache por (caminho, mtime) da nota.
- `da_nota` / `varrer`: o relatorio completo, com sugestao de onde o arquivo
  esta agora (plocate, se houver).

Desligado com `referencias_enabled=false`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from .procs import sem_janela
from .referencias import extrair, verificar

logger = logging.getLogger(__name__)

# Lugar onde um arquivo com o mesmo nome nao e "o arquivo que mudou de lugar":
# copia de teste, lixeira, cache, dependencia vendida.
_IGNORAR = ("/.cache/", "/.local/share/Trash/", "/node_modules/", "/.git/", "/__pycache__/",
            "/.venv/", "/site-packages/", "/tmp/", "/proc/")

_CACHE: dict[str, tuple[int, list[str]]] = {}

# Casa do usuario para `~/` e para decidir o que e caminho local; None = a real.
CASA: str | None = None


def _casa(cfg) -> str | None:
    """`referencias_casa` do config vence o HOME do processo.

    O daemon de teste do fork roda com HOME falso, e ali todo `~/` citado
    virava caminho morto (190 em 75 notas contra 84 em 42 com a casa real).
    """
    return CASA or (getattr(cfg, "referencias_casa", "") or None)


def ligado(cfg) -> bool:
    return bool(getattr(cfg, "referencias_enabled", True))


def localizar_plocate(nome: str, limite: int = 200) -> list[str]:
    """Arquivos com exatamente este nome, pelo indice do plocate. Lista vazia se nao houver plocate."""
    exe = shutil.which("plocate")
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "-b", "-e", "-l", str(limite), "--", nome], capture_output=True,
                           text=True, timeout=3, **sem_janela())
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [p for p in r.stdout.splitlines() if p and not any(x in p + "/" for x in _IGNORAR)]


def _arquivo(cfg, caminho: str) -> Path:
    p = Path(caminho)
    return p if p.is_absolute() else Path(cfg.vault) / p


def mortas(cfg, caminho: str) -> list[str]:
    """Caminhos citados pela nota que nao existem, so por `stat`, com cache pelo mtime da nota."""
    arq = _arquivo(cfg, caminho)
    try:
        m = arq.stat().st_mtime_ns
    except OSError:
        return []
    chave = str(arq)
    if chave in _CACHE and _CACHE[chave][0] == m:
        return _CACHE[chave][1]
    try:
        texto = arq.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    rel = caminho
    try:
        rel = str(arq.relative_to(Path(cfg.vault)))
    except ValueError:
        pass
    saida = [] if historica(rel, texto[:600]) else [r.caminho for r in verificar(extrair(texto, casa=_casa(cfg))) if not r.existe]
    _CACHE[chave] = (m, saida)
    return saida


def marcar_mortas(cfg, hits: list[dict]) -> None:
    """Nunca levanta: a marca e um extra da busca, nao pode derruba-la."""
    if not ligado(cfg):
        return
    for h in hits:
        try:
            p = h.get("path") or ""
            if p.endswith(".md"):
                m = mortas(cfg, p)
                if m:
                    h["dead_refs"] = m
        except Exception as e:  # noqa: BLE001
            logger.debug("dead_refs falhou em %s: %s", h.get("path"), e)


def da_nota(cfg, caminho: str, localizar=localizar_plocate) -> dict:
    arq = _arquivo(cfg, caminho)
    texto = arq.read_text(encoding="utf-8", errors="ignore")
    refs = verificar(extrair(texto, casa=_casa(cfg)), localizar=localizar)
    saida = {"note": caminho, "cited": len(refs), "dead": [r.como_dict() for r in refs if not r.existe]}
    if historica(caminho, texto[:600]):
        # pedida pelo nome, responde; mas avisa que caminho velho ali e registro, nao defeito
        saida["historical"] = True
    return saida


def historica(rel: str, cabeca: str = "") -> bool:
    """Registro do que aconteceu, nao instrucao do que fazer: caminho velho ali e fato, nao defeito.

    Transcricao bruta e sessao contam o que existia no dia. Medido no vault
    real: das 134 notas com caminho morto na primeira varredura, as de mais
    mortos eram transcricoes. Nota gerada por maquina (`gerado_por:`) tambem sai.
    """
    partes = Path(rel).parts
    return (bool(partes) and partes[0] in PASTAS_HISTORICAS) or "transcript" in Path(rel).name \
        or "gerado_por:" in cabeca


PASTAS_HISTORICAS = ("Sessions",)


def _notas(cfg, pasta: str = ""):
    raiz = Path(cfg.vault)
    base = raiz / pasta if pasta else raiz
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(raiz)
        if any(x.startswith((".", "_")) for x in rel.parts) or historica(str(rel)):
            continue
        yield str(rel)


def varrer(cfg, pasta: str = "", limite: int = 30, localizar=localizar_plocate) -> dict:
    """Notas com caminho morto, a de mais mortos primeiro. Sugestao so para as `limite` listadas."""
    contagem, citados, total_mortos = [], 0, 0
    for rel in _notas(cfg, pasta):
        try:
            texto = (Path(cfg.vault) / rel).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "gerado_por:" in texto[:600]:
            continue
        refs = verificar(extrair(texto, casa=_casa(cfg)))
        citados += len(refs)
        n = sum(1 for r in refs if not r.existe)
        total_mortos += n
        if n:
            contagem.append((n, rel))
    contagem.sort(key=lambda x: (-x[0], x[1]))
    notas = [da_nota(cfg, rel, localizar) for _, rel in contagem[:limite]]
    return {"folder": pasta or "(all)", "paths_cited": citados, "paths_dead": total_mortos,
            "notes_with_dead": len(contagem), "notes": notas}
