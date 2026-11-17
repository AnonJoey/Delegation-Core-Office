"""Liga o pacote `digestao` ao vault: quais transcricoes resumir, e onde o resumo vai.

Resume so transcricao bruta de dia sem NENHUMA sessao curada (ou sem data no
nome), que e onde o bruto e o unico registro: 60 + 18 em 27/09. Da mais nova
para a mais antiga, no maximo `maximo` por execucao, para o modelo local nao
passar a noite inteira nisso. O resumo vai para `Sessions/` com
`gerado_por: digestao` (o sonho nao o compara) e `digere: <transcricao>`, que e
como a proxima execucao sabe que aquela ja foi feita.

Medido numa transcricao real de 35 KB (Palworld, 18/06): 4 pedacos, 61 s,
nenhuma citacao sem lastro, e o conteudo bate com a correcao registrada na
memoria. O primeiro teste cortou o resumo no meio por falta de tokens: a etapa
de reduzir precisa de ~1.200, e nao dos 400 do sonho.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_BRUTA = re.compile(r"transcript|transcri[cç][aã]o", re.IGNORECASE)
_DATA = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DIGERE = re.compile(r"^digere:\s*[\"']?(.+?)[\"']?\s*$", re.M)
_TITULO = re.compile(r"^title:\s*[\"']?(.*?)[\"']?\s*$", re.M)
_PARTE = re.compile(r"^(.+)-parte-\d+$")


def _sem_travessao(texto: str) -> str:
    """Travessao e meia-risca viram hifen. O titulo vem da transcricao e ia direto para o nome do arquivo
    e para o frontmatter; so o corpo era limpo."""
    return re.sub(r"(?:\s*-\s*)?\s*[\u2014\u2013]\s*(?:-\s*)?", " - ", texto).strip()


def _arquivo_de_vazias(cfg) -> Path:
    return Path(cfg.vault) / ".digestao" / "vazias.json"


def _assinatura(p: Path) -> str:
    st = p.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def _vazias_conhecidas(cfg) -> dict:
    """Notas em que o modelo nao achou o que resumir: {nome: tamanho:mtime}. Mudou o arquivo, volta a ser tentada."""
    try:
        dados = json.loads(_arquivo_de_vazias(cfg).read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _lembrar_vazias(cfg, vazias: dict) -> None:
    arq = _arquivo_de_vazias(cfg)
    try:
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_name(arq.name + ".tmp")
        tmp.write_text(json.dumps(vazias, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(arq)
    except OSError:
        pass  # perder a lista custa uma chamada rapida por nota na proxima noite; nao derruba o job


def _sessoes(cfg) -> Path:
    for pasta in getattr(cfg, "vault_folders", []) or []:
        if pasta.lower() == "sessions":
            return Path(cfg.vault) / pasta
    return Path(cfg.vault) / "Sessions"


def pendentes(cfg) -> list[Path]:
    base = _sessoes(cfg)
    if not base.is_dir():
        return []
    notas = [p for p in base.iterdir() if p.suffix == ".md" and p.is_file()]
    brutas, curadas = [], []
    dias_curados = set()
    ja_digeridas = set()
    for p in notas:
        try:
            cab = p.open(encoding="utf-8", errors="ignore").read(800)
        except OSError:
            continue
        # Resumo se reconhece pelo cabecalho, nunca pelo nome. O nome do resumo herda o titulo da
        # transcricao ("Resumo da sessao - Session Transcript ..."), casa com _BRUTA e, tomado por
        # transcricao, era resumido de novo (resumo de resumo) enquanto a original seguia pendente:
        # tres resumos da mesma transcricao e dois de resumo, medidos em 2026-11-04.
        m = _DIGERE.search(cab)
        if m:
            ja_digeridas.add(m.group(1).strip())
            continue  # resumo gerado nao e transcricao nem conta como sessao curada do dia
        if _BRUTA.search(p.name):
            brutas.append(p)
            continue
        curadas.append(p)
        d = _DATA.match(p.name)
        if d:
            dias_curados.add(d.group(1))
    # Nota-indice de reuniao dividida (`<nome>` com links para `<nome>-parte-N`): a fala esta nas
    # partes, que ja estao na fila. Medido em 2026-11-04: eram as cinco da frente, sempre vazias.
    indices = {m.group(1) for p in brutas if (m := _PARTE.match(p.stem))}
    vazias = _vazias_conhecidas(cfg)
    saida = []
    for p in brutas:
        if p.stem in ja_digeridas or p.stem in indices:
            continue
        try:
            if vazias.get(p.name) == _assinatura(p):
                continue
        except OSError:
            continue
        d = _DATA.match(p.name)
        if d and d.group(1) in dias_curados:
            continue
        saida.append(p)
    saida.sort(key=lambda p: (_DATA.match(p.name).group(1) if _DATA.match(p.name) else "", p.stat().st_mtime),
               reverse=True)
    return saida


_TAG = re.compile(r"<[^>]{1,80}>")
_TURNO_VOCE = re.compile(r"^### You\b[^\n]*\n+(.*?)(?=^### |\Z)", re.S | re.M)


def _primeira_fala(texto: str) -> str:
    """A primeira fala do usuario que nao e so marcacao do Claude Code."""
    for m in _TURNO_VOCE.finditer(texto):
        corpo = m.group(1).strip()
        if not corpo or corpo.startswith("<"):
            continue
        linha = next((l.strip() for l in corpo.splitlines() if l.strip() and l.strip() != "---"), "")
        linha = re.sub(r"\s+", " ", _TAG.sub(" ", linha)).strip()
        if linha:
            return linha
    return ""


def _assunto(texto: str, stem: str) -> str:
    """Assunto do resumo: o titulo do bruto, ou a primeira fala real se o titulo for marcacao.

    Medido em 27/09: 40 das 75 transcricoes brutas tinham como titulo a
    marcacao `<local-command-caveat>Caveat: ...` que o Claude Code poe antes
    de um comando local, e o primeiro resumo saiu como "Resumo da sessao -
    _local-command-caveat_Caveat".
    """
    m = _TITULO.search(texto[:800])
    t = (m.group(1) if m else "").replace("Raw transcript", "").strip(" -:\u2014\u2013")
    if not t or "<" in t:
        t = _primeira_fala(texto)
    return (t or stem)[:70]


def _gravar(vault, titulo: str, corpo: str, data: str | None) -> dict:
    """Grava com a data DA SESSAO no nome, e nao a de hoje.

    O create_note sempre prefixa a data do dia; um resumo de 18/06 escrito em
    27/09 sairia como nota de 27/09, e as facetas de data e o boletim leem a
    data pelo nome. Visto no primeiro teste: `2026-09-27-Resumo da sessao
    2026-06-18...`. Segredo coberto, indexado e carimbado como no create_note.
    """
    from datetime import datetime
    from .notes import compose_note, safe_filename, unique_note_path
    from .notewriter import _proteger

    cfg = vault.cfg
    dia = data or datetime.now().strftime("%Y-%m-%d")
    pasta = _sessoes(cfg)
    dest = unique_note_path(pasta / f"{dia}-{safe_filename(titulo)}.md")
    texto, _ = _proteger(cfg, compose_note(titulo, corpo, dia))
    try:
        dest.write_text(texto, encoding="utf-8")
    except OSError as e:
        return {"error": f"Write failed: {e}"}
    rel = str(dest.relative_to(cfg.vault))
    if vault.index_note(texto, {"title": titulo, "path": rel, "folder": pasta.name}):
        vault.stamp_indexed([rel])
    return {"status": "ok", "path": rel}


def digerir(vault, maximo: int = 5, perguntar=None) -> dict:
    from .digestao import resumir
    from .engine import perguntar_local

    cfg = vault.cfg
    if not getattr(cfg, "digestao_enabled", True):
        return {"desligado": True}
    fila = pendentes(cfg)
    if perguntar is None:
        from .engine import modelo_local_liberado, resultado_adiado
        if not modelo_local_liberado(cfg):
            return resultado_adiado(len(fila))
    feitos, falhas, vazias = [], [], []
    conhecidas = _vazias_conhecidas(cfg)
    mapa = perguntar or perguntar_local(cfg, max_tokens=500, tarefa="digestao")
    reduzir = perguntar or perguntar_local(cfg, max_tokens=1200, tarefa="digestao")

    def pergunta(system, prompt):
        from .digestao.resumo import REDUZIR
        return (reduzir if system == REDUZIR else mapa)(system, prompt)

    # So feito e erro real gastam a cota de `maximo`. Nota sem o que resumir custa uma resposta
    # curta do modelo e fica lembrada; o teto de tentativas evita que uma fila toda de vazias
    # prenda a execucao.
    for tentativa, p in enumerate(fila):
        if len(feitos) + len(falhas) >= maximo or tentativa >= maximo * 5:
            break
        try:
            texto = p.read_text(encoding="utf-8", errors="ignore")
            r = resumir(texto, pergunta)
        except Exception as e:  # noqa: BLE001 - uma transcricao ruim nao para a fila
            falhas.append({"transcricao": p.name, "erro": str(e)[:200]})
            continue
        if r["vazio"]:
            vazias.append(p.name)
            try:
                conhecidas[p.name] = _assinatura(p)
            except OSError:
                pass
            continue
        d = _DATA.match(p.name)
        titulo = _sem_travessao(f"Resumo da sessao - {_assunto(texto, p.stem)}")
        rodape = ["## Fonte", "", f"Resumo automatico, pelo modelo local, da transcricao [[{p.stem}]] "
                  f"({r['partes']} partes)."]
        if r["sem_lastro"]:
            rodape.append("Citacoes que nao aparecem na transcricao, a conferir: "
                          + ", ".join(f"`{c}`" for c in r["sem_lastro"][:10]))
        # A troca do travessao e so do texto que o modelo escreveu: aplicada ao corpo inteiro ela
        # adulterava `digere:` e o wikilink de um stem que tivesse travessao, e a transcricao voltava
        # a ser resumida.
        resumo = r["resumo"].replace(chr(0x2014), ",").replace(chr(0x2013), "-")
        corpo = ("---\ngerado_por: digestao\ntype: session\n"
                 f"digere: {p.stem}\n---\n\n" + resumo + "\n\n" + "\n".join(rodape) + "\n")
        nota = _gravar(vault, titulo, corpo, d.group(1) if d else None)
        feitos.append({"transcricao": p.name, "resumo": nota.get("path") or nota.get("error"),
                       "partes": r["partes"], "sem_lastro": len(r["sem_lastro"])})
    if vazias:
        _lembrar_vazias(cfg, conhecidas)
    return {"pendentes_antes": len(fila), "feitos": feitos, "falhas": falhas, "vazias": vazias,
            "restam": max(0, len(fila) - len(feitos) - len(falhas) - len(vazias))}
