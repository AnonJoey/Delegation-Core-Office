"""Paridade dos modulos `system` simples do RTK (wc, ls) com o binario real.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk_sistema.py [-n CASOS] [--so wc|ls] [-v]

Cada comando roda no `rtk <comando>` real e no porte (em outro processo, pelo mesmo caminho do
`delegation-core shell`: `modulos.rodavel`), sobre uma arvore com o que costuma quebrar um leitor
de `ls -l` e de `wc`: nomes com espaco e UTF-8, datas recentes e antigas, links, FIFO, setuid e
sticky, arquivos de 2 MiB, pastas de ruido, mais de 50 entradas e diretorio vazio. stdout, stderr
e codigo de saida tem que ser iguais, byte a byte. Para o `wc` a entrada padrao e sorteada entre
/dev/null, pipe e arquivo comum.

`PARIDADE_MUTACAO=nome` injeta um defeito conhecido no porte, para ver o oraculo acusar.
"""

from __future__ import annotations

import argparse
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RTK = os.environ.get("RTK_BIN", "rtk")
AVISO_DO_RTK = b"[rtk] /!\\ No hook installed"
ANTIGO = 1_500_000_000   # 2017: o ls mostra o ano em vez da hora

FLAGS_LS = [[], [], [], ["-l"], ["-a"], ["-la"], ["-A"], ["-lh"], ["-t"], ["-S"], ["-r"], ["-R"], ["--color=always"], ["-1"],
            ["-d"], ["-F"], ["-i"], ["-s"], ["-p"], ["-n"], ["-o"], ["-g"], ["--full-time"], ["--format=long"],
            ["--sort=size"], ["-lt"], ["-ltr"], ["-X"], ["--group-directories-first"], ["-U"], ["-v"], ["--all"],
            ["--almost-all"], ["-lA"], ["-alh"], ["--human-readable"], ["-b"], ["-Q"], ["--time-style=long-iso"],
            ["-l", "-t", "-r"], ["-la", "--color=never"], ["--hide=*.txt"], ["-I", "*.md"], ["--author"]]
CAMINHOS_LS = [[], [], ["."], ["src"], ["many"], ["ruido"], ["vazio"], ["src/a.py"], ["nao-existe"], ["src", "docs"],
               ["especiais"], ["docs"], [".", "src"], ["many", "ruido"], ["grandes"]]
FLAGS_WC = [[], [], ["-l"], ["-w"], ["-c"], ["-m"], ["-L"], ["-lw"], ["-lwc"], ["-cl"], ["--lines"], ["--bytes"], ["--words"],
            ["--chars"], ["--total=only"], ["--total=never"], ["--total=always"], ["-l", "-w"], ["-lm"], ["-wc"],
            ["--max-line-length"], ["--files0-from=lista0"]]
CAMINHOS_WC = [["src/a.py"], ["src/a.py", "src/b.py"], ["src/a.py", "docs/x.md", "big.txt"], ["many/f001.txt", "many/f002.txt"],
               ["nao-existe"], ["src"], ["src/a.py", "nao-existe"], ["vazio.txt"], ["sem-quebra.txt"], ["utf8.txt", "src/a.py"],
               ["-"], [], [], ["src/a.py", "src/a.py"], ["/etc/hostname"], ["many/f001.txt", "src/a.py", "docs/x.md"]]
ENTRADA = ["um dois\ntres\n", "", "sem quebra", "a b c\n" * 50, "éção\n"]


def montar(raiz: Path) -> None:
    def w(nome: str, dados: str | bytes, antigo: bool = False) -> Path:
        p = raiz / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados if isinstance(dados, bytes) else dados.encode())
        if antigo:
            os.utime(p, (ANTIGO, ANTIGO))
        return p

    w("src/a.py", "".join(f"linha {i} foo\n" for i in range(30)))
    w("src/b.py", "def f():\n    pass\n", antigo=True)
    w("docs/x.md", "# titulo\ntexto com mais palavras aqui\n")
    w("big.txt", "palavra " * 5000 + "\n")
    w("utf8.txt", "éção \U0001F600 texto\nsegunda linha\n")
    w("sem-quebra.txt", "sem quebra no fim")
    w("vazio.txt", b"")
    (raiz / "vazio").mkdir(exist_ok=True)
    for i in range(70):
        w(f"many/f{i:03d}.txt", "x" * (i * 37), antigo=i % 3 == 0)
    for ruido in ("node_modules", ".git", "target", "__pycache__", "dist", "build", ".venv", "venv", "env", ".idea",
                  "coverage", ".cache", ".env", ".DS_Store", "app.egg-info", ".eggs", ".vs", ".nyc_output", "*.egg-info",
                  "Thumbs.db", ".turbo", ".vercel", ".next", ".tox", ".mypy_cache", ".pytest_cache", ".vscode"):
        w(f"ruido/{ruido}/x", "r")
    w("ruido/real.txt", "real")
    w("ruido/.hidden", "h")
    w("especiais/com espaco.txt", "e")
    w("especiais/ção \U0001F600.txt", "u")
    w("especiais/exec.sh", "#!/bin/sh\n").chmod(0o755)
    w("especiais/setuid", "s").chmod(0o4755)
    w("especiais/setgid", "s").chmod(0o2755)
    w("especiais/so-leitura", "r").chmod(0o444)
    w("especiais/sem-permissao", "n").chmod(0o000)
    (raiz / "especiais" / "sticky").mkdir(exist_ok=True)
    (raiz / "especiais" / "sticky").chmod(0o1777)
    (raiz / "especiais" / "link").symlink_to("com espaco.txt")
    (raiz / "especiais" / "link-quebrado").symlink_to("nao-existe")
    os.mkfifo(raiz / "especiais" / "fifo")
    for nome, tam in (("kilo", 5000), ("mega", 2 * 1024 * 1024), ("exato-kilo", 1024), ("exato-mega", 1024 * 1024)):
        with open(raiz / "especiais" / nome, "wb") as f:
            f.truncate(tam)
    for i in range(3):
        w(f"grandes/g{i}.bin", b"\0" * (i * 700_000))
    w("lista0", b"src/a.py\0src/b.py\0")


def sortear(r: random.Random, cmd: str):
    if cmd == "ls":
        flags = [a for _ in range(r.choice([0, 1, 1, 2])) for a in r.choice(FLAGS_LS)]
        return flags + r.choice(CAMINHOS_LS), "null", ""
    flags = [a for _ in range(r.choice([0, 1, 1, 2])) for a in r.choice(FLAGS_WC)]
    caminhos = r.choice(CAMINHOS_WC)
    tipo = r.choices(["null", "pipe", "arquivo"], weights=[50, 35, 15])[0]
    return flags + caminhos, tipo, r.choice(ENTRADA)


def ambiente(casa: Path) -> dict:
    casa.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(casa), "NO_COLOR": "1", "RTK_NO_TRACK": "1", "LANG": "C.UTF-8",
            "TERM": "dumb", "XDG_DATA_HOME": str(casa / "share"), "XDG_CONFIG_HOME": str(casa / "config")}


def rodar(argv, tipo, entrada, cwd, env, arq):
    kw: dict = {}
    if tipo == "null":
        kw["stdin"] = subprocess.DEVNULL
    elif tipo == "pipe":
        kw["input"] = entrada.encode()
    else:
        arq.write_text(entrada)
        kw["stdin"] = open(arq, "rb")
    try:
        p = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, timeout=60, **kw)
    finally:
        if tipo == "arquivo":
            kw["stdin"].close()
    return p.stdout, b"".join(l for l in p.stderr.splitlines(keepends=True) if not l.startswith(AVISO_DO_RTK)), p.returncode


def aplicar_mutacao() -> None:
    nome = os.environ.get("PARIDADE_MUTACAO")
    if not nome:
        return
    from delegation_core.filtros_saida.modulos.system import ls, wc
    mutacoes = {
        "wc: modo": lambda: setattr(wc, "detect_mode", lambda a: wc.FULL),
        "wc: prefixo comum": lambda: setattr(wc, "find_common_prefix", lambda p: ""),
        "wc: total": lambda: setattr(wc, "format_multi_line", lambda ls_, m: "\n".join(ls_)),
        "wc: sem stdin": lambda: setattr(wc, "rodar", lambda a, amb: 0),
        "ls: teto": lambda: setattr(ls, "CAP_INVENTORY", 49),
        "ls: ruido": lambda: setattr(ls, "NOISE_DIRS", ls.NOISE_DIRS[:-3]),
        "ls: octal": lambda: setattr(ls, "perms_to_octal", lambda p: "000"),
        "ls: tamanho": lambda: setattr(ls, "human_size", lambda n: f"{n}B"),
        "ls: dica": lambda: setattr(ls, "hidden_hint", lambda c, f: None),
        "ls: flags": lambda: setattr(ls, "argumentos", lambda a: ["-l", *(a or ["."])]),
        "ls: longa": lambda: setattr(ls, "mostra_longa", lambda a: False),
        "ls: pontos": lambda: setattr(ls, "shows_dotfiles", lambda a: False),
    }
    mutacoes[nome]()


def driver() -> int:
    """O porte, em outro processo: `paridade_rtk_sistema.py --porte COMANDO ARGS...`."""
    import shlex
    sys.path.insert(0, str(RAIZ / "src"))
    from delegation_core.filtros_saida import modulos
    from delegation_core.filtros_saida.modulos import base
    from delegation_core.filtros_saida.modulos.ambiente import Ambiente
    base.PREFIXO = "rtk"
    aplicar_mutacao()
    achado = modulos.rodavel(shlex.join(sys.argv[2:]))
    if achado is None:
        sys.stderr.write("modulo nao encontrado\n")
        return 99
    amb = Ambiente()
    codigo = modulos.rodar_modulo(achado, amb)
    amb.flush()
    return codigo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=400, help="casos por comando")
    ap.add_argument("--so", choices=["wc", "ls"])
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    total = ok = 0
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        arvore = t / "arvore"
        montar(arvore)
        env_rtk, env_porte = ambiente(t / "casa-rtk"), ambiente(t / "casa-porte")
        if os.environ.get("PARIDADE_MUTACAO"):
            env_porte["PARIDADE_MUTACAO"] = os.environ["PARIDADE_MUTACAO"]
        for cmd in ("wc", "ls"):
            if a.so and a.so != cmd:
                continue
            for semente in range(a.n):
                r = random.Random(f"{cmd}{semente}")
                args, tipo, entrada = sortear(r, cmd)
                esperado = rodar([RTK, cmd, *args], tipo, entrada, arvore, env_rtk, t / "entrada-rtk")
                obtido = rodar([sys.executable, str(Path(__file__).resolve()), "--porte", cmd, *args], tipo, entrada,
                               arvore, env_porte, t / "entrada-porte")
                total += 1
                if esperado == obtido:
                    ok += 1
                    if a.v:
                        print(f"ok   {cmd} {args} [{tipo}]")
                    continue
                falhas.append((cmd, args, tipo))
                print(f"DIFF {cmd} {args} [{tipo}] entrada={entrada[:30]!r}")
                for rotulo, x, y in (("stdout", esperado[0], obtido[0]), ("stderr", esperado[1], obtido[1]),
                                      ("codigo", esperado[2], obtido[2])):
                    if x != y:
                        print(f"   {rotulo} rtk : {repr(x)[:500]}\n   {rotulo} porte: {repr(y)[:500]}")
    print(f"{ok}/{total} identicos, {len(falhas)} diferentes")
    return 1 if falhas else 0


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--porte":
        raise SystemExit(driver())
    raise SystemExit(main())
