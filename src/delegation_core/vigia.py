"""Liga a agenda e os alertas ao delegation-core: as acoes, as regras e o laco do daemon.

Os pacotes `agenda` e `alertas` nao sabem o que existe no sistema. Este modulo
sabe, e e o unico que precisa saber: traduz nome de acao em funcao, le o estado
real para as regras, e avisa quando um alerta abre ou fecha.

## As regras embutidas, e o caso real de cada uma

| regra | o que ja aconteceu aqui sem ninguem perceber |
|---|---|
| `indice_atrasado` | 26/09: 284 notas com carimbo desatualizado enquanto a saude dizia `unindexed: 2` |
| `saude_do_vault` | notas para reparar e links quebrados so apareciam se alguem chamasse o heartbeat |
| `agenda_falhando` | nova: sem agenda nao havia o que falhar calado, agora ha |
| `sentinela_esquecida` | `no_auto_reindex` criada em 31/08 e esquecida ate 26/09, 26 dias de reindex desligado |
| `inbox_parado` | arquivo no `_inbox/` que a manutencao nao consegue processar fica la para sempre |
| `processo_parado` | processo ativo sem atualizacao ha semanas (ha tres assim hoje) |
| `disco` | o vault, os grafos e o historico moram no mesmo disco |

`agenda_enabled = false` desliga o laco inteiro; `alertas_desktop = false`
desliga so o aviso na area de trabalho.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from .agenda import Agenda, tarefas_de_config
from .alertas import Disparo, MotorDeAlertas, Regra
from .procs import sem_janela

logger = logging.getLogger("vigia")

TAREFAS_PADRAO = [
    {"nome": "historico-horario", "cron": "17 * * * *", "acao": "historico"},
    {"nome": "alertas", "cron": "*/10 * * * *", "acao": "alertas"},
    {"nome": "reindex-noturno", "cron": "7 4 * * *", "acao": "reindex"},
    {"nome": "podar-historico", "cron": "43 3 * * 0", "acao": "podar_historico",
     "argumentos": {"manter_por_nota": 50}},
    {"nome": "sonho-noturno", "cron": "23 3 * * *", "acao": "sonho", "argumentos": {"dias": 1}},
    {"nome": "boletim-diario", "cron": "13 7 * * *", "acao": "boletim", "argumentos": {"horas": 24}},
    {"nome": "digestao-noturna", "cron": "37 2 * * *", "acao": "digestao", "argumentos": {"maximo": 5}},
    {"nome": "fatos-noturno", "cron": "47 4 * * *", "acao": "fatos", "argumentos": {"maximo": 40}},
]

SENTINELAS = ("no_auto_reindex",)


# ── regras ──────────────────────────────────────────────────────────────────

def _notas_atrasadas(cfg) -> tuple[int, list[str]]:
    from . import notes
    from .listagem_vault import notas_do_vault

    estado = notes.carregar_estado(notes.caminho_do_estado(cfg.vault))
    raiz = Path(cfg.vault)
    atrasadas = []
    for rel in notas_do_vault(cfg):
        try:
            m = (raiz / rel).stat().st_mtime
        except OSError:
            continue
        carimbo = estado.get(rel)
        if carimbo is None or abs(float(carimbo) - m) > 1e-3:
            atrasadas.append(rel)
    return len(atrasadas), atrasadas[:10]


def regra_indice_atrasado(ctx) -> list[Disparo]:
    n, exemplos = _notas_atrasadas(ctx.cfg)
    limite = int(getattr(ctx.cfg, "alerta_indice_atrasado", 100))
    if n <= limite:
        return []
    return [Disparo("vault", f"{n} notas mudaram no disco e nao foram reindexadas",
                    {"notas": n, "exemplos": exemplos, "limite": limite})]


def regra_saude_do_vault(ctx) -> list[Disparo]:
    s = ctx.vault.get_health_summary() or {}
    out = []
    if int(s.get("needs_repair", 0)) > 5:
        out.append(Disparo("needs_repair", f"{s['needs_repair']} notas marcadas para reparo",
                           {"needs_repair": s["needs_repair"]}))
    if int(s.get("broken_links", 0)) > 0:
        out.append(Disparo("broken_links", f"{s['broken_links']} links quebrados",
                           {"broken_links": s["broken_links"]}))
    if int(s.get("malformed_frontmatter", 0)) > 0:
        out.append(Disparo("frontmatter", f"{s['malformed_frontmatter']} notas com frontmatter ilegivel",
                           {"malformed_frontmatter": s["malformed_frontmatter"]}))
    return out


def regra_agenda_falhando(ctx) -> list[Disparo]:
    if ctx.agenda is None:
        return []
    out = []
    for nome in ctx.agenda.tarefas:
        e = ctx.agenda.estado(nome)
        if int(e.get("falhas_seguidas", 0)) >= 2:
            out.append(Disparo(nome, f"a tarefa agendada '{nome}' falhou {e['falhas_seguidas']} vezes seguidas",
                               {"ultimo_erro": e.get("ultimo_erro", "")}))
    return out


def regra_sentinela_esquecida(ctx) -> list[Disparo]:
    out = []
    for nome in SENTINELAS:
        p = Path(ctx.config_dir) / nome
        if p.exists():
            dias = (time.time() - p.stat().st_mtime) / 86400
            out.append(Disparo(nome, f"a sentinela {nome} existe ha {dias:.0f} dias e desliga um comportamento",
                               {"caminho": str(p), "dias": round(dias, 1)}))
    return out


def regra_inbox_parado(ctx) -> list[Disparo]:
    inbox = Path(ctx.cfg.vault) / "_inbox"
    if not inbox.is_dir():
        return []
    velhos = []
    for f in inbox.iterdir():
        if f.is_file() and not f.name.startswith("."):
            idade_h = (time.time() - f.stat().st_mtime) / 3600
            if idade_h > 24:
                velhos.append((f.name, round(idade_h)))
    if not velhos:
        return []
    return [Disparo("_inbox", f"{len(velhos)} arquivos no _inbox ha mais de 24 h",
                    {"arquivos": velhos[:10]})]


def regra_processo_parado(ctx) -> list[Disparo]:
    if ctx.tracker is None:
        return []
    dias = int(getattr(ctx.cfg, "alerta_processo_parado_dias", 14))
    out = []
    for p in ctx.tracker.list_processes(status="active"):
        try:
            atualizado = datetime.fromisoformat(p["updated"])
        except (KeyError, ValueError):
            continue
        idade = (datetime.now() - atualizado).days
        if idade >= dias:
            out.append(Disparo(p["id"], f"processo ativo '{p['name']}' sem atualizacao ha {idade} dias",
                               {"dias": idade}))
    return out


def regra_disco(ctx) -> list[Disparo]:
    uso = shutil.disk_usage(ctx.cfg.vault)
    livre_gb = uso.free / 1e9
    frac = uso.free / uso.total
    if livre_gb < 5 or frac < 0.05:
        return [Disparo(str(ctx.cfg.vault), f"{livre_gb:.1f} GB livres ({frac:.0%}) no disco do vault",
                        {"livre_gb": round(livre_gb, 1)})]
    return []


def regra_segredo_no_vault(ctx) -> list[Disparo]:
    """Nota mudada nos ultimos 2 dias com algo que parece segredo.

    So as recentes: varrer o vault inteiro (31 MB) a cada 10 minutos seria
    desperdicio, e nota antiga ja foi varrida quando era recente. A escrita pelo
    delegation-core ja cobre; isto pega o que entrou por fora (editor, Obsidian,
    copia de arquivo).
    """
    from .listagem_vault import notas_do_vault
    from .segredos import achar

    raiz = Path(ctx.cfg.vault)
    corte = time.time() - 2 * 86400
    token = getattr(ctx.cfg, "server_token", "") or ""
    out = []
    for rel in notas_do_vault(ctx.cfg):
        p = raiz / rel
        try:
            if p.stat().st_mtime < corte:
                continue
            achados = achar(p.read_text(encoding="utf-8", errors="ignore"), (token,) if token else ())
        except OSError:
            continue
        if achados:
            out.append(Disparo(rel, f"possivel segredo em {rel}: " + ", ".join(sorted(achados)),
                               {"tipos": achados}))
    return out


_COMMIT_DO_GRAFO: dict[str, tuple[int, str | None]] = {}
GRAFO_COMMITS_ATRAS = 5


def _commit_do_grafo(caminho: Path) -> str | None:
    """`built_at_commit` do graph.json, lido uma vez por versao do arquivo (o maior tem 153 MB)."""
    import json as _json

    try:
        m = caminho.stat().st_mtime_ns
    except OSError:
        return None
    chave = str(caminho)
    if chave not in _COMMIT_DO_GRAFO or _COMMIT_DO_GRAFO[chave][0] != m:
        try:
            with open(caminho, encoding="utf-8") as f:
                c = _json.load(f).get("built_at_commit")
        except (OSError, ValueError):
            c = None
        _COMMIT_DO_GRAFO[chave] = (m, c if isinstance(c, str) and c else None)
    return _COMMIT_DO_GRAFO[chave][1]


def regra_grafo_desatualizado(ctx) -> list[Disparo]:
    """Grafo de repositorio git construido `GRAFO_COMMITS_ATRAS` ou mais commits antes do HEAD.

    Medido em 27/09: o grafo do delegation-core estava 9 commits atras e o do
    fork 68. Nota ligada a codigo (`vault_note_code`, `graph_notes`) e codigo
    que sumiu (`gone`) so valem com grafo em dia. Fonte que nao e git (copia
    de outro projeto, pacote baixado) nao anda sozinha e fica de fora; grafo
    de subpasta conta so os commits que tocam a subpasta.
    """
    import subprocess

    from . import registro_grafos

    out = []
    for nome, r in sorted((registro_grafos._load_registry(ctx.cfg) or {}).items()):
        src = (r or {}).get("source_path")
        gj = Path(ctx.cfg.graphs_dir) / nome / "graph.json"
        if not src or not Path(src).is_dir() or not gj.is_file():
            continue
        feito = _commit_do_grafo(gj)
        if not feito:
            continue
        try:
            # `-- .`: so commit que toca a pasta do grafo. Grafo de subpasta (o
            # painel, dentro do fork) nao envelhece com commit do resto do repo;
            # pasta fora de git faz o comando falhar e fica de fora
            n = subprocess.run(["git", "-C", src, "rev-list", "--count", f"{feito}..HEAD", "--", "."],
                               capture_output=True, text=True, timeout=10, **sem_janela())
        except (OSError, subprocess.TimeoutExpired):
            continue
        if n.returncode != 0 or not n.stdout.strip().isdigit():
            continue
        atras = int(n.stdout.strip())
        if atras >= GRAFO_COMMITS_ATRAS:
            out.append(Disparo(nome, f"grafo {nome} esta {atras} commits atras do repositorio "
                                     f"(construido em {feito[:8]}); graph_changed_notes lista as notas que "
                                     f"citam o codigo mudado, graph_build_bg refaz",
                               {"commits_atras": atras, "construido_em": feito, "fonte": src}))
    return out


def regras_padrao() -> list[Regra]:
    return [
        Regra("indice_atrasado", regra_indice_atrasado, "aviso", para_s=3600,
              descricao="notas mudaram e nao foram reindexadas por mais de 1 h"),
        Regra("saude_do_vault", regra_saude_do_vault, "aviso", para_s=1800),
        Regra("agenda_falhando", regra_agenda_falhando, "critico"),
        Regra("sentinela_esquecida", regra_sentinela_esquecida, "aviso", para_s=86400),
        Regra("inbox_parado", regra_inbox_parado, "info"),
        Regra("processo_parado", regra_processo_parado, "info"),
        Regra("disco", regra_disco, "critico"),
        Regra("segredo_no_vault", regra_segredo_no_vault, "critico"),
        Regra("grafo_desatualizado", regra_grafo_desatualizado, "info",
              descricao="grafo de codigo varios commits atras do repositorio"),
    ]


# ── avisar ──────────────────────────────────────────────────────────────────

def avisar(cfg, config_dir: Path, eventos: list[dict]) -> None:
    """Log sempre; area de trabalho se houver notify-send e nao estiver desligado."""
    if not eventos:
        return
    log = Path(config_dir) / "alertas.log"
    with log.open("a", encoding="utf-8") as f:
        for e in eventos:
            f.write(json.dumps({"quando": datetime.now().isoformat(timespec="seconds"), **e},
                               ensure_ascii=False) + "\n")
    if not getattr(cfg, "alertas_desktop", True) or not shutil.which("notify-send"):
        return
    for e in eventos:
        titulo = ("delegation-core: " + ("resolvido" if e["tipo"] == "resolvido" else e["severidade"]))
        urg = "critical" if e.get("severidade") == "critico" and e["tipo"] == "aberto" else "normal"
        try:
            subprocess.run(["notify-send", "-a", "delegation-core", "-u", urg, titulo, e.get("mensagem", "")],
                           timeout=5, check=False, capture_output=True, **sem_janela())
        except (OSError, subprocess.SubprocessError):
            pass


# ── o vigia ─────────────────────────────────────────────────────────────────

class Vigia:
    """A agenda, o motor de alertas e as acoes, montados sobre os objetos do daemon."""

    def __init__(self, cfg, vault, tracker=None, config_dir: Path | None = None, submeter=None):
        from .config import CONFIG_DIR

        self.cfg = cfg
        self.vault = vault
        self.tracker = tracker
        self.config_dir = Path(config_dir or CONFIG_DIR)
        self.submeter = submeter  # jobs.submit, para acoes que ja tem exclusividade la
        lista = getattr(cfg, "agenda_tarefas", None)
        tarefas, self.erros_de_config = tarefas_de_config(TAREFAS_PADRAO if lista is None else lista)
        self.agenda = Agenda(self.config_dir / "agenda.json", tarefas)
        self.agenda.destravar_orfas()
        self.alertas = MotorDeAlertas(self.config_dir / "alertas.json", regras_padrao())
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    def contexto(self):
        return SimpleNamespace(cfg=self.cfg, vault=self.vault, tracker=self.tracker,
                               agenda=self.agenda, config_dir=self.config_dir)

    # ── acoes ──────────────────────────────────────────────────────────────

    def acoes(self) -> dict:
        from . import historico_vault

        def historico(args):
            return historico_vault.fotografar(self.cfg, origem="agenda")

        def podar(args):
            h = historico_vault.abrir(self.cfg)
            return None if h is None else h.podar(manter_por_nota=int(args.get("manter_por_nota", 50)))

        def reindex(args):
            if self.submeter is None:
                return {"reindexadas": self.vault.reindex_vault(force=False)}
            # pela fila de jobs, que ja recusa segundo reindex simultaneo
            return {"job_id": self.submeter("vault_reindex:incremental", self.vault.reindex_vault, force=False)}

        def alertas(args):
            r = self.alertas.avaliar(self.contexto())
            avisar(self.cfg, self.config_dir, r["eventos"])
            saida = {"abertos": len(r["abertos"]), "pendentes": len(r["pendentes"]),
                     "eventos": [f"{e['tipo']}: {e['regra']} {e['sujeito']}" for e in r["eventos"]]}
            # o que o hook de inicio de sessao mostra: gravado aqui porque esta
            # e a tarefa que ja roda a cada 10 min e ja tem os alertas abertos
            try:
                from . import atencao
                saida["atencao"] = atencao.gravar(self.cfg, self.config_dir, self.alertas.abertos())
            except Exception as e:  # noqa: BLE001
                saida["atencao"] = {"erro": str(e)[:200]}
            return saida

        def lexico(args):
            from . import busca_hibrida
            return busca_hibrida.sincronizar(self.cfg)

        def sonho(args):
            from . import sonho_vault
            r = sonho_vault.sonhar_e_registrar(self.vault, dias=float(args.get("dias", 1)))
            return {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}

        def boletim(args):
            from . import boletim as _boletim
            return _boletim.gerar(self.vault, self.config_dir, self.tracker, horas=float(args.get("horas", 24)))

        def digestao(args):
            from . import digestao_vault
            r = digestao_vault.digerir(self.vault, maximo=int(args.get("maximo", 5)))
            saida = {k: (len(v) if isinstance(v, list) else v) for k, v in r.items()}
            if r.get("falhas"):
                # Sem isto a agenda so dizia "falhas: 5", noite apos noite, e o motivo se perdia.
                saida["motivos"] = [f"{f.get('transcricao')}: {f.get('erro')}" for f in r["falhas"][:3]]
            return saida

        def fatos(args):
            from . import fatos_vault
            return fatos_vault.extrair_pendentes(self.vault, maximo=int(args.get("maximo", 40)))

        return {"historico": historico, "podar_historico": podar, "reindex": reindex,
                "alertas": alertas, "lexico": lexico, "sonho": sonho, "boletim": boletim,
                "digestao": digestao, "fatos": fatos}

    def rodar(self, nome: str, agora: datetime | None = None) -> dict:
        t = self.agenda.tarefas.get(nome)
        if t is None:
            return {"error": f"Scheduled task not found: {nome}"}
        acao = self.acoes().get(t.acao)
        if acao is None:
            return {"error": f"Unknown action '{t.acao}' for task {nome}"}
        return self.agenda.executar(t, acao, agora=agora)

    def ciclo(self, agora: datetime | None = None) -> list[str]:
        """Roda o que estiver devido, uma tarefa por vez. Devolve os nomes rodados."""
        rodadas = []
        for t in self.agenda.devidas(agora):
            if self._parar.is_set():
                break
            # o mesmo relogio que decidiu que estava devida: sem passar `agora`
            # adiante, a ancora recebia o relogio real e o ciclo seguinte
            # decidia com os dois misturados (pego pelo teste do ciclo)
            self.rodar(t.nome, agora=agora)
            rodadas.append(t.nome)
        return rodadas

    # ── laco do daemon ─────────────────────────────────────────────────────

    def iniciar(self, intervalo: float = 30.0) -> None:
        if self._thread is not None:
            return

        def laco():
            while not self._parar.wait(intervalo):
                try:
                    self.ciclo()
                except Exception as e:  # noqa: BLE001 - o laco nao pode morrer
                    logger.warning("ciclo da agenda falhou: %s", e)

        self._thread = threading.Thread(target=laco, name="vigia", daemon=True)
        self._thread.start()

    def parar(self) -> None:
        self._parar.set()
