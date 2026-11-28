"""Guarda de suite: nenhum teste escreve em ~/.delegation_core.

Isto existe por causa de um estrago real, nao de uma preocupacao teorica.

Em 02/09/2026 um teste novo chamou `DelegationEngine.calibrate()`. O ultimo
que calibrate faz e `self.cfg.save()`, e `Config.save()` escreve em
`config.CONFIG_FILE`, que e uma constante de modulo apontando para
`~/.delegation_core/config.json`. O objeto Config nao sabe de onde veio: um
Config construido pelo teste com `vault_path=tmp_path` grava por cima da
config real da maquina exatamente como o Config carregado dela gravaria.

O resultado: o `config.json` do usuario passou a apontar para
`/tmp/pytest-of-joey/pytest-76/...`, o daemon subiu, nao encontrou vault,
imprimiu "delegation-core is not configured", e o systemd desistiu depois de
cinco tentativas. A maquina ficou sem servico ate a config ser reescrita a mao.

Ja tinha acontecido antes. O HANDOFF registra a correcao de 28/07: o fixture de
`test_dashboard_api_routes.py` passou a apontar CONFIG_DIR/CONFIG_FILE para
tmp_path. A correcao foi feita em UM arquivo, e a suite tem 65. Uma defesa que
depende de cada autor de teste lembrar dela nao e uma defesa.

Por isso o redirecionamento aqui e `autouse=True`: vale para todo teste da
suite, escrito antes ou depois, sem que ninguem precise pedir. Um teste que
QUEIRA exercitar o caminho de escrita continua podendo, e escreve no tmp_path
que este fixture instalou.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


#: Modulos que carregam CONFIG_DIR/CONFIG_FILE de `config` por `from ... import`
#: e portanto guardam a propria referencia, que reapontar `config.CONFIG_DIR`
#: sozinho nao alcanca.
_MODULOS_COM_COPIA = (
    "delegation_core.cli",
    "delegation_core.dashboard_api",
    "delegation_core.wizard",
    "delegation_core.doctor",
    "delegation_core.service",
    "delegation_core.clients",
    "delegation_core.windows",
    "delegation_core.localqueue",
    "delegation_core.tracker",
    "delegation_core.downloader",
    # installer.uninstall() REMOVE arquivos sob CONFIG_DIR. Um teste que o
    # chamasse sem este redirecionamento apagaria hooks/, sessions/, graphs/ e
    # a config da maquina de verdade. E a mesma copia de `from .config import
    # CONFIG_DIR` dos outros, so que destrutiva.
    "delegation_core.installer",
)


#: O estado real, calculado antes de qualquer teste mexer em HOME ou em modulo.
_ESTADO_REAL = (Path.home() / ".delegation_core").absolute()


def _dentro_do_estado_real(caminho: Path) -> bool:
    try:
        return Path(caminho).absolute().is_relative_to(_ESTADO_REAL)
    except (OSError, ValueError, RuntimeError):
        return False


_PACOTE_IMPORTADO = False


def _importar_o_pacote_inteiro():
    """Importa todo submodulo, para que a varredura abaixo alcance os
    caminhos de modulo que um teste so importaria depois do fixture. Uma vez
    por sessao: depois disso os modulos ja estao em sys.modules."""
    global _PACOTE_IMPORTADO
    if _PACOTE_IMPORTADO:
        return
    _PACOTE_IMPORTADO = True
    import pkgutil

    import delegation_core
    for info in pkgutil.walk_packages(delegation_core.__path__, "delegation_core."):
        if info.name.endswith("__main__"):
            continue          # importar __main__ executa a CLI com o argv do pytest
        try:
            importlib.import_module(info.name)
        except Exception:
            continue          # extra opcional ausente nao pode quebrar a suite


@pytest.fixture(autouse=True)
def _sem_daemon_real(monkeypatch):
    """Nenhum teste fala com o daemon de verdade desta maquina (6.1.2).

    O `cliente_fino` le a porta e o token do config.json; com CONFIG_DIR reapontado ele ja nao
    os acha, e esta trava cobre o caso de algum teste ler o config real. Os testes do proprio
    cliente fino tiram a variavel e sobem um daemon de teste."""
    monkeypatch.setenv("DELEGATION_CORE_SEM_DAEMON", "1")
    from delegation_core.filtros_saida import execucao
    monkeypatch.setattr(execucao, "_ESCRITOR", False)
    monkeypatch.setattr(execucao, "_COLETOR", None)


def _endereco_local(endereco) -> bool:
    """Laco, endereco nao especificado ou socket de caminho (AF_UNIX): fica nesta maquina."""
    if not isinstance(endereco, tuple) or not endereco:
        return True
    host = str(endereco[0]).lower()
    return host in ("", "localhost", "::1", "::", "0.0.0.0") or host.startswith("127.") or host.startswith("::ffff:127.")


def _nome_local(host) -> bool:
    if host is None or isinstance(host, (bytes, bytearray)) and not host:
        return True
    nome = host.decode("ascii", "replace") if isinstance(host, (bytes, bytearray)) else str(host)
    nome = nome.strip().lower().rstrip(".")
    if nome in ("", "localhost") or nome.endswith(".localhost"):
        return True
    import ipaddress
    try:
        ipaddress.ip_address(nome.split("%", 1)[0])
        return True          # IP literal nao consulta DNS; quem decide e o bloqueio do connect
    except ValueError:
        pass
    import socket
    try:
        return nome == socket.gethostname().lower()
    except OSError:
        return False


@pytest.fixture(autouse=True)
def _sem_rede_de_verdade(monkeypatch):
    """Nenhum teste sai desta maquina: conexao e consulta de nome para fora sao recusadas.

    ESCRITO DEPOIS DE MEDIR, em 27/11/2026. Um gancho de auditoria (`sys.addaudithook`) em todos os
    processos da suite mostrou `test_linguagem_sem_gramatica_cai_no_kompress_sem_quebrar` abrindo
    conexao com o Hugging Face: o recuo do compressor de codigo chamava o Kompress com o download
    ligado e a suite baixava 264 MB de modelo a cada rodada numa maquina sem o cache. O teste
    passava, porque trocava so o `_kompress` do roteador.

    A recusa tem a forma de "sem rede" (`ENETUNREACH`, `gaierror`), que e o que o codigo ja trata
    numa maquina desconectada. Como o codigo em teste costuma engolir esse erro, a tentativa fica
    anotada e o teste falha no fim, pelo nome. Vale para este processo; filho que a suite dispara
    nao herda monkeypatch.
    """
    import errno
    import socket

    tentativas: list[str] = []
    connect_real = socket.socket.connect
    connect_ex_real = socket.socket.connect_ex
    getaddrinfo_real = socket.getaddrinfo

    def connect(self, endereco, *resto):
        if not _endereco_local(endereco):
            tentativas.append(f"connect {endereco!r}")
            raise OSError(errno.ENETUNREACH, f"blocked by the test suite: no test connects to {endereco!r}")
        return connect_real(self, endereco, *resto)

    def connect_ex(self, endereco, *resto):
        if not _endereco_local(endereco):
            tentativas.append(f"connect {endereco!r}")
            return errno.ENETUNREACH
        return connect_ex_real(self, endereco, *resto)

    def getaddrinfo(host, *resto, **nomeados):
        if not _nome_local(host):
            tentativas.append(f"getaddrinfo {host!r}")
            raise socket.gaierror(socket.EAI_NONAME, f"blocked by the test suite: no test resolves {host!r}")
        return getaddrinfo_real(host, *resto, **nomeados)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    yield tentativas

    if tentativas:
        vistos = ", ".join(sorted(set(tentativas)))
        pytest.fail(
            f"o teste tentou sair desta maquina: {vistos}. Nenhum teste usa a rede: "
            "troque por um dublê o passo que baixa ou consulta (as tentativas foram recusadas)."
        )


@pytest.fixture(autouse=True)
def _sem_escrita_no_estado_real(tmp_path, monkeypatch):
    """Reaponta todo caminho de estado do usuario para um diretorio temporario."""
    import importlib

    from delegation_core import config as config_mod

    raiz = tmp_path / "estado_delegation_core"
    raiz.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(config_mod, "CONFIG_DIR", raiz, raising=False)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", raiz / "config.json", raising=False)

    # `from .config import CONFIG_DIR` copia o valor no import. Reapontar so o
    # modulo de origem deixa essas copias apontando para a casa do usuario.
    for nome in _MODULOS_COM_COPIA:
        try:
            mod = importlib.import_module(nome)
        except Exception:
            continue          # extra opcional ausente nao pode quebrar a suite
        for atributo, valor in (("CONFIG_DIR", raiz),
                                ("CONFIG_FILE", raiz / "config.json"),
                                ("STORE_PATH", raiz / "local_tasks.json")):
            if hasattr(mod, atributo):
                monkeypatch.setattr(mod, atributo, valor, raising=False)

    # Qualquer OUTRO caminho de modulo que caia dentro do estado real, com
    # qualquer nome. A lista acima cobre CONFIG_DIR, CONFIG_FILE e STORE_PATH,
    # e em 29/09/2026 isso nao bastou: `ingest._REGISTRY_FILE` e calculado no
    # import, nenhum dos tres nomes o alcanca, e um teste novo que chamou
    # `_save_registry` sem reapontar o nome a mao gravou uma fonte do pytest
    # por cima do `ingested_sources.json` real. Aconteceu em duas maquinas:
    # aqui o registro de 23 fontes virou 1, e num Mac o de 172 virou 1, o que
    # fez a reconstrucao do indice de la pular todas as fontes externas. Oito
    # testes ja faziam o reapontamento a mao; o nono esqueceu.
    _importar_o_pacote_inteiro()
    for nome, mod in list(sys.modules.items()):
        if not nome.startswith("delegation_core") or mod is None:
            continue
        for atributo, valor in list(vars(mod).items()):
            if isinstance(valor, Path) and _dentro_do_estado_real(valor):
                monkeypatch.setattr(mod, atributo,
                                    raiz / valor.relative_to(_ESTADO_REAL), raising=False)

    # ~/.claude/settings.json fica fora de ~/.delegation_core, e desde a v0.15.0
    # o instalador registra os hooks de sessao nele. Os testes do instalador
    # chamam post_install, update e uninstall: sem isto, gravariam no arquivo
    # real de quem roda a suite.
    from delegation_core import clients as clients_mod
    monkeypatch.setattr(clients_mod, "CLAUDE_SETTINGS", raiz / "claude_settings.json",
                        raising=False)
    # O mesmo vale para ~/.codex/hooks.json, que `post_install` e `update`
    # tambem gravam. Medido em 19/10/2026: rodar os testes do instalador criou o
    # arquivo real, apontando para o venv de quem rodou, e o Codex da maquina
    # passaria a disparar o hook. A constante e calculada no import, entao
    # trocar `Path.home` nao a alcanca.
    monkeypatch.setattr(clients_mod, "CODEX_HOOKS", raiz / "codex_hooks.json",
                        raising=False)

    yield raiz



@pytest.fixture(autouse=True)
def _sem_gerenciador_de_servico_real(tmp_path, monkeypatch):
    """Nenhum teste executa systemctl/launchctl/schtasks de verdade.

    ESCRITO DEPOIS DO ESTRAGO, em 03/09/2026. Um teste novo chamou
    `installer.uninstall(dry_run=False)`. O redirecionamento de CONFIG_DIR
    acima protegeu os ARQUIVOS: nada foi apagado de ~/.delegation_core. Mas
    `uninstall` tambem desregistra os servicos, e essa metade nao passa por
    CONFIG_DIR nenhum: passa por `service._run(["systemctl", "--user",
    "disable", "--now", "delegation-core"])` com o nome REAL da unit.

    Resultado medido: o daemon da maquina ficou `inactive`, a unit
    `~/.config/systemd/user/delegation-core.service` foi removida, e
    `systemctl --user is-enabled` passou a responder `not-found`. O teste
    ainda levou 16,6s no lugar de 0,2s, porque estava esperando o systemd de
    verdade. Foi preciso `delegation-core service install` para reverter.

    A licao e a que este arquivo ja abre dizendo sobre o `calibrate()`: o
    perigo nao e o teste que se sabe destrutivo, e a funcao que faz mais do que
    o nome do fixture cobre. Por isso isto e `autouse` e nao um opt-in.

    Devolve (127, ...), que e a forma de "comando indisponivel" que os
    chamadores ja tratam: uma maquina sem systemd responde a mesma coisa.
    """
    from delegation_core import service as service_mod

    def _bloqueado(cmd, timeout=30):
        return (127, "blocked by the test suite: no test runs a real service manager")

    monkeypatch.setattr(service_mod, "_run", _bloqueado, raising=False)

    # A sonda de porta tambem sai, e por um motivo diferente do bloqueio acima:
    # sem ela o resultado do teste depende de o daemon do usuario estar de pe
    # neste instante. `installer.uninstall` recusa com "refused_daemon_still_up"
    # quando algo responde na porta, entao o mesmo teste passava na maquina de
    # quem tinha o servico parado e falhava na de quem nao tinha. Falso na
    # suite significa "nao ha daemon aqui", que e o mundo em que um teste roda.
    monkeypatch.setattr(service_mod, "_port_answers", lambda: False, raising=False)

    # E os CAMINHOS das units, que e por onde o estrago passou de verdade.
    # Bloquear `_run` tira os `systemctl disable`, mas `service.uninstall` apaga
    # o arquivo com `SYSTEMD_UNIT.unlink(missing_ok=True)`, direto, sem passar
    # por comando nenhum. Foi assim que a unit real caiu uma SEGUNDA vez, ja com
    # o bloqueio de `_run` no lugar: a rede de seguranca abaixo pegou e nomeou o
    # teste culpado, que e exatamente para isso que ela existe.
    unidades = tmp_path / "systemd-de-mentira"
    unidades.mkdir(parents=True, exist_ok=True)
    for atributo, destino in (
        ("SYSTEMD_UNIT", unidades / "delegation-core.service"),
        ("LLAMA_SYSTEMD_UNIT", unidades / "delegation-core-llama.service"),
        ("LAUNCHD_PLIST", unidades / "com.delegation-core.plist"),
        ("LLAMA_LAUNCHD_PLIST", unidades / "com.delegation-core.llama.plist"),
    ):
        monkeypatch.setattr(service_mod, atributo, destino, raising=False)


def _so_os_hooks_do_dc_mudaram(orig: bytes | None, atual: bytes) -> bool:
    """A escrita tem a forma da do instalador: so a chave `hooks` mudou e o novo cita o delegation-core.

    O instalador mescla os hooks e preserva o resto do arquivo; o Claude Code, quando grava o
    settings.json por conta propria (/effort, /model), muda outras chaves.
    """
    import json
    try:
        a = json.loads(orig) if orig else {}
        b = json.loads(atual)
    except ValueError:
        return False
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    mudaram = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    texto = json.dumps(b.get("hooks"))
    return mudaram == {"hooks"} and ("delegation-core" in texto or "delegation_core" in texto)


@pytest.fixture(autouse=True)
def _units_do_systemd_intactas():
    """Rede de seguranca para o mesmo estrago, caso alguem contorne o bloqueio.

    Falha o teste culpado em vez de deixar a maquina sem daemon para quem for
    rodar a suite depois. Mesma forma da rede de hooks/venv/models acima, que
    nao cobria isto porque as units vivem fora de ~/.delegation_core.
    """
    unidades = Path.home() / ".config" / "systemd" / "user"
    antes = {p.name for p in unidades.glob("delegation-core*.service")} if unidades.exists() else set()
    # Conteudo, e nao so presenca: um teste que dispara um processo filho do delegation-core
    # reescreve a unit e os hooks dos clientes sem passar por monkeypatch nenhum (o bloqueio de
    # `service._run` acima vale so para este processo). Arquivo que mudou volta ao original e o
    # teste falha pelo nome; arquivo que o teste criou e removido.
    vigiados = [unidades / n for n in sorted(antes)] + [
        Path.home() / ".claude" / "settings.json", Path.home() / ".codex" / "hooks.json"]
    conteudo = {c: (c.read_bytes() if c.is_file() else None) for c in vigiados}

    yield

    depois = {p.name for p in unidades.glob("delegation-core*.service")} if unidades.exists() else set()
    sumiram = antes - depois
    if sumiram:
        pytest.fail(
            f"o teste removeu {', '.join(sorted(sumiram))} de {unidades}. "
            "Nenhum teste desregistra servico real: use um dublê de service._run. "
            "Para reverter a mao: delegation-core service install"
        )
    mexidos = []
    for c, orig in conteudo.items():
        atual = c.read_bytes() if c.is_file() else None
        if atual == orig:
            continue
        # O settings.json tambem e escrito pelo proprio Claude Code (/effort, /model) enquanto a suite
        # roda; so volta ao original a escrita com sinal da suite (o python dela ou caminho temporario).
        da_suite = c.parent == unidades or (atual is not None and (
            sys.executable.encode() in atual or b"/tmp/" in atual or b"pytest" in atual
            or _so_os_hooks_do_dc_mudaram(orig, atual)))
        if not da_suite:
            mexidos.append(f"{c} (mudou, sem sinal da suite: nao revertido)")
            continue
        mexidos.append(str(c))
        if orig is None:
            c.unlink(missing_ok=True)
        else:
            c.write_bytes(orig)
    for n in sorted(depois - antes):
        mexidos.append(str(unidades / n))
        (unidades / n).unlink(missing_ok=True)
    if mexidos:
        pytest.fail(
            f"o teste mexeu em {', '.join(mexidos)} (os da suite ja voltaram ao original). Um processo filho "
            "do delegation-core nao herda monkeypatch: troque o passo que o dispara por um dublê."
        )

@pytest.fixture(autouse=True)
def _config_real_intacta():
    """Rede de seguranca: falha o teste que ainda assim tocar a config real.

    O fixture acima cobre os caminhos conhecidos. Este cobre os que ninguem
    mapeou ainda, e falha o teste culpado em vez de deixar a maquina quebrada
    para quem for rodar a suite depois.
    """
    real = Path.home() / ".delegation_core" / "config.json"
    antes = real.read_bytes() if real.exists() else None

    # Desde que `installer.uninstall()` existe, a suite tem uma funcao que
    # APAGA diretorios sob ~/.delegation_core. Conferir so o config.json
    # deixaria passar um teste que removesse hooks/ ou o venv, que e um
    # estrago maior e mais silencioso do que o que criou este arquivo.
    raiz_real = Path.home() / ".delegation_core"
    vigiados = ("hooks", "venv", "models")
    presentes_antes = {n for n in vigiados if (raiz_real / n).exists()}

    yield

    sumiram = presentes_antes - {n for n in vigiados if (raiz_real / n).exists()}
    if sumiram:
        pytest.fail(
            f"o teste apagou {', '.join(sorted(sumiram))} de {raiz_real}. "
            "Nenhum teste pode remover estado real: use o tmp_path que "
            "conftest._sem_escrita_no_estado_real ja instalou. Isto nao pode "
            "ser desfeito automaticamente."
        )

    depois = real.read_bytes() if real.exists() else None
    if antes != depois:
        # Devolve o arquivo antes de falhar: o teste ja errou, a maquina do
        # usuario nao precisa pagar por isso.
        if antes is None:
            real.unlink(missing_ok=True)
        else:
            real.write_bytes(antes)
        pytest.fail(
            f"o teste escreveu em {real}. Nenhum teste pode tocar o estado real "
            "da maquina: use o tmp_path que conftest._sem_escrita_no_estado_real "
            "ja instalou. O arquivo foi restaurado."
        )


@pytest.fixture(autouse=True)
def _sem_reordenador_real(monkeypatch):
    """Nenhum teste carrega o cross-encoder de verdade (2 GB, e GPU se houver).

    Nesta maquina o modelo esta no cache e a placa tem espaco, entao sem isto
    todo teste que passa pelo search_vault carregaria o reordenador real. Quem
    testa a busca hibrida poe um duble no lugar de `busca_hibrida.reordenador`.
    O estado do modulo tambem e zerado, porque indice lexico e reordenador sao
    guardados por processo.
    """
    from delegation_core import busca_hibrida

    monkeypatch.setattr(busca_hibrida, "reordenador", lambda cfg: None)
    monkeypatch.setattr(busca_hibrida, "_estado", {"indice": None, "sincronizado_em": 0.0,
                                                   "reordenador": None, "motivo_sem_reordenador": ""})


@pytest.fixture(autouse=True)
def _sem_extracao_de_fatos_em_segundo_plano(monkeypatch):
    """Escrever nota viva agenda extracao de fatos pelo modelo local (fatos_vault.apos_escrita).

    Na suite isso chamaria o llama de verdade na porta 8181. O agendador
    padrao vira um que nao agenda; teste que quiser o caminho passa o seu.
    """
    from delegation_core import fatos_vault
    monkeypatch.setattr(fatos_vault, "SUBMETER_PADRAO", lambda *a, **k: None)

@pytest.fixture
def backend_chroma(monkeypatch):
    """Fixa o indice do Chroma, o padrao ate a migracao para SQLite.

    Para os testes cujo assunto E o Chroma: reabertura de cliente, quarentena da
    pasta `.chroma_bge`, leitura de `chroma.sqlite3` e a recuperacao desse indice.
    Os demais usam o padrao (SQLite num vault novo).
    """
    from delegation_core.config import Config
    monkeypatch.setattr(Config, "usa_sqlite", property(lambda self: False))


def pytest_addoption(parser):
    parser.addoption("--atualizar-baseline-evals", action="store_true", default=False,
                     help="regrava tests/evals_busca/baseline.json com as metricas medidas agora")


@pytest.fixture(autouse=True)
def _token_do_dashboard(request, monkeypatch):
    """Instala o bearer token que a API do dashboard exige, so nos testes dela.

    O servidor falha fechado sem token, entao sem isto todo teste de rota levaria
    401. Os testes mandam `tests._dashboard_auth.AUTH` de forma explicita em cada
    chamada: este fixture so decide o que o servidor aceita, nao o que o cliente
    envia, e por isso nao deixa passar um teste que esqueceu a cabecalho.
    """
    if "dashboard" not in request.module.__name__:
        return
    from delegation_core import dashboard_api
    from tests._dashboard_auth import TOKEN

    monkeypatch.setattr(dashboard_api, "_token", TOKEN)


@pytest.fixture
def catalogo_de_skills():
    """Catalogo de skills pequeno e conhecido, no estado temporario do teste.

    O catalogo real e construido na maquina de quem usa e nao vem no repositorio (texto de
    terceiros sem licenca conferida); testes que precisam de busca usam este."""
    from delegation_core.cores.agent_harness import db
    conn = db.get_connection()
    linhas = [
        ("ECC", "Git commit discipline", "ECC/git-commit.md", "harness-skills",
         "Write small git commit messages; one change per commit."),
        ("ECC", "Python testing", "ECC/python-tests.md", "harness-skills",
         "Use pytest for python projects; keep fixtures small."),
        ("ECC", "Code review", "ECC/review.md", "harness-skills",
         "Review the diff before the commit; read every changed line."),
        ("superpowers", "TDD loop", "superpowers/tdd.md", "tdd-discipline",
         "Red, green, refactor. Write the failing python test first."),
        ("humanizer", "Plain prose", "humanizer/prose.md", "prose-naturalization",
         "Prefer short sentences and concrete words over filler."),
    ]
    with conn:
        conn.execute("DELETE FROM skills")
        for repo, titulo, rel, cat, texto in linhas:
            conn.execute("INSERT INTO skills (source_repo, title, rel_path, category, content, char_count) "
                         "VALUES (?, ?, ?, ?, ?, ?)", (repo, titulo, rel, cat, texto, len(texto)))
    conn.close()
    return len(linhas)
