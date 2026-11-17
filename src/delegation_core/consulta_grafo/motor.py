"""Consultar um grafo de codigo ja construido: achar no, vizinhanca, caminho, subgrafo.

## Por que existe

O delegation-core constroi grafos de codigo (`graph_build`) e ate hoje so
sabia devolver o relatorio e os artigos que o build escreve no vault. Nesta
maquina ha 13 grafos, o maior com 112 mil nos, e nenhum agente conseguia
perguntar a um deles "quem chama isto", "como A chega em B" ou "o que ha em
volta deste conceito". Para isso ele abria arquivo por arquivo.

O graphify, de onde o `graph/` deste projeto descende, responde isso pelo
proprio servidor MCP (`graphify/serve.py`: query_graph, get_neighbors,
shortest_path...). Este modulo traz a capacidade sem trazer o servidor: le o
mesmo `graph.json` e responde em Python puro, sem networkx.

## O que ele sabe que o relatorio nao sabe

- **Direcao**: `calls`, `imports`, `inherits` tem sentido. Vizinhanca separa
  quem chama (entrada) de quem e chamado (saida).
- **Racional**: o build liga docstrings e comentarios ao codigo por arestas
  `rationale_for` (2.178 no grafo do fork). O subgrafo de uma pergunta traz o
  porque junto do que.
- **Trecho**: com a raiz do repositorio, devolve as linhas de codigo de um no,
  porque o rotulo de um racional vem cortado em 80 caracteres.

## Criterio de lego

Recebe o caminho de um `graph.json` (e, opcional, a raiz do codigo). Nao sabe
o que e vault, config, registro de grafos ou MCP. Quem liga isso ao servidor e
uma camada fina no `server.py`.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import unicodedata
from collections import Counter, OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path

#: Relacoes estruturais demais para ajudar a entender codigo: `contains` liga
#: arquivo a tudo que ha nele e explode qualquer vizinhanca.
RELACOES_RUIDOSAS = frozenset({"contains"})

_PALAVRA = re.compile(r"[a-z0-9]+")


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in t if not unicodedata.combining(c)).lower()


def _termos(texto: str) -> list[str]:
    """Quebra camelCase e snake_case: `buildGraph` e `build_graph` viram build, graph."""
    t = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", texto or "")
    return [p for p in _PALAVRA.findall(_normalizar(t)) if len(p) > 1]


@dataclass
class Aresta:
    outro: str
    relacao: str
    confianca: str


@dataclass
class Grafo:
    nos: dict[str, dict]
    saida: dict[str, list[Aresta]] = field(default_factory=dict)
    entrada: dict[str, list[Aresta]] = field(default_factory=dict)
    raiz_codigo: Path | None = None
    _idf: dict[str, float] = field(default_factory=dict)
    _por_termo: dict[str, list[str]] = field(default_factory=dict)

    # ── construcao ─────────────────────────────────────────────────────────

    @classmethod
    def de_dados(cls, dados: dict, raiz_codigo: str | Path | None = None) -> "Grafo":
        nos = {n["id"]: n for n in dados.get("nodes", []) if "id" in n}
        g = cls(nos=nos, raiz_codigo=Path(raiz_codigo) if raiz_codigo else None)
        for no in nos:
            g.saida[no] = []
            g.entrada[no] = []
        for ln in dados.get("links") or dados.get("edges") or []:
            a, b = ln.get("_src", ln.get("source")), ln.get("_tgt", ln.get("target"))
            if a not in nos or b not in nos:
                continue
            rel = ln.get("relation", "") or ""
            conf = ln.get("confidence", "") or ""
            g.saida[a].append(Aresta(b, rel, conf))
            g.entrada[b].append(Aresta(a, rel, conf))
        g._indexar()
        return g

    def _indexar(self) -> None:
        df: Counter = Counter()
        for nid, n in self.nos.items():
            termos = set(_termos(n.get("label", ""))) | set(_termos(nid))
            for t in termos:
                df[t] += 1
                self._por_termo.setdefault(t, []).append(nid)
        total = max(len(self.nos), 1)
        self._idf = {t: math.log(1 + total / c) for t, c in df.items()}

    # ── leitura basica ─────────────────────────────────────────────────────

    def grau(self, nid: str, sem_ruido: bool = True) -> int:
        arestas = self.saida.get(nid, []) + self.entrada.get(nid, [])
        if sem_ruido:
            arestas = [a for a in arestas if a.relacao not in RELACOES_RUIDOSAS]
        return len(arestas)

    def descrever(self, nid: str) -> dict:
        n = self.nos[nid]
        return {
            "id": nid,
            "rotulo": n.get("label", nid),
            "tipo": n.get("file_type", ""),
            "arquivo": n.get("source_file", ""),
            "local": n.get("source_location", ""),
            "comunidade": n.get("community_name") or n.get("community"),
            "grau": self.grau(nid),
        }

    def estatisticas(self, topo: int = 10) -> dict:
        rel: Counter = Counter()
        for arestas in self.saida.values():
            rel.update(a.relacao for a in arestas)
        tipos = Counter(n.get("file_type", "") for n in self.nos.values())
        comunidades = {n.get("community") for n in self.nos.values() if n.get("community") is not None}
        codigo = [nid for nid, n in self.nos.items() if n.get("file_type") != "rationale"]
        centrais = sorted(codigo, key=lambda x: (-self.grau(x), x))[:topo]
        return {
            "nos": len(self.nos),
            "arestas": sum(rel.values()),
            "comunidades": len(comunidades),
            "relacoes": dict(rel.most_common()),
            "tipos": dict(tipos.most_common()),
            "centrais": [self.descrever(c) for c in centrais],
        }

    # ── achar ──────────────────────────────────────────────────────────────

    def achar(self, termo: str, limite: int = 10, incluir_racional: bool = False) -> list[tuple[str, float]]:
        """Nos cujo rotulo ou id melhor casam com o termo, do melhor ao pior.

        Rotulo identico vence tudo; depois, a soma do IDF dos termos em comum,
        dividida pelo numero de termos do rotulo. Dividir pela raiz, a primeira
        versao, ainda deixava nome de teste vencer: `test_carimbo_faz_o_reindex_
        pular` tem oito termos e casa com metade de qualquer pergunta sobre
        carimbo, e dominou as sementes na primeira medicao contra o grafo do
        fork. Pela mesma razao, no de arquivo de teste vale 0,3 do que valeria,
        a nao ser que a pergunta fale de teste.

        Nos de racional ficam de fora por padrao: eles explicam codigo, nao sao
        o codigo que alguem procura pelo nome.
        """
        alvo = _normalizar(termo).strip()
        termos = _termos(termo)
        if not alvo:
            return []
        pontos: dict[str, float] = {}
        for t in termos:
            for nid in self._por_termo.get(t, []):
                pontos[nid] = pontos.get(nid, 0.0) + self._idf.get(t, 0.0)
        quer_teste = any(t.startswith("test") for t in termos)
        saida = []
        for nid, p in pontos.items():
            n = self.nos[nid]
            if not incluir_racional and n.get("file_type") == "rationale":
                continue
            rotulo = _normalizar(n.get("label", ""))
            base = rotulo.rsplit(".", 1)[0] if rotulo.endswith((".py", ".ts", ".go", ".rs", ".js")) else rotulo
            # identico por termos, e nao por cadeia: "gravar indice" digitado e o
            # rotulo `gravar_indice()` sao o mesmo nome. A comparacao por cadeia,
            # a primeira versao, nunca casava pergunta com espaco.
            if rotulo == alvo or base == alvo or _termos(n.get("label", "")) == termos:
                p += 1000.0
            elif alvo in rotulo:
                p += 10.0
            p /= max(len(_termos(rotulo)), 1)
            if not quer_teste and _e_teste(n.get("source_file", "")):
                p *= 0.3
            saida.append((nid, p))
        saida.sort(key=lambda x: (-x[1], -self.grau(x[0]), x[0]))
        return saida[:limite]

    def resolver(self, termo: str) -> str | None:
        """Um id: o proprio, se existir; senao o melhor achado."""
        if termo in self.nos:
            return termo
        achados = self.achar(termo, limite=1)
        return achados[0][0] if achados else None

    # ── vizinhanca e caminho ───────────────────────────────────────────────

    def vizinhos(self, nid: str, direcao: str = "ambas", relacoes: set[str] | None = None,
                 limite: int = 40, incluir_ruido: bool = False) -> dict:
        def filtrar(arestas):
            out = []
            for a in arestas:
                if relacoes and a.relacao not in relacoes:
                    continue
                if not relacoes and not incluir_ruido and a.relacao in RELACOES_RUIDOSAS:
                    continue
                out.append({"relacao": a.relacao, "confianca": a.confianca, **self.descrever(a.outro)})
            out.sort(key=lambda d: (d["relacao"], -d["grau"], d["id"]))
            return out[:limite]
        r = {"no": self.descrever(nid)}
        if direcao in ("ambas", "saida"):
            r["saida"] = filtrar(self.saida.get(nid, []))
        if direcao in ("ambas", "entrada"):
            r["entrada"] = filtrar(self.entrada.get(nid, []))
        return r

    def caminho(self, origem: str, destino: str, max_nos: int = 200_000) -> dict:
        """Caminho mais curto seguindo a direcao das arestas; sem ele, ignorando a direcao.

        `contains` fica de fora: todo par de nos do mesmo arquivo se liga por
        ele em dois passos, e esse caminho nao ensina nada.
        """
        for dirigido in (True, False):
            trilha = self._bfs_caminho(origem, destino, dirigido, max_nos)
            if trilha is not None:
                passos = []
                for (a, rel, sentido), b in zip(trilha, [t[0] for t in trilha[1:]] + [destino]):
                    passos.append({"de": self.descrever(a)["rotulo"], "relacao": rel,
                                   "sentido": sentido, "para": self.descrever(b)["rotulo"]})
                return {"achado": True, "respeita_direcao": dirigido, "tamanho": len(passos),
                        "nos": [self.descrever(t[0]) for t in trilha] + [self.descrever(destino)],
                        "passos": passos}
        return {"achado": False}

    def _bfs_caminho(self, origem, destino, dirigido, max_nos):
        if origem == destino:
            return []
        anterior: dict[str, tuple[str, str, str]] = {origem: ("", "", "")}
        fila = deque([origem])
        while fila and len(anterior) < max_nos:
            atual = fila.popleft()
            candidatos = [(a, "->") for a in self.saida.get(atual, [])]
            if not dirigido:
                candidatos += [(a, "<-") for a in self.entrada.get(atual, [])]
            for a, sentido in candidatos:
                if a.relacao in RELACOES_RUIDOSAS or a.outro in anterior:
                    continue
                anterior[a.outro] = (atual, a.relacao, sentido)
                if a.outro == destino:
                    trilha = []
                    no = destino
                    while no != origem:
                        pai, rel, s = anterior[no]
                        trilha.append((pai, rel, s))
                        no = pai
                    return list(reversed(trilha))
                fila.append(a.outro)
        return None

    # ── subgrafo de uma pergunta ───────────────────────────────────────────

    def subgrafo(self, pergunta: str, profundidade: int = 2, sementes: int = 3,
                 leque: int = 8, orcamento: int = 6000) -> dict:
        """O entorno das sementes que a pergunta aponta, em texto pronto para ler.

        As sementes sao os melhores nos para a pergunta inteira e para cada
        termo raro dela, o que acha `rrf` numa pergunta como "onde a fusao usa
        rrf". A expansao anda `profundidade` saltos pelos dois sentidos, com no
        maximo `leque` vizinhos por no (os de maior grau), porque um no central
        tem centenas. Racionais ligados a qualquer no do subgrafo entram junto.
        """
        escolhidas: list[str] = []
        for nid, _ in self.achar(pergunta, limite=sementes):
            if nid not in escolhidas:
                escolhidas.append(nid)
        raros = sorted(set(_termos(pergunta)), key=lambda t: -self._idf.get(t, 0))
        for t in raros[:sementes]:
            for nid, _ in self.achar(t, limite=1):
                if nid not in escolhidas and len(escolhidas) < sementes * 2:
                    escolhidas.append(nid)
        if not escolhidas:
            return {"sementes": [], "texto": "", "nos": 0}

        vistos = set(escolhidas)
        arestas: list[tuple[str, str, str]] = []
        fronteira = list(escolhidas)
        for _ in range(profundidade):
            proxima = []
            for nid in fronteira:
                cand = [(nid, a.relacao, a.outro) for a in self.saida.get(nid, [])
                        if a.relacao not in RELACOES_RUIDOSAS and a.relacao != "rationale_for"]
                cand += [(a.outro, a.relacao, nid) for a in self.entrada.get(nid, [])
                         if a.relacao not in RELACOES_RUIDOSAS and a.relacao != "rationale_for"]
                cand.sort(key=lambda e: -self.grau(e[2] if e[0] == nid else e[0]))
                for e in cand[:leque]:
                    arestas.append(e)
                    outro = e[2] if e[0] == nid else e[0]
                    if outro not in vistos:
                        vistos.add(outro)
                        proxima.append(outro)
            fronteira = proxima

        racionais = []
        for nid in list(vistos):
            for a in self.entrada.get(nid, []):
                if a.relacao == "rationale_for":
                    racionais.append((nid, a.outro))

        rot = lambda x: self.nos[x].get("label", x)  # noqa: E731
        linhas = ["# sementes"]
        for s in escolhidas:
            d = self.descrever(s)
            linhas.append(f"- {d['rotulo']}  [{d['arquivo']}:{d['local']}]")
        linhas.append("# relacoes")
        for a, rel, b in dict.fromkeys(arestas):
            linhas.append(f"- {rot(a)} --{rel}--> {rot(b)}")
        if racionais:
            linhas.append("# por que (docstrings e comentarios)")
            for alvo, r in racionais:
                linhas.append(f"- {rot(alvo)}: {rot(r)}")
        texto, cortado = _cortar("\n".join(linhas), orcamento)
        return {"sementes": [self.descrever(s) for s in escolhidas], "nos": len(vistos),
                "arestas": len(set(arestas)), "cortado": cortado, "texto": texto}

    # ── trecho de codigo ───────────────────────────────────────────────────

    def trecho(self, nid: str, linhas: int = 30) -> dict:
        """As linhas do arquivo a partir do local do no, se a raiz do codigo for conhecida."""
        d = self.descrever(nid)
        if not self.raiz_codigo or not d["arquivo"]:
            return {**d, "trecho": None, "motivo": "raiz do codigo desconhecida"}
        m = re.match(r"L(\d+)", str(d["local"] or ""))
        inicio = int(m.group(1)) if m else 1
        arq = (self.raiz_codigo / d["arquivo"]).resolve()
        if self.raiz_codigo.resolve() not in arq.parents:
            return {**d, "trecho": None, "motivo": "arquivo fora da raiz"}
        try:
            todas = arq.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as e:
            return {**d, "trecho": None, "motivo": f"nao li o arquivo: {e.strerror}"}
        fim = min(len(todas), inicio - 1 + linhas)
        return {**d, "inicio": inicio, "fim": fim,
                "trecho": "\n".join(todas[inicio - 1:fim])}


def _e_teste(arquivo: str) -> bool:
    a = arquivo.replace("\\", "/").lower()
    nome = a.rsplit("/", 1)[-1]
    return ("/tests/" in f"/{a}" or "/test/" in f"/{a}" or nome.startswith("test_")
            or nome.endswith(("_test.py", "_test.go", ".test.ts", ".spec.ts", ".test.js")))


def _cortar(texto: str, orcamento: int) -> tuple[str, bool]:
    if len(texto) <= orcamento:
        return texto, False
    corte = texto.rfind("\n", 0, orcamento)
    return texto[: corte if corte > 0 else orcamento] + "\n... (cortado pelo orcamento)", True


# ── carga com cache ──────────────────────────────────────────────────────────

_CACHE: "OrderedDict[tuple, Grafo]" = OrderedDict()
_TRAVA = threading.Lock()
#: Grafos grandes custam memoria: o de 160 MB em disco vira alguns GB em dict.
#: Dois cabem; o terceiro despeja o mais antigo.
MAX_EM_MEMORIA = int(os.environ.get("DC_GRAFOS_EM_MEMORIA", "2"))


def carregar(caminho_json: str | Path, raiz_codigo: str | Path | None = None) -> Grafo:
    """Carrega (ou devolve do cache) o grafo, invalidando quando o arquivo muda."""
    p = Path(caminho_json)
    st = p.stat()
    chave = (str(p.resolve()), st.st_mtime_ns, st.st_size, str(raiz_codigo or ""))
    with _TRAVA:
        if chave in _CACHE:
            _CACHE.move_to_end(chave)
            return _CACHE[chave]
    with p.open(encoding="utf-8") as f:
        g = Grafo.de_dados(json.load(f), raiz_codigo)
    with _TRAVA:
        for velha in [k for k in _CACHE if k[0] == chave[0]]:
            del _CACHE[velha]
        _CACHE[chave] = g
        while len(_CACHE) > MAX_EM_MEMORIA:
            _CACHE.popitem(last=False)
    return g
