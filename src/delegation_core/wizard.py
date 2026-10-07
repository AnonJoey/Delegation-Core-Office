"""
wizard.py: Interactive setup wizard for delegation-core.
Designed for non-technical users: numbered menus, progress bars, clear prompts.
No technical knowledge required.
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from .config import Config, CONFIG_DIR
from .downloader import MODELS, download_llama_binary, download_model, find_llama_binary

console = Console()


# ── entry point ───────────────────────────────────────────────────────────────

#: Pastas que o AGENT_GUIDE manda usar (`write_note(folder="Projects")`, "Decisions",
#: "Sessions", "Procedures"...). O wizard criava `decisions research tools fixes
#: reference sessions`, em minusculas e com uma `research` que o proprio guia diz
#: nao existir: numa instalacao nova, gravar em Projects, Procedures, Scratch ou
#: Infrastructure falhava com "pasta invalida".
PASTAS_PADRAO = ["Projects", "Decisions", "Fixes", "Sessions", "Procedures",
                 "Reference", "Tools", "Scratch", "Infrastructure"]

TOTAL_DE_PASSOS = 8


def _apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def run_wizard():
    _welcome()
    try:
        cfg = Config.load()

        _header("System Check", "Detecting your environment")
        _step_system_check()

        _header(f"Step 1 of {TOTAL_DE_PASSOS}", "Your Notes Vault")
        vault_path, vault_folders = _step_vault()
        cfg.vault_path = str(vault_path)
        cfg.vault_folders = vault_folders
        _step_index_location(cfg)

        _header(f"Step 2 of {TOTAL_DE_PASSOS}", "AI Engine")
        cfg.engine_mode = _step_engine_mode()

        if cfg.engine_mode == "agent":
            # Agent mode: no local model: nothing to download. Generation is
            # delegated to the calling Claude; embeddings/search stay local.
            cfg.llama_model = ""
            cfg.llama_binary = ""
            cfg.motor_local = "llamacpp"
            console.print("  [green]✓[/green] Agent mode: skipping model and engine "
                          "download. Claude will handle generation.\n")
        else:
            cfg.motor_local = _step_local_engine_kind() if _apple_silicon() else "llamacpp"
            if cfg.motor_local == "mlx":
                _header(f"Step 3 of {TOTAL_DE_PASSOS}", "AI Model (MLX)")
                cfg.llama_binary, cfg.llama_model = _step_mlx()
            else:
                _header(f"Step 3 of {TOTAL_DE_PASSOS}", "AI Model")
                cfg.llama_model = _step_model(cfg.models_dir)

                _header(f"Step 3b of {TOTAL_DE_PASSOS}", "Local Engine (llama.cpp)")
                cfg.llama_binary = _step_binary(cfg.llama_dir)

        _header(f"Step 4 of {TOTAL_DE_PASSOS}", "Start at Login")
        auto_start = _step_startup()

        _header(f"Step 5 of {TOTAL_DE_PASSOS}", "Processing Options")
        synthesis_enabled, synthesis_lang, budget_mode = _step_features()
        cfg.synthesis_enabled = synthesis_enabled
        cfg.synthesis_lang    = synthesis_lang
        cfg.budget_mode       = budget_mode

        _header(f"Step 6 of {TOTAL_DE_PASSOS}", "Embedding Model")
        _step_embedding_model(cfg)
        cfg.save()
        if _apple_silicon():
            _step_embed_llama(cfg)

        _header(f"Step 7 of {TOTAL_DE_PASSOS}", "Building Search Index")
        _step_index(cfg)

        _header(f"Step 8 of {TOTAL_DE_PASSOS}", "Start the Server and Connect Claude")
        conexao = _step_connect(cfg, auto_start)

        _completion(cfg, conexao)

    except (KeyboardInterrupt, EOFError):
        # EOFError: stdin closed (piped input ran out, CI, a script). It used to
        # end in a traceback in the middle of a half-finished setup.
        console.print("\n\n[yellow]Setup cancelled.[/yellow] Nothing was installed "
                      "beyond what is already shown above; run "
                      "[bold]delegation-core setup[/bold] to continue.\n")
        sys.exit(0)


# ── system check ─────────────────────────────────────────────────────────────

def _step_system_check():
    system = platform.system()
    machine = platform.machine()
    py = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    ok  = "[green]✓[/green]"
    bad = "[red]✗[/red]"

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("label", style="dim", min_width=22)
    table.add_column("value")

    os_names = {"Linux": "Linux", "Darwin": "macOS", "Windows": "Windows"}
    table.add_row("Operating System", f"{os_names.get(system, system)}  ({machine})")
    table.add_row("Python", py)

    inalcancaveis = _hosts_inalcancaveis()
    internet = not inalcancaveis
    table.add_row("Internet", f"{ok} connected" if internet
                  else f"{bad} [red]cannot reach {', '.join(inalcancaveis)}[/red]")

    if system == "Linux":
        pkg_status, missing = _check_linux_packages()
        table.add_row("System packages", pkg_status)
    elif system == "Darwin":
        xcode_ok = _check_xcode()
        table.add_row("Xcode CLT", f"{ok} installed" if xcode_ok else "[yellow]⚠[/yellow]  not found")

    console.print(table)
    console.print()

    if not internet:
        console.print("  [red]Setup downloads the embedding model from Hugging Face and the local engine "
                      "from GitHub, and cannot reach "
                      f"{', '.join(inalcancaveis)}.[/red]")
        console.print("  Behind a corporate proxy? Set [bold]HTTPS_PROXY[/bold] in this terminal and run "
                      "setup again. If the models are already on this machine, you can continue.\n")
        raw = console.input("  Continue anyway? [y/N]: ").strip().lower()
        if raw not in ("y", "yes"):
            sys.exit(1)
        console.print()

    if system == "Linux" and missing:
        _install_linux_packages(missing)
    elif system == "Darwin" and not _check_xcode():
        _install_xcode()

    # Final Python package availability check
    _verify_python_packages()

    console.print(f"  {ok} Environment ready.\n")


#: O que o setup de fato baixa. O teste antigo abria 8.8.8.8:53, o DNS do Google:
#: atras de um firewall ou proxy corporativo (o caso comum de quem instala numa
#: empresa) essa porta e bloqueada mesmo com o HTTPS para o Hugging Face e o
#: GitHub funcionando, e o wizard recusava seguir com "no connection".
HOSTS_DE_DOWNLOAD = ("https://huggingface.co", "https://github.com")


def _hosts_inalcancaveis() -> list[str]:
    """Os hosts de download que esta maquina nao alcanca, respeitando HTTP(S)_PROXY."""
    try:
        import requests
    except ImportError:  # sem requests o resto do setup tambem nao roda
        return [h.split("//", 1)[1] for h in HOSTS_DE_DOWNLOAD]
    fora = []
    for url in HOSTS_DE_DOWNLOAD:
        try:
            requests.head(url, timeout=6, allow_redirects=True)
        except requests.RequestException:
            fora.append(url.split("//", 1)[1])
    return fora


def _check_internet() -> bool:
    return not _hosts_inalcancaveis()


def _check_linux_packages() -> tuple[str, list[str]]:
    if not shutil.which("dpkg"):
        return "[dim]non-apt system: skipped[/dim]", []
    required = ["python3-venv", "python3-dev", "build-essential"]
    missing = []
    for pkg in required:
        r = subprocess.run(["dpkg", "-s", pkg], capture_output=True, text=True)
        if r.returncode != 0:
            missing.append(pkg)
    if missing:
        return f"[yellow]missing: {', '.join(missing)}[/yellow]", missing
    return "[green]✓[/green]  all present", []


def _install_linux_packages(missing: list[str]):
    console.print(f"  Missing system packages: [bold]{', '.join(missing)}[/bold]")
    raw = console.input("  Install them now? (requires sudo password) [Y/n]: ").strip().lower()
    if raw in ("n", "no"):
        console.print("  [yellow]Skipped.[/yellow] You may encounter errors during installation.\n")
        return
    console.print()
    try:
        subprocess.run(["sudo", "apt-get", "install", "-y"] + missing, check=True)
        console.print("\n  [green]✓[/green] System packages installed.\n")
    except subprocess.CalledProcessError:
        console.print("\n  [red]Install failed.[/red] Try manually:")
        console.print(f"    sudo apt-get install {' '.join(missing)}\n")


def _check_xcode() -> bool:
    r = subprocess.run(["xcode-select", "-p"], capture_output=True, text=True)
    return r.returncode == 0


def _install_xcode():
    console.print("  [yellow]Xcode Command Line Tools are needed to install Python packages.[/yellow]")
    raw = console.input("  Install them now? [Y/n]: ").strip().lower()
    if raw in ("n", "no"):
        console.print("  [yellow]Skipped.[/yellow] You may see errors during installation.\n")
        return
    console.print("  Starting Xcode installer: a dialog will appear, click Install.")
    subprocess.run(["xcode-select", "--install"], capture_output=True)
    console.input("  Press Enter once the Xcode installer has finished: ")
    console.print()


def _verify_python_packages():
    checks = [
        ("fastmcp",             "fastmcp"),
        ("chromadb",            "chromadb"),
        ("sentence_transformers","sentence-transformers"),
        ("requests",            "requests"),
        ("rich",                "rich"),
    ]
    missing = []
    for module, pkg in checks:
        try:
            __import__(module)
        except ImportError:
            missing.append(pkg)
    if missing:
        console.print(f"  [red]Missing Python packages:[/red] {', '.join(missing)}")
        console.print("  Run the installer again ([bold]./install.sh[/bold] or [bold]install.bat[/bold]) "
                      "in the folder you cloned.\n")
        sys.exit(1)


# ── steps ─────────────────────────────────────────────────────────────────────

def _step_vault() -> tuple[Path, list[str]]:
    defaults = list(PASTAS_PADRAO)
    console.print("  Where is your notes vault?\n")
    console.print("  [dim]A folder of markdown notes (an Obsidian vault works, Obsidian itself is "
                  "optional). delegation-core reads and writes notes here.[/dim]\n")

    while True:
        raw = console.input("  Vault path (e.g. ~/Documents/Vault): ").strip()
        if not raw:
            continue
        vault_path = Path(raw).expanduser().resolve()
        if _conflicts_with_config_dir(vault_path):
            _warn_config_dir_conflict(vault_path)
            continue
        if vault_path.exists() and not vault_path.is_dir():
            console.print("  [red]That path is a file, not a directory. Try again.[/red]\n")
            continue
        break

    if not vault_path.exists():
        console.print(f"\n  Directory [bold]{vault_path}[/bold] does not exist.")
        raw = console.input("  Create it now? [Y/n]: ").strip().lower()
        if raw not in ("", "y", "yes"):
            console.print("\n  [yellow]Setup cancelled.[/yellow]\n")
            sys.exit(0)
        vault_path.mkdir(parents=True, exist_ok=True)
        console.print(f"  [green]✓[/green] Created {vault_path}")

    # `_inbox` e `_processed` sao do proprio delegation-core, e `.obsidian` e
    # escondida: nenhuma delas e pasta de notas para indexar.
    existing_dirs = sorted(d.name for d in vault_path.iterdir()
                           if d.is_dir() and not d.name.startswith((".", "_")))
    if existing_dirs:
        console.print(f"\n  Found existing folders in vault: [bold]{', '.join(existing_dirs)}[/bold]")
        raw = console.input("  Use these folders for the vault structure? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            folders = existing_dirs
        else:
            folders = defaults
            for f in defaults:
                (vault_path / f).mkdir(exist_ok=True)
            console.print(f"  [green]Created default folders:[/green] {', '.join(defaults)}")
    else:
        console.print(f"\n  Creating standard vault folders: [bold]{', '.join(defaults)}[/bold]")
        for f in defaults:
            (vault_path / f).mkdir(exist_ok=True)
        folders = defaults
        console.print(f"  [green]Created:[/green] {', '.join(defaults)}")

    console.print(f"\n  [green]✓[/green] Vault ready: {vault_path}\n")
    return vault_path, folders


def _step_index_location(cfg: Config) -> None:
    """Tira o indice de dentro de um vault que mora numa pasta sincronizada.

    Sincronizacao (OneDrive, iCloud, Dropbox, Google Drive) mexendo no SQLite do
    Chroma sob um processo aberto danifica o indice: foi o que derrubou o daemon
    de um Mac em setembro, e a recuperacao automatica so entra DEPOIS do dano.
    O wizard e o unico lugar que sabe, antes de o indice existir, onde o vault esta.
    """
    from .config import caminho_local_do_indice, em_pasta_sincronizada
    if str(cfg.index_path or "").strip() or not em_pasta_sincronizada(cfg.vault):
        return
    cfg.index_path = str(caminho_local_do_indice())
    console.print("  [yellow]This vault is inside a cloud-synced folder.[/yellow] A sync client rewriting "
                  "the search index while it is open corrupts it,")
    console.print(f"  so the index will live outside it, at [bold]{cfg.index_path}[/bold]. "
                  "Your notes stay where they are.\n")


def _conflicts_with_config_dir(path: Path) -> bool:
    """True when `path` must not be used as a vault.

    uninstall.sh / uninstall.bat remove a fixed list of CONFIG_DIR subpaths by
    name (sessions/, config.json, graphs/, ...) without ever touching the
    configured vault_path directly. That guarantee only holds if the vault
    itself is never placed at/under CONFIG_DIR in the first place: otherwise
    a targeted removal could coincidentally delete real vault content that
    happens to share one of those names — and `Sessions` is a vault folder on
    every install, against the uninstaller's `sessions/`. Reject the path here
    instead.

    A path that cannot be resolved is rejected too. This used to `return False`
    — "no conflict" — for a path it had failed to examine, which is a check that
    passes when it cannot check. `_unindexed_notes` already carries the rule in
    its own docstring: degrade to "cannot tell", never to "all fine". The cost
    of being wrong in this direction is the user picking a different folder; the
    cost in the other direction is the uninstaller deleting their notes.
    """
    try:
        resolved = path.resolve()
        cfg = CONFIG_DIR.resolve()
    except OSError:
        return True
    return resolved == cfg or cfg in resolved.parents


def _warn_config_dir_conflict(path: Path):
    # Two reasons reach here — it really is under CONFIG_DIR, or it could not be
    # resolved at all — and the message used to assert the first for both.
    console.print(f"  [red]That path cannot be used as a vault: it is "
                  f"delegation-core's own config directory ({CONFIG_DIR}), is "
                  f"inside it, or could not be resolved.[/red]")
    console.print("  [red]Choose a location outside of it: uninstalling could "
                  "otherwise delete vault content.[/red]\n")


def _step_engine_mode() -> str:
    """Choose where generation runs: local model, the calling Claude, or hybrid.

    Returns "local", "agent", or "hybrid". Embeddings + search always run locally.
    """
    console.print("  How should delegation-core generate summaries and compress content?\n")
    console.print("  [bold]1. Local model[/bold] (llama.cpp)")
    console.print("     [dim]Runs a model on this machine. Fully offline, but uses RAM/CPU[/dim]")
    console.print("     [dim]and competes with your other apps. Downloads ~2 GB on setup.[/dim]\n")
    console.print("  [bold]2. Agent (Claude does it)[/bold]  [green](lightest)[/green]")
    console.print("     [dim]No local model. The Claude you're talking to handles generation;[/dim]")
    console.print("     [dim]this machine only runs the (small) embedding + search layer. Nothing[/dim]")
    console.print("     [dim]to download. Best if the local model strains your hardware.[/dim]\n")
    console.print("  [bold]3. Hybrid[/bold]  [green](recommended)[/green]")
    console.print("     [dim]Interactive work goes to Claude (fast, no load); big/slow/bulk[/dim]")
    console.print("     [dim]jobs (whole-vault synthesis, healing) use the local model in the[/dim]")
    console.print("     [dim]background. Oversized calls show their token cost and let you choose[/dim]")
    console.print("     [dim]local vs Claude. Downloads ~2 GB (needs the local model on hand).[/dim]\n")

    choice = _menu_index("Choose an engine", 3)
    mode = {0: "local", 1: "agent", 2: "hybrid"}[choice]
    label = {"local": "Local model (llama.cpp)",
             "agent": "Agent: Claude handles generation",
             "hybrid": "Hybrid: Claude for interactive, local model for big/bulk"}[mode]
    console.print(f"\n  [green]✓[/green] Engine: {label}\n")
    return mode


def _step_model(models_dir: Path) -> str:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Model", min_width=16)
    table.add_column("Download", min_width=9)
    table.add_column("RAM needed", min_width=10)
    table.add_column("Description")

    for i, m in enumerate(MODELS, 1):
        name = m["name"]
        if m.get("recommended"):
            name += "  [yellow]★ recommended[/yellow]"
        already = (models_dir / m["filename"]).exists()
        size_str = "[green]on disk[/green]" if already else m["size"]
        table.add_row(str(i), name, size_str, m["ram"], m["description"])

    console.print("  These models run entirely on your computer.\n")
    console.print(table)
    console.print()

    choice = _menu_index("Choose a model", len(MODELS))
    model = MODELS[choice]

    dest = models_dir / model["filename"]
    if dest.exists():
        console.print(f"\n  [green]✓[/green] Already downloaded: {model['name']}\n")
    else:
        console.print(f"\n  Downloading [bold]{model['name']}[/bold] ({model['size']}): this may take a few minutes...\n")
        result = download_model(model, models_dir)
        if not result:
            console.print("\n  [red]Download failed.[/red] Check your internet connection and run setup again.")
            sys.exit(1)
        console.print(f"\n  [green]✓[/green] {model['name']} ready.\n")

    return str(dest)


def _step_binary(llama_dir: Path) -> str:
    existing = find_llama_binary(llama_dir)

    if existing:
        console.print(f"  Found existing llama.cpp: [bold]{existing}[/bold]")
        raw = console.input("  Use this? [Y/n]: ").strip().lower()
        if raw in ("", "y", "yes"):
            console.print("\n  [green]✓[/green] Using existing binary.\n")
            return str(existing)

    console.print("  llama.cpp is the engine that runs the AI model locally.")
    console.print("  We can download and install it automatically.\n")
    raw = console.input("  Download llama.cpp automatically? [Y/n]: ").strip().lower()

    if raw in ("n", "no"):
        return _pedir_binario("  Enter the full path to your llama-server binary: ")

    console.print()
    result = download_llama_binary(llama_dir)
    if result:
        console.print("\n  [green]✓[/green] llama.cpp installed.\n")
        return str(result)

    console.print("\n  [yellow]Automatic download failed.[/yellow]")
    console.print("  You can download it manually from:")
    console.print("  [bold]https://github.com/ggml-org/llama.cpp/releases[/bold]\n")
    return _pedir_binario("  Enter path to llama-server binary once downloaded: ")


def _pedir_binario(pergunta: str) -> str:
    """Pede o caminho de um executavel ate ele existir, ou vazio para deixar para depois.

    Antes aceitava qualquer texto, inclusive vazio, que virava `Path("")` e ia
    para o config.json: o `doctor` so reclamava depois, e o motor nunca subia.
    """
    while True:
        raw = console.input(pergunta + "(empty to set it later in config.json) ").strip()
        if not raw:
            console.print("  [yellow]No engine configured.[/yellow] Set llama_binary in "
                          "~/.delegation_core/config.json before using local generation.\n")
            return ""
        caminho = Path(raw).expanduser()
        if caminho.is_file():
            return str(caminho)
        console.print(f"  [red]No file at {caminho}. Try again.[/red]\n")


# ── MLX (Macs com Apple Silicon) ─────────────────────────────────────────────

#: Um modelo pequeno que existe de verdade no Hugging Face, so para o primeiro
#: teste. Modelos maiores pedem muita memoria: ver docs/INSTALL_MAC_MLX.md.
MODELO_MLX_PADRAO = "mlx-community/Qwen3-0.6B-4bit"


def _step_local_engine_kind() -> str:
    console.print("  This Mac has Apple Silicon. Which program should run the local model?\n")
    console.print("  [bold]1. llama.cpp[/bold]  [dim]GGUF models; the same as on every other machine[/dim]")
    console.print("  [bold]2. MLX[/bold]  [dim]Apple's own framework (mlx_lm.server); usually faster on "
                  "M-series chips and runs the newest models[/dim]\n")
    return "mlx" if _menu_index("Choose the engine", 2) == 1 else "llamacpp"


def _find_mlx_server() -> str:
    dentro = Path(sys.executable).parent / "mlx_lm.server"
    if dentro.is_file():
        return str(dentro)
    return shutil.which("mlx_lm.server") or ""


def _step_mlx() -> tuple[str, str]:
    """(binario, modelo) do MLX. O modelo e baixado pelo proprio mlx_lm na primeira subida."""
    binario = _find_mlx_server()
    if binario:
        console.print(f"  Found mlx_lm.server: [bold]{binario}[/bold]\n")
    else:
        console.print("  mlx_lm.server is not installed.")
        raw = console.input("  Install mlx-lm into this environment now? [Y/n]: ").strip().lower()
        if raw in ("n", "no"):
            return _pedir_binario("  Enter the full path to mlx_lm.server: "), _pedir_modelo_mlx()
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "mlx-lm"], check=True)
            binario = _find_mlx_server()
        except (subprocess.CalledProcessError, OSError) as e:
            console.print(f"  [red]Could not install mlx-lm:[/red] {e}")
        if not binario:
            binario = _pedir_binario("  Enter the full path to mlx_lm.server: ")
        else:
            console.print("  [green]✓[/green] mlx-lm installed.\n")
    return binario, _pedir_modelo_mlx()


def _pedir_modelo_mlx() -> str:
    console.print("  Which model? A folder with MLX weights, or a Hugging Face id "
                  "([dim]org/name[/dim]). It is downloaded the first time the engine starts.")
    console.print("  [dim]Bigger models need a lot of memory (a 27B model in 8 bits needs about 30 GB): "
                  "see docs/INSTALL_MAC_MLX.md.[/dim]\n")
    while True:
        raw = console.input(f"  Model [{MODELO_MLX_PADRAO}]: ").strip() or MODELO_MLX_PADRAO
        pasta = Path(raw).expanduser()
        if pasta.exists():
            return str(pasta)
        if raw.count("/") == 1:
            return raw
        console.print("  [red]Not a folder and not an org/name Hugging Face id. Try again.[/red]\n")


def _step_startup() -> bool:
    system = platform.system()
    methods = {"Linux": "systemd user service", "Darwin": "launchd agent", "Windows": "Task Scheduler"}
    method = methods.get(system, "background service")

    console.print("  Should delegation-core start automatically when you log in?")
    console.print(f"  [dim]Method: {method}. This is the memory server your Claude apps connect to "
                  "(and the local model, if you chose one).[/dim]")
    console.print("  [dim]Without it, nothing answers until you run `delegation-core run` yourself.[/dim]\n")
    raw = console.input("  Auto-start at login? [Y/n]: ").strip().lower()
    result = raw in ("", "y", "yes")
    console.print()
    return result


def _step_features() -> tuple[bool, str, str]:
    """Ask about v0.2 config: synthesis, language, budget mode."""
    console.print("  Configure the v0.2 processing features.\n")

    # Synthesis
    console.print("  [bold]Note synthesis[/bold]")
    console.print("  When enabled, inbox files are converted into structured Obsidian notes")
    console.print("  by the local AI model (sections, frontmatter, bullet points).")
    console.print("  Disable to file raw text directly: faster but less organised.\n")
    raw = console.input("  Enable note synthesis? [Y/n]: ").strip().lower()
    synthesis_enabled = raw not in ("n", "no")
    console.print()

    # Language
    synthesis_lang = "en"
    if synthesis_enabled:
        console.print("  [bold]Synthesis language[/bold]")
        lang_choice = _menu("Choose the language for synthesised notes:", [
            "English (default)",
            "Portuguese (Brazilian)",
        ])
        synthesis_lang = "pt" if lang_choice == 1 else "en"
        console.print()

    # Budget mode
    console.print("  [bold]Budget mode[/bold]")
    console.print("  CPU mode applies strict per-task token caps to stay within MCP timeouts")
    console.print("  on low-power machines (e.g. i9 Mac without GPU offload).")
    console.print("  [dim]normal[/dim] : full-quality outputs (recommended on any GPU machine)")
    console.print("  [dim]cpu[/dim]    : hard caps: classify=8, compress=200, synthesize=2500\n")
    budget_choice = _menu("Select budget mode:", [
        "normal : full quality  [dim](recommended)[/dim]",
        "cpu : strict token caps for low-power machines",
    ])
    budget_mode = "cpu" if budget_choice == 1 else "normal"

    console.print(
        f"\n  [green]✓[/green]  synthesis={'on' if synthesis_enabled else 'off'} ({synthesis_lang})  "
        f"budget={budget_mode}\n"
    )
    return synthesis_enabled, synthesis_lang, budget_mode


#: Medido no Hugging Face em 06/10/2026: o pesos do bge-base-en-v1.5 sao 438 MB
#: (o texto antigo dizia "~110 MB", o numero de parametros e nao o tamanho) e o
#: pytorch_model.bin do bge-m3 e 2,27 GB.
MODELOS_DE_BUSCA = [
    ("BAAI/bge-base-en-v1.5", "~440 MB", "English; the default; light on memory"),
    ("BAAI/bge-m3", "~2.3 GB", "Multilingual, much better for Portuguese and mixed-language notes; "
                               "needs about 3 GB of RAM"),
]


def _step_embedding_model(cfg: Config) -> None:
    """Escolhe o modelo de busca, grava o config e baixa o modelo.

    O wizard nunca perguntava: todo mundo ficava com o modelo em ingles, mesmo com
    o vault em portugues. Trocar depois exige reindexar o vault inteiro.
    """
    conhecidos = [m for m, _, _ in MODELOS_DE_BUSCA]
    if cfg.bge_model in conhecidos:
        console.print("  Which model should power search? Changing it later means re-indexing the "
                      "whole vault.\n")
        recomendado = 1 if getattr(cfg, "synthesis_lang", "en") == "pt" else 0
        for i, (modelo, tamanho, desc) in enumerate(MODELOS_DE_BUSCA):
            marca = "  [yellow]★ recommended for your notes[/yellow]" if i == recomendado else ""
            console.print(f"  [bold]{i + 1}. {modelo}[/bold]  [dim]{tamanho}[/dim]{marca}")
            console.print(f"     [dim]{desc}[/dim]\n")
        cfg.bge_model = MODELOS_DE_BUSCA[_menu_index("Choose the search model", len(MODELOS_DE_BUSCA), recomendado)][0]
        console.print()
    else:
        console.print(f"  Keeping your configured search model: [bold]{cfg.bge_model}[/bold]\n")
    cfg.save()   # antes do download: interromper aqui nao pode perder as respostas
    tamanho = next((t for m, t, _ in MODELOS_DE_BUSCA if m == cfg.bge_model), "")
    _step_bge(cfg.bge_model, tamanho)


def _step_embed_llama(cfg: Config) -> None:
    """Apple Silicon: o BGE roda pelo llama.cpp, ao lado do modelo (MLX), nunca no torch/MPS.

    O torch em MPS e o caminho que ja derrubou o daemon por alocacao de buffer na
    memoria unificada. O GGUF f16 da o mesmo vetor do torch (cosseno 0,99999),
    entao nada precisa ser reindexado. Se a preparacao falhar, o BGE segue no
    torch e o `doctor` diz o comando que falta.
    """
    from . import embed_llama

    item = embed_llama.GGUF_CATALOGO.get(cfg.bge_model)
    if item is None:
        console.print(f"  [yellow]No llama.cpp build is known for {cfg.bge_model}:[/yellow] "
                      "it stays on torch.\n")
        return
    tamanho = f"{item[2] / 1e9:.1f} GB" if item[2] >= 1e9 else f"{item[2] / 1e6:.0f} MB"
    console.print("  On a Mac the search model runs on llama.cpp, next to the MLX model, "
                  "instead of on torch.")
    console.print(f"  [dim]Download: {tamanho} (GGUF f16: the same vectors as torch, so an existing "
                  "index stays valid).[/dim]\n")
    raw = console.input("  Set it up now? [Y/n]: ").strip().lower()
    if raw in ("n", "no"):
        console.print("  Skipped. Run [bold]delegation-core embed-llama setup[/bold] later.\n")
        return
    r = embed_llama.preparar(cfg)
    if r["status"] == "ok":
        console.print(f"  [green]✓[/green] Search model on llama.cpp ({r['dim']}-dim vectors).\n")
    else:
        console.print(f"  [yellow]Could not set it up[/yellow] ({r.get('step', '?')}): {r['detail']}")
        console.print("  Search stays on torch. Fix the cause and run "
                      "[bold]delegation-core embed-llama setup[/bold].\n")


def _step_bge(model_name: str, tamanho: str = ""):
    console.print(f"  Downloading the search embedding model [bold]{model_name}[/bold].")
    if tamanho:
        console.print(f"  [dim]{tamanho} (one-time download. Runs locally forever after).[/dim]\n")
    try:
        from sentence_transformers import SentenceTransformer
        SentenceTransformer(model_name)
        console.print("  [green]✓[/green] Embedding model ready.\n")
    except Exception as e:
        console.print(f"  [yellow]Warning:[/yellow] {e}")
        console.print("  It will download automatically on first use.\n")


def _step_index(cfg: Config):
    from . import daemon
    if daemon.is_listening(cfg):
        # Abrir o indice aqui seria um segundo escritor ao lado do daemon: a
        # sequencia que ja corrompeu um indice em campo.
        console.print("  A delegation-core daemon is already running and owns the index, so it is "
                      "not opened a second time here.")
        console.print("  If you changed the vault or the search model, run "
                      "[bold]delegation-core reindex[/bold] afterwards.\n")
        return
    console.print(f"  Indexing notes in [bold]{cfg.vault_path}[/bold]...")
    console.print("  [dim]A large vault can take several minutes.[/dim]")
    try:
        from .vault import VaultManager
        vault = VaultManager(cfg)
        count = vault.reindex_vault()
        console.print(f"  [green]✓[/green] {count} notes indexed and searchable.\n")
    except Exception as e:
        console.print(f"  [yellow]Warning:[/yellow] Could not build index: {e}")
        console.print("  Run [bold]delegation-core reindex[/bold] after setup to fix this.\n")


# ── startup configuration ─────────────────────────────────────────────────────

def _setup_startup(cfg: Config):
    if cfg.is_agent_mode or not cfg.llama_binary or not cfg.llama_model:
        console.print("  [dim]Agent mode (no local model): skipping background engine service.[/dim]\n")
        return
    if getattr(cfg, "motor_e_mlx", False):
        # O servico do llama.cpp rodaria o mlx_lm.server com --ctx-size e --n-gpu-layers,
        # que ele recusa. O daemon sobe o mlx_lm.server sozinho quando precisa.
        console.print("  [dim]MLX engine: the server starts it when needed, so no separate "
                      "engine service.[/dim]\n")
        return
    system = platform.system()
    console.print("  Configuring background startup...")
    try:
        if system == "Linux":
            _startup_systemd(cfg)
        elif system == "Darwin":
            _startup_launchd(cfg)
        elif system == "Windows":
            _startup_task_scheduler(cfg)
        console.print("  [green]✓[/green] AI engine will start automatically at login.\n")
    except Exception as e:
        console.print(f"  [yellow]Warning:[/yellow] Could not configure auto-start: {e}\n")


def _systemd_literal(value) -> str:
    """A user-controlled path as a systemd unit file reads it, not as we meant it.

    `%` opens a specifier in a unit file, and the escape for a literal one is
    `%%`. The paths interpolated below are chosen by the person running setup,
    and `%` is a perfectly ordinary character in a directory name.

    Measured on 2026-09-03, with the unit actually loaded and
    `systemctl show -p ExecStart` asked what it understood::

        written : ExecStart="/home/joey/100%hits/llama-server"
                    --model "/data/%name%.gguf"
        loaded  : path=/home/joey/100/home/joeyits/llama-server
                  argv[]=... --model /data/<unit name>ame%.gguf

    `%h` became the home directory and `%n` the unit name. The service then
    points at a path that does not exist, the engine never starts at login, and
    setup has already printed "AI engine will start automatically at login".

    The quoting one line down was added for the same reason — a space in any of
    these paths splits the command — so the hostility of these values was
    already known here. This is the second metacharacter, not a new idea.
    """
    return str(value).replace("%", "%%")


def _startup_systemd(cfg: Config):
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)

    service = (
        "[Unit]\n"
        "Description=llama.cpp server for delegation-core\n"
        "After=graphical-session.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        # ExecStart= uses systemd's own shell-like word splitting on
        # whitespace, paths must be quoted or a space anywhere in the home
        # directory, models dir, or binary path (all user-controlled) splits
        # into the wrong number of arguments. `%` needs _systemd_literal for
        # the same reason, one layer down: see its docstring.
        f'ExecStart="{_systemd_literal(cfg.llama_binary)}"'
        f' --model "{_systemd_literal(cfg.llama_model)}"'
        f" --port {cfg.llama_port}"
        f" --ctx-size {cfg.llama_ctx}"
        f" --n-gpu-layers {cfg.llama_ngl}\n"
        "Restart=on-failure\n"
        "RestartSec=10\n"
        f"StandardOutput=append:{_systemd_literal(cfg.llama_log_path)}\n"
        f"StandardError=append:{_systemd_literal(cfg.llama_log_path)}\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )

    # Name and path both come from service.py, which is where the uninstaller
    # reads them too. They used to be spelled out independently in five files.
    from . import service as _svc
    service_file = _svc.LLAMA_SYSTEMD_UNIT
    # encoding explicito, como service.py ja faz para a unit DELE. Sem ele
    # o Python usa locale.getpreferredencoding(): medido sob LC_ALL=C, um
    # caminho com acento levanta UnicodeEncodeError e o usuario recebe
    # "Could not configure auto-start" em vez do motor no login.
    service_file.write_text(service, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", _svc.LLAMA_SERVICE_NAME], check=True)


def _startup_launchd(cfg: Config):
    from . import service as _svc
    _LLAMA_LABEL = _svc.LLAMA_LAUNCHD_LABEL
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    # Um `&`, `<` ou `>` num caminho e legal no macOS e ILEGAL cru em XML: sem
    # escape o plist sai malformado, `launchctl load` recusa, e o motor nunca
    # sobe. Medido em 03/09/2026 com "/Users/joey/Documents/AI & ML/llama-server":
    # "not well-formed (invalid token): line 5, column 38".
    # E o mesmo problema do `%` do systemd na funcao acima, no formato vizinho:
    # valor escolhido pelo usuario interpolado cru num formato que da significado
    # a alguns caracteres.
    esc = xml_escape

    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"'
        ' "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        f'  <key>Label</key><string>{esc(_LLAMA_LABEL)}</string>\n'
        '  <key>ProgramArguments</key>\n'
        '  <array>\n'
        f'    <string>{esc(str(cfg.llama_binary))}</string>\n'
        f'    <string>--model</string><string>{esc(str(cfg.llama_model))}</string>\n'
        f'    <string>--port</string><string>{cfg.llama_port}</string>\n'
        f'    <string>--ctx-size</string><string>{cfg.llama_ctx}</string>\n'
        f'    <string>--n-gpu-layers</string><string>{cfg.llama_ngl}</string>\n'
        '  </array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '  <key>KeepAlive</key><true/>\n'
        f'  <key>StandardOutPath</key><string>{esc(str(cfg.llama_log_path))}</string>\n'
        f'  <key>StandardErrorPath</key><string>{esc(str(cfg.llama_log_path))}</string>\n'
        '</dict></plist>\n'
    )

    plist_file = _svc.LLAMA_LAUNCHD_PLIST
    plist_file.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "load", str(plist_file)], check=True)


def _startup_task_scheduler(cfg: Config):
    from . import service as _svc
    cmd_str = (
        f'"{cfg.llama_binary}" --model "{cfg.llama_model}"'
        f' --port {cfg.llama_port} --ctx-size {cfg.llama_ctx}'
        f' --n-gpu-layers {cfg.llama_ngl}'
    )
    subprocess.run(
        ["schtasks", "/create",
         "/tn", _svc.LLAMA_SERVICE_NAME,
         "/tr", cmd_str,
         "/sc", "ONLOGON",
         "/rl", "HIGHEST",
         "/f"],
        check=True, capture_output=True,
    )
    subprocess.run(["schtasks", "/run", "/tn", _svc.LLAMA_SERVICE_NAME], capture_output=True)


# ── completion ────────────────────────────────────────────────────────────────

# ── daemon e clientes ─────────────────────────────────────────────────────────

def _clientes_detectados() -> list[tuple[str, str, str]]:
    """(chave, rotulo, arquivo) dos clientes MCP que ja existem nesta maquina."""
    from . import clients
    casa = Path.home()
    achados = []
    if (casa / ".claude.json").exists() or (casa / ".claude").is_dir() or shutil.which("claude"):
        achados.append(("claude_code", "Claude Code", "~/.claude.json"))
    desktop = clients.claude_desktop_config_path()
    if desktop.parent.is_dir():
        achados.append(("claude_desktop", "Claude Desktop", str(desktop)))
    if (casa / ".codex").is_dir():
        achados.append(("codex", "Codex", "~/.codex/config.toml"))
    if (casa / ".gemini").is_dir():
        achados.append(("antigravity", "Antigravity / Gemini CLI", str(clients.ANTIGRAVITY_CONFIG)))
    return achados


STATUS_CLIENTE_OK = ("installed", "updated", "created", "already-configured", "already_present")

_INSTALADOR_DO_CLIENTE = {
    "claude_code": "install_claude_code",
    "claude_desktop": "install_claude_desktop",
    "codex": "install_codex",
    "antigravity": "install_antigravity",
}


def _step_connect(cfg: Config, auto_start: bool) -> dict:
    """Registra o daemon e liga os clientes MCP que ja existem na maquina.

    O wizard nunca fez isto. Numa instalacao nova o `post-install` entrega ao
    wizard e para ali (o servico do daemon e a configuracao dos clientes so
    rodam quando ja ha config.json), e o wizard so registrava o servico do
    llama.cpp. Medido em 06/10/2026 num HOME limpo: depois de um wizard completo
    nao existia unit, nem ~/.claude.json, nem daemon. A tela final ainda
    mandava colar `"args": ["run"]`, o formato que faz cada cliente subir o seu
    proprio daemon, brigando pela porta, pelo indice e pela GPU.
    """
    from . import clients, service

    resultado: dict = {"daemon": "not_registered", "clients": {}, "hooks": None}

    # O token nasce aqui, antes do daemon e dos clientes. Se so o daemon o gerasse
    # (`ensure_server_token` no startup), os clientes gravados por este passo
    # levariam `Bearer ` vazio e todo pedido seria recusado com 401.
    cfg.ensure_server_token()

    if auto_start:
        ja_no_ar = service.is_up()
        console.print("  Registering the server to start at login...")
        try:
            r = service.install()
        except Exception as e:  # noqa: BLE001 - o wizard nao pode morrer aqui
            r = {"status": "error", "detail": str(e)}
        if r.get("status") not in ("installed", "written_but_not_started"):
            resultado["daemon"] = "registration_failed"
            console.print(f"  [yellow]Warning:[/yellow] could not register the service "
                          f"({r.get('status')}): {r.get('detail') or r.get('hint') or ''}")
            console.print("  Start it by hand with [bold]delegation-core run[/bold], or fix the cause "
                          "and run [bold]delegation-core service install[/bold].\n")
        else:
            if ja_no_ar:
                raw = console.input("  A server is already running with the old settings. "
                                    "Restart it to apply the new ones? [Y/n]: ").strip().lower()
                if raw in ("", "y", "yes"):
                    service.restart()
            console.print("  Waiting for the server to answer "
                          "(the first start loads the search model: up to 90 s)...")
            if service.is_up(wait_seconds=90):
                resultado["daemon"] = "running"
                console.print(f"  [green]✓[/green] Server running at {cfg.server_url}\n")
            else:
                resultado["daemon"] = "not_answering"
                console.print("  [yellow]Registered, but not answering yet.[/yellow] "
                              "Look at ~/.delegation_core/server.log\n")
        _setup_startup(cfg)
    else:
        console.print("  Auto-start skipped. Start the server whenever you need it with "
                      "[bold]delegation-core run[/bold].\n")

    achados = _clientes_detectados()
    if not achados:
        console.print("  No Claude app found on this machine yet. When you install one, connect it with "
                      "[bold]delegation-core clients[/bold].\n")
        return resultado

    console.print("  Found on this machine:")
    for _, rotulo, onde in achados:
        console.print(f"    - {rotulo}  [dim]{onde}[/dim]")
    console.print("  [dim]Each entry is written in the shape that client needs, with a one-time backup "
                  "of its config. Other servers you already have are kept.[/dim]\n")
    raw = console.input("  Connect delegation-core to these now? [Y/n]: ").strip().lower()
    if raw in ("n", "no"):
        console.print("  Skipped. Run [bold]delegation-core clients[/bold] when you want to.\n")
        return resultado

    for chave, rotulo, _ in achados:
        try:
            r = getattr(clients, _INSTALADOR_DO_CLIENTE[chave])(cfg)
        except Exception as e:  # noqa: BLE001
            r = {"status": "error", "detail": str(e)}
        resultado["clients"][chave] = r.get("status", "?")
        marca = "[green]✓[/green]" if r.get("status") in STATUS_CLIENTE_OK \
            else "[yellow]![/yellow]"
        console.print(f"  {marca} {rotulo}: {r.get('status')}"
                      + (f" ({r.get('detail')})" if r.get("detail") and r.get("status") == "error" else ""))
        if chave == "claude_code":
            try:
                resultado["hooks"] = clients.register_session_hooks().get("status")
                console.print(f"  {marca} Claude Code session hooks: {resultado['hooks']}")
            except Exception as e:  # noqa: BLE001
                resultado["hooks"] = "error"
                console.print(f"  [yellow]![/yellow] Claude Code session hooks: {e}")
    console.print()
    return resultado


def _completion(cfg: Config, conexao: dict | None = None):
    conexao = conexao or {}
    agent_guide = CONFIG_DIR / "AGENT_GUIDE.md"
    system_prompt = CONFIG_DIR / "CLAUDE_SYSTEM_PROMPT.md"

    estado_do_daemon = {
        "running": f"[green]running[/green] at {cfg.server_url}",
        "not_answering": "registered, [yellow]not answering yet[/yellow] (see ~/.delegation_core/server.log)",
        "registration_failed": "[yellow]could not be registered[/yellow]: run it with `delegation-core run`",
        "not_registered": "not registered to start at login: run it with `delegation-core run`",
    }.get(conexao.get("daemon", "not_registered"), "unknown")
    ligados = [k.replace("_", " ").title() for k, v in (conexao.get("clients") or {}).items()
               if v in STATUS_CLIENTE_OK]

    console.print(Panel.fit(
        "[bold green]Setup complete![/bold green]\n\n"
        f"Server: {estado_do_daemon}\n"
        f"Connected: {', '.join(ligados) if ligados else 'no Claude app yet: run `delegation-core clients`'}",
        border_style="green",
    ))

    console.print()
    console.print("  [bold]What is left[/bold]")
    console.print()
    console.print("  [bold]1. Reconnect your Claude apps[/bold]")
    console.print("     Restart Claude Desktop. In Claude Code, type [cyan]/mcp[/cyan] and reconnect "
                  "delegation-core.")
    console.print()
    console.print("  [bold]2. Claude Code: load the agent protocol every session[/bold]")
    console.print("     Add this to [cyan]~/.claude/CLAUDE.md[/cyan] (create it if missing).")
    console.print()
    console.print(Panel(
        "# delegation-core\n\n"
        "Follow this protocol whenever delegation-core's MCP tools are available:\n\n"
        f"@{agent_guide}",
        title="[bold]~/.claude/CLAUDE.md[/bold]", border_style="blue"))
    console.print()
    console.print("  [bold]3. Claude Desktop / Cowork: load the agent protocol[/bold]")
    console.print("     There's no config file for this: open Claude Desktop's")
    console.print("     [cyan]Settings → Custom Instructions[/cyan] (and/or each Cowork project's")
    console.print("     instructions) and paste the contents of:")
    console.print(f"       [bold]{system_prompt}[/bold]")
    console.print()
    console.print("  Verify everything is working:")
    console.print("    [bold]delegation-core status[/bold]")
    console.print("    [bold]delegation-core doctor[/bold]")
    console.print("    and, inside Claude, ask for [bold]heartbeat()[/bold]\n")


# ── helpers ───────────────────────────────────────────────────────────────────

def _welcome():
    console.print()
    console.print(Panel.fit(
        "[bold cyan]delegation-core[/bold cyan]  setup\n"
        "[dim]Local AI for Claude · takes about 5 minutes[/dim]",
        border_style="cyan",
        padding=(1, 4),
    ))
    console.print()


def _header(step: str, title: str):
    console.print()
    console.print(Rule(f"[bold]{step} : {title}[/bold]", style="cyan"))
    console.print()


def _menu(title: str, options: list) -> int:
    console.print(f"  {title}\n")
    for i, opt in enumerate(options, 1):
        console.print(f"    [bold cyan]{i}[/bold cyan]  {opt}")
    console.print()
    while True:
        raw = console.input(f"  Enter number [1-{len(options)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        console.print(f"  [red]Please enter a number between 1 and {len(options)}.[/red]")


def _menu_index(prompt: str, count: int, padrao: int | None = None) -> int:
    """Indice base zero da escolha. `padrao` (base zero) e o que o Enter aceita."""
    dica = f", Enter = {padrao + 1}" if padrao is not None else ""
    while True:
        raw = console.input(f"  {prompt} [1-{count}{dica}]: ").strip()
        if raw == "" and padrao is not None:
            return padrao
        if raw.isdigit() and 1 <= int(raw) <= count:
            return int(raw) - 1
        console.print(f"  [red]Please enter a number between 1 and {count}.[/red]")


