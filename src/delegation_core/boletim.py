"""Boletim diario: o que aconteceu no sistema desde o ultimo, numa nota so.

## Por que existe

Os sistemas de 27/09 produzem sinal a noite toda: o historico sabe que notas
mudaram e por qual operacao, os alertas abrem e fecham, o sonho acha nota nova
revogando antiga, a recordacao acha pergunta sem resposta, a agenda sabe o que
falhou. Cada um tem sua ferramenta, e ninguem abre sete ferramentas de manha.

O boletim junta tudo numa nota em `Sessions/`, deterministica (sem modelo),
e so escreve se houver o que dizer. Roda pela agenda as 07:13.

## Criterio de lego

Le o que os outros sistemas ja gravaram, por funcoes injetaveis. Se um deles
estiver desligado, a secao dele some; o boletim nao depende de nenhum.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from .arquivos_json import ler_json


def _json(caminho: Path) -> dict:
    return ler_json(caminho, dict)


def coletar(cfg, config_dir: Path, desde: float, tracker=None) -> dict:
    """Os fatos do periodo, por sistema. Cada chave falta se o sistema estiver desligado."""
    fatos: dict = {"desde": desde}

    try:
        from .historico_vault import abrir
        h = abrir(cfg)
        if h is not None:
            mud = [m for m in h.mudancas_desde(desde, limite=50_000) if "Boletim de " not in m["caminho"]]
            # Visto no boletim de teste sobre a copia do vault real: "500 notas
            # mudaram" no dia em que o historico fotografou o vault pela primeira
            # vez. Primeira foto de nota antiga e linha de base, nao mudanca; nota
            # nova de verdade (data no nome dentro da janela) continua contando.
            from .facetas import data_da_nota
            corte = datetime.fromtimestamp(desde).strftime("%Y-%m-%d")
            base = [m for m in mud if m["versoes"] == 1 and m.get("primeira", 0) >= desde
                    and data_da_nota(m["caminho"], "", 0) < corte]
            fatos["linha_de_base"] = len(base)
            fatos["mudancas"] = [m for m in mud if m not in base][:500]
    except Exception as e:  # noqa: BLE001
        fatos["erro_historico"] = str(e)

    alertas = _json(config_dir / "alertas.json")
    if alertas:
        fatos["alertas_abertos"] = [a for a in alertas.get("alertas", {}).values() if a.get("estado") == "disparando"]
        fatos["eventos"] = [e for e in alertas.get("eventos", []) if e.get("em", 0) >= desde]

    agenda = _json(config_dir / "agenda.json")
    if agenda:
        fatos["tarefas_falhando"] = {n: e.get("ultimo_erro", "") for n, e in agenda.items()
                                     if int(e.get("falhas_seguidas", 0)) >= 1}
        fatos["tarefas_rodadas"] = sorted(n for n, e in agenda.items()
                                          if e.get("ultima_execucao") and
                                          datetime.fromisoformat(e["ultima_execucao"]).timestamp() >= desde)

    try:
        from .sonho_vault import registro
        r = registro(cfg)
        if r is not None:
            fatos["lacunas"] = r.lacunas(desde=desde)[:10]
            fatos["consultas"] = r.estatisticas()
    except Exception as e:  # noqa: BLE001
        fatos["erro_recordacao"] = str(e)

    raiz = Path(cfg.vault)
    sonhos = []
    for p in (raiz / "Reference").glob("*Sonho de *.md") if (raiz / "Reference").is_dir() else []:
        try:
            if p.stat().st_mtime >= desde:
                sonhos.append(str(p.relative_to(raiz)))
        except OSError:
            continue
    fatos["sonhos"] = sorted(sonhos)

    if tracker is not None:
        dias = int(getattr(cfg, "alerta_processo_parado_dias", 14))
        parados = []
        for pr in tracker.list_processes(status="active"):
            try:
                idade = (datetime.now() - datetime.fromisoformat(pr["updated"])).days
            except (KeyError, ValueError):
                continue
            if idade >= dias:
                parados.append({"nome": pr["name"], "dias": idade})
        fatos["processos_parados"] = parados
    return fatos


def tem_o_que_dizer(f: dict) -> bool:
    return bool(f.get("mudancas") or f.get("alertas_abertos") or f.get("eventos") or f.get("tarefas_falhando")
                or f.get("lacunas") or f.get("sonhos"))


def _origem_curta(o: str) -> str:
    o = (o or "").strip()
    return "manual ou externo" if o in ("varredura", "agenda", "") else o


def redigir(f: dict, hoje: str) -> tuple[str, str]:
    """(titulo, markdown). Sem travessao: e regra de escrita do vault."""
    mud = f.get("mudancas") or []
    abertos = f.get("alertas_abertos") or []
    titulo = (f"Boletim de {hoje} - {len(mud)} notas mudaram, {len(abertos)} alertas abertos")
    ln = ["---", "gerado_por: boletim", "type: session", "---", "", "## Resumo", ""]
    desde_txt = datetime.fromtimestamp(f["desde"]).strftime("%d/%m %H:%M")
    partes = [f"{len(mud)} notas mudaram desde {desde_txt}"]
    if f.get("linha_de_base"):
        partes.append(f"{f['linha_de_base']} notas antigas entraram no historico pela primeira vez (linha de base, nao mudanca)")
    if abertos:
        partes.append(f"{len(abertos)} alertas abertos")
    if f.get("tarefas_falhando"):
        partes.append(f"{len(f['tarefas_falhando'])} tarefas agendadas com falha")
    if f.get("sonhos"):
        partes.append("o sonho escreveu relatorio")
    if f.get("lacunas"):
        partes.append(f"{len(f['lacunas'])} perguntas sem boa resposta")
    ln += ["; ".join(partes) + ".", ""]

    if abertos:
        ln += ["## Alertas abertos", ""]
        for a in abertos:
            ln.append(f"- [{a.get('severidade', '')}] {a.get('mensagem', '')}")
        ln.append("")
    if f.get("tarefas_falhando"):
        ln += ["## Tarefas agendadas com falha", ""]
        for n, e in f["tarefas_falhando"].items():
            ln.append(f"- {n}: {e[:160]}")
        ln.append("")
    if f.get("sonhos"):
        ln += ["## Sonho", ""]
        for s in f["sonhos"]:
            ln.append(f"- [[{Path(s).stem}]]")
        ln.append("")
    if mud:
        por_origem: dict[str, list] = {}
        for m in mud:
            chave = ", ".join(sorted({_origem_curta(o) for o in m.get("origens", [])})) or "manual ou externo"
            por_origem.setdefault(chave, []).append(m["caminho"])
        ln += ["## Notas que mudaram, por origem", ""]
        for origem, caminhos in sorted(por_origem.items(), key=lambda kv: -len(kv[1])):
            ln.append(f"- {origem}: {len(caminhos)}")
            for c in caminhos[:8]:
                ln.append(f"  - [[{Path(c).stem}]]")
            if len(caminhos) > 8:
                ln.append(f"  - e mais {len(caminhos) - 8}")
        ln.append("")
    if f.get("lacunas"):
        ln += ["## Perguntas que se repetem sem boa resposta", ""]
        for l in f["lacunas"]:
            ln.append(f"- {l['consulta']} ({l['vezes']} vezes)")
        ln.append("")
    if f.get("processos_parados"):
        ln += ["## Processos ativos sem atualizacao", ""]
        for pr in f["processos_parados"]:
            ln.append(f"- {pr['nome']} ({pr['dias']} dias)")
        ln.append("")
    texto = "\n".join(ln).replace("—", ",").replace("–", "-")
    return titulo, texto


def gerar(vault, config_dir: Path, tracker=None, horas: float = 24.0, escrever: bool = True) -> dict:
    """O que a agenda chama. Escreve a nota so se houver o que dizer."""
    desde = time.time() - horas * 3600
    fatos = coletar(vault.cfg, Path(config_dir), desde, tracker)
    r = {"notas_mudadas": len(fatos.get("mudancas") or []), "alertas_abertos": len(fatos.get("alertas_abertos") or []),
         "sonhos": len(fatos.get("sonhos") or []), "lacunas": len(fatos.get("lacunas") or [])}
    if escrever and tem_o_que_dizer(fatos):
        from .notewriter import create_note
        titulo, corpo = redigir(fatos, datetime.now().strftime("%Y-%m-%d"))
        nota = create_note(vault, "Sessions", titulo, corpo)
        r["nota"] = nota.get("path") or nota.get("error")
    return r
