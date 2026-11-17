"""Liga o pacote `sonho` ao vault: registro de recordacao na busca e o sonho noturno.

## O sonho, passo a passo

1. **O que mudou**: notas escritas a mao alteradas nos ultimos `dias` (pelo
   historico quando ligado, senao pelo mtime). Transcricao bruta e nota
   gerada ficam de fora: nao sao afirmacao de ninguem.
2. **Com quem comparar**: para cada uma, as notas mais parecidas e MAIS
   ANTIGAS, pela busca densa.
3. **Julgar**: o modelo local diz se a nova contradiz, atualiza, repete ou
   complementa a antiga, citando as duas. A citacao e conferida no texto.
4. **Confirmar**: cada achado passa por uma segunda pergunta, so com as duas
   citacoes: e o mesmo assunto especifico, e A substitui B? Sai o que nao passa.
5. **Recordacao**: as notas mais lembradas da semana e as perguntas que se
   repetem sem boa resposta.
6. **Relatorio**: uma nota em `Reference/`, e o resultado para o agendador.

Medido no primeiro sonho sobre o vault real (14 notas de 20 a 26/09, 40
pares): 15 sem relacao, 13 complementos, 12 atualizacoes, das quais 3 com
citacao inventada ou costurada e 9 conferidas. Ver ENRIQUECIMENTO.md.

`sonho_enabled` e `recordacao_enabled` desligam cada metade.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from .sonho import RegistroDeRecordacao
from .sonho import contradicao

logger = logging.getLogger("sonho_vault")

_REGISTRO: dict[str, RegistroDeRecordacao] = {}

CONFIRMACAO = """You check one finding from an automatic review of a personal notes vault.
Statement B is from an older note, statement A from a newer note.
Answer with a single JSON object and nothing else:
{"same_subject": true|false, "a_replaces_or_contradicts_b": true|false}
"same_subject" is true only if both statements are about the same specific thing (the same setting, decision, file, number or plan), not merely the same project."""


# ── recordacao ──────────────────────────────────────────────────────────────

def registro(cfg) -> RegistroDeRecordacao | None:
    if not getattr(cfg, "recordacao_enabled", True):
        return None
    from .config import CONFIG_DIR

    caminho = str(Path(getattr(cfg, "recordacao_path", "") or CONFIG_DIR / "recordacao.sqlite3"))
    if caminho not in _REGISTRO:
        _REGISTRO[caminho] = RegistroDeRecordacao(caminho)
    return _REGISTRO[caminho]


def lembrar(cfg, consulta: str, hits: list[dict], confianca: str = "", melhor: float | None = None) -> None:
    """Chamado pelo search_vault. Nunca levanta: registrar nao pode derrubar a busca."""
    try:
        r = registro(cfg)
        if r is not None:
            r.registrar(consulta, [h.get("path", "") for h in hits], confianca, melhor)
    except Exception as e:  # noqa: BLE001
        logger.warning("recordacao nao registrou: %s", e)


def abriu(cfg, caminho: str) -> None:
    """Chamado pelo read_note. Nunca levanta."""
    try:
        r = registro(cfg)
        if r is not None:
            r.registrar_abertura(caminho)
    except Exception as e:  # noqa: BLE001
        logger.warning("abertura nao registrada: %s", e)


_ACHADOS: dict = {}


def achados(cfg):
    """O registro de achados do sonho (sonho/achados.py), ou None se o sonho estiver desligado."""
    if not getattr(cfg, "sonho_enabled", True):
        return None
    from .config import CONFIG_DIR
    from .sonho import RegistroDeAchados

    caminho = str(Path(getattr(cfg, "achados_path", "") or CONFIG_DIR / "achados.sqlite3"))
    if caminho not in _ACHADOS:
        _ACHADOS[caminho] = RegistroDeAchados(caminho)
    return _ACHADOS[caminho]


def marcar_superadas(cfg, hits: list[dict]) -> None:
    """Poe `superseded_by` nos acertos que um achado do sonho diz terem sido atualizados. Nunca levanta."""
    try:
        reg = achados(cfg)
        if reg is None or not hits:
            return
        por = reg.sobre([h.get("path", "") for h in hits if h.get("path")])
        for h in hits:
            if h.get("path") in por:
                h["superseded_by"] = por[h["path"]]
    except Exception as e:  # noqa: BLE001
        logger.warning("marcacao de nota superada falhou: %s", e)


# ── o sonho ─────────────────────────────────────────────────────────────────



def _elegivel(rel: str, cabeca: str) -> bool:
    nome = Path(rel).name.lower()
    # A nota do proprio sonho sai pela marca no frontmatter, e nao pelo nome: o
    # nome ganha prefixo de data (Reference/2026-09-27-Sonho de...), e a
    # primeira versao, que testava rel.startswith("Reference/Sonho"), nunca
    # casava. O sonho de cada noite teria comparado o relatorio da anterior.
    # Vale para toda nota gerada por sistema (sonho, boletim), por `gerado_por:`.
    return ("transcript" not in nome and "transcricao" not in nome and "/graphs/" not in f"/{rel}"
            and "graph_build" not in cabeca and "gerado_por:" not in cabeca)


from .facetas import data_da_nota  # noqa: E402  (a mesma data para sonho e busca)


def notas_recentes(cfg, dias: float, limite: int) -> list[str]:
    from .listagem_vault import notas_do_vault

    raiz = Path(cfg.vault)
    corte = datetime.fromtimestamp(time.time() - dias * 86400).strftime("%Y-%m-%d")
    saida = []
    for rel in notas_do_vault(cfg):
        p = raiz / rel
        try:
            m = p.stat().st_mtime
            with p.open(encoding="utf-8", errors="ignore") as f:
                cabeca = f.read(600)
        except OSError:
            continue
        d = data_da_nota(rel, cabeca, m)
        if d >= corte and _elegivel(rel, cabeca):
            saida.append((d, m, rel))
    saida.sort(reverse=True)
    return [r for _, _, r in saida[:limite]]


def _confirmar(perguntar, v, titulo_a: str, titulo_b: str) -> bool:
    bruto = perguntar(CONFIRMACAO, f'Statement B (older note "{titulo_b}"): {v.citacao_b}\n\n'
                                   f'Statement A (newer note "{titulo_a}"): {v.citacao_a}')
    d = contradicao._primeiro_json(bruto) or {}
    return d.get("same_subject") is True and d.get("a_replaces_or_contradicts_b") is True


def sonhar(vault, perguntar, dias: float = 2.0, vizinhos: int = 3, limite_notas: int = 30) -> dict:
    """Roda o sonho. `perguntar(system, prompt) -> str` e o modelo local, injetado."""
    from .busca_hibrida import ler_nota

    cfg = vault.cfg
    raiz = Path(cfg.vault)
    t0 = time.monotonic()
    recentes = notas_recentes(cfg, dias, limite_notas)
    pares = julgados = 0
    achados_lista, descartados = [], []
    for rel in recentes:
        try:
            ta, ca = ler_nota(raiz / rel)
        except OSError:
            continue
        with (raiz / rel).open(encoding="utf-8", errors="ignore") as f:
            data_a = data_da_nota(rel, f.read(600), (raiz / rel).stat().st_mtime)
        candidatos = vault.search(f"{ta} {ca[:400]}", limit=12, scope="notes", snippet_chars=0)
        antigos = []
        for h in candidatos:
            if "error" in h:
                break
            b = h.get("path", "")
            if not b or b == rel:
                continue
            try:
                mb = (raiz / b).stat().st_mtime
                with (raiz / b).open(encoding="utf-8", errors="ignore") as f:
                    cabeca_b = f.read(600)
            except OSError:
                continue
            data_b = data_da_nota(b, cabeca_b, mb)
            if _elegivel(b, cabeca_b) and data_b < data_a:
                antigos.append((b, data_b))
            if len(antigos) >= vizinhos:
                break
        for b, data_b in antigos:
            pares += 1
            tb, cb = ler_nota(raiz / b)
            try:
                v = contradicao.julgar(perguntar, ta, data_a, f"{ta}\n{ca}", tb, data_b, f"{tb}\n{cb}")
            except Exception as e:  # noqa: BLE001
                descartados.append({"a": rel, "b": b, "motivo": f"modelo falhou: {e}"})
                continue
            julgados += 1
            item = {"a": rel, "b": b, "relacao": v.relacao, "citacao_a": v.citacao_a,
                    "citacao_b": v.citacao_b, "confianca": v.confianca}
            if not v.achado:
                if v.relacao in contradicao.ACHADOS:
                    descartados.append({**item, "motivo": "; ".join(v.problemas)})
                continue
            try:
                ok = _confirmar(perguntar, v, ta, tb)
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                achados_lista.append(item)
                try:
                    reg = achados(cfg)
                    if reg is not None:
                        # o descarte humano anterior vence: registrar nao reabre
                        reg.registrar(b, rel, v.relacao, v.citacao_b, v.citacao_a)
                except Exception as e:  # noqa: BLE001
                    logger.warning("achado nao registrado: %s", e)
            else:
                descartados.append({**item, "motivo": "nao confirmado na segunda pergunta"})

    lembr, lacunas, estat = [], [], {}
    reg = registro(cfg)
    if reg is not None:
        semana = time.time() - 7 * 86400
        lembr = reg.mais_lembradas(desde=semana, limite=10)
        lacunas = reg.lacunas(desde=semana)[:10]
        estat = reg.estatisticas()
    return {"notas_recentes": len(recentes), "pares": pares, "julgados": julgados,
            "achados": achados_lista, "descartados": descartados, "mais_lembradas": lembr,
            "lacunas": lacunas, "recordacao": estat, "segundos": round(time.monotonic() - t0, 1)}


def relatorio(r: dict, hoje: str) -> tuple[str, str]:
    """(titulo, markdown) da nota do sonho. Sem travessao, pela regra de escrita do vault."""
    n = len(r["achados"])
    titulo = f"Sonho de {hoje} - {n} atualizacoes entre notas, {len(r['lacunas'])} lacunas"
    ln = ["---", "gerado_por: sonho", "---", "", "## Resumo", "",
          f"O sonho leu {r['notas_recentes']} notas recentes, comparou {r['pares']} pares com notas mais "
          f"antigas e confirmou {n} casos em que a nota nova atualiza ou contradiz a antiga. "
          f"{len(r['descartados'])} candidatos cairam na conferencia de citacao ou na confirmacao.", ""]
    ln += ["## A nota nova muda o que a antiga diz", ""]
    if not r["achados"]:
        ln.append("Nenhum caso confirmado.")
    for a in r["achados"]:
        ln += [f"- [[{Path(a['a']).stem}]] {a['relacao']} [[{Path(a['b']).stem}]]",
               f"  - antes: \"{a['citacao_b'][:240]}\"",
               f"  - agora: \"{a['citacao_a'][:240]}\""]
    ln += ["", "## Perguntas que se repetem sem boa resposta", ""]
    if not r["lacunas"]:
        ln.append("Nenhuma nesta semana.")
    for l in r["lacunas"]:
        ln.append(f"- {l['consulta']} ({l['vezes']} vezes)")
    ln += ["", "## Notas mais lembradas na semana", ""]
    if not r["mais_lembradas"]:
        ln.append("O registro de recordacao ainda nao tem tres consultas diferentes para nenhuma nota.")
    for m in r["mais_lembradas"]:
        ln.append(f"- [[{Path(m['caminho']).stem}]]: {m['consultas_unicas']} consultas diferentes")
    ln += ["", "## Como foi feito", "",
           f"Modelo local, {r['julgados']} julgamentos, {r['segundos']} s. Cada achado cita as duas notas; "
           "a citacao e conferida no texto e o achado passa por uma segunda pergunta. "
           "Gerado por `sonho_vault.py` no fork do delegation-core."]
    return titulo, "\n".join(ln).replace("—", ",").replace("–", "-")


from .engine import perguntar_local  # noqa: E402,F401  (mora no engine; nome mantido aqui)


def sonhar_e_registrar(vault, dias: float = 2.0, escrever_nota: bool = True, perguntar=None) -> dict:
    """O que a agenda chama: sonha e, se houver o que dizer, escreve a nota do sonho."""
    cfg = vault.cfg
    if not getattr(cfg, "sonho_enabled", True):
        return {"desligado": True}
    if perguntar is None:
        from .engine import modelo_local_liberado, resultado_adiado
        if not modelo_local_liberado(cfg):
            return resultado_adiado()
    r = sonhar(vault, perguntar or perguntar_local(cfg), dias=dias)
    if escrever_nota and (r["achados"] or r["lacunas"]):
        from .notewriter import create_note

        titulo, corpo = relatorio(r, datetime.now().strftime("%Y-%m-%d"))
        nota = create_note(vault, "Reference", titulo, corpo)
        r["nota"] = nota.get("path") or nota.get("error")
    return r
