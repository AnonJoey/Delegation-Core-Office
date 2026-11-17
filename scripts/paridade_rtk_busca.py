"""Paridade do porte de `grep` e `rg` (search.rs) com o binario real do RTK.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk_busca.py [-n CASOS] [--so grep|rg] [-v]

Monta uma arvore de arquivos com o que costuma quebrar um agrupador de busca (linhas
longas, UTF-8, CRLF, nomes com `:`, `-` e espaco, binario, Latin-1, mais de 200
resultados, caminho com mais de 50 bytes, arquivo escondido e ignorado), sorteia
comandos de grep e rg com flags, padroes, caminhos e entrada padrao, e roda cada um no
`rtk grep|rg` real e no porte (em outro processo, com a mesma entrada). stdout,
stderr e codigo de saida tem que ser iguais, byte a byte.

A entrada padrao e sorteada entre /dev/null (o caminho que agrupa), um pipe com
dados e um arquivo comum (os dois ultimos fazem o motor ler a entrada e entram no
caminho que reescreve linha a linha).

O rg paraleliza e nao fixa a ordem dos arquivos; por isso a maioria dos casos do rg leva
`--sort=path`. Nos que nao levam, e com mais de um arquivo, as linhas sao comparadas sem
ordem (o agrupado, que ordena por arquivo, continua conferido nos outros).
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

FLAGS_GREP = [[], [], ["-r"], ["-rn"], ["-n"], ["-i"], ["-rin"], ["-w"], ["-F"], ["-E"], ["-v"], ["-H"], ["-h"], ["-rh"],
              ["-c"], ["-l"], ["-L"], ["-o"], ["-q"], ["-s"], ["-A2"], ["-B1"], ["-C2"], ["-3"], ["-A", "1"],
              ["--context=2"], ["-m2"], ["-m", "1"], ["--max-count=3"], ["--include=*.py"], ["--exclude-dir=docs"],
              ["--color=always"], ["--color=never"], ["-a"], ["-I"], ["-z"], ["-Z"], ["-b"], ["--line-number"],
              ["--no-filename"], ["--with-filename"], ["--initial-tab"], ["-T"], ["--recursive"], ["-R"], ["-nr"],
              ["-rl"], ["-rc"], ["-rA2"], ["-rnC1"], ["-x"], ["-P"]]
FLAGS_RG = [[], [], ["-n"], ["-N"], ["-i"], ["-w"], ["-F"], ["-v"], ["-A2"], ["-B1"], ["-C2"], ["-c"], ["-l"],
            ["--files"], ["-o"], ["-t", "py"], ["-g", "*.py"], ["--glob=!docs"], ["-m2"], ["-uu"], ["-I"],
            ["--no-heading"], ["--heading"], ["--color=always"], ["--no-line-number"], ["-H"], ["--with-filename"],
            ["-r", "X"], ["-U"], ["--type-list"], ["--max-depth=1"], ["-L"], ["-z"], ["--hidden"],
            ["-S"], ["-s"], ["--column"], ["--vimgrep"], ["-nH"], ["-An"], ["-C1"], ["--context=1"], ["-e", "bar"]]
PADROES = ["foo", "foo", "foo", "Foo", "bar|baz", "o+", "zzzznomatch", "a:b", "key: foo", "é", "\\bfoo\\b", "e", ".",
           "", "fo*", "^def", "foo$", "[0-9]+", "foo-bar", "ao", "x"]
CAMINHOS = [[], [], ["."], ["src"], ["src/a.py"], ["src/a.py", "src/b.py"], ["docs"], ["many"], ["big.txt"], ["nofile.txt"],
            ["src", "docs"], ["-"], ["empty.txt"], ["weird:name.txt"], ["bin.dat"], ["latin1.txt"], ["ignored"],
            [".hid"], ["pats.txt"], ["src/deep"], ["many", "big.txt"]]
ENTRADA = ["x foo y\nsem\nfoo foo\n", "foo\r\nbar\r\n", "nada\n", "a:1:foo\nb-2-foo\n", "", "sem quebra foo"]


def montar_arvore(raiz: Path) -> None:
    def w(nome: str, dados: str | bytes) -> None:
        p = raiz / nome
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(dados if isinstance(dados, bytes) else dados.encode())

    linhas = ["def foo_i():", "    return foo + bar", "x = 'Foo'", "# baz e foo juntos", "key: foo - valor", "a:b foo",
              "é foo ção", "emoji \U0001F600 foo", "\tfoo com tab", "   foo indentado",
              "foo no inicio" + " x" * 60, "x " * 60 + "foo no meio" + " y" * 60, "z " * 70 + "foo", "nada aqui", "", "bar so",
              "foo-bar e foo:bar", "123 foo 456", "foo" * 30]
    w("src/a.py", "\n".join(linhas * 2) + "\n")
    w("src/b.py", "\r\n".join(["foo crlf", "bar crlf", "baz foo"]) + "\r\n")
    w("src/deep/er/than/fifty/characters/in/the/path/to/file.py", "foo funda\nbar\nfoo\n")
    w("docs/x.md", "# titulo\nfoo em docs\nbar\n")
    w("docs/y md.txt", "foo com espaco no nome\n")
    w("big.txt", "".join(f"linha {i} foo\n" if i % 3 else f"linha {i}\n" for i in range(450)))
    for i in range(70):
        w(f"many/f{i:03d}.txt", "".join(f"foo {i} {j}\n" for j in range(5)))
    w("weird:name.txt", "foo dentro\nbar\n")
    w("dash-name.txt", "foo-dash\n")
    w("bin.dat", b"foo\x00\x01\x02bar\nfoo outra\n")
    w("latin1.txt", b"foo \xe7\xe3o\nbar\n")
    w("empty.txt", b"")
    w(".hid/z.txt", "foo escondido\n")
    w(".ignore", "ignored/\n")
    w("ignored/i.txt", "foo ignorado\n")
    w("pats.txt", "foo\nbaz\n")
    w("contexto.txt", "".join(f"l{i}\n" if i not in (3, 4, 10, 30) else f"l{i} foo\n" for i in range(40)))


def sortear(r: random.Random, motor: str):
    pool = FLAGS_GREP if motor == "grep" else FLAGS_RG
    flags = [a for _ in range(r.choice([0, 1, 1, 2, 3])) for a in r.choice(pool)]
    if motor == "rg" and r.random() < .75:
        flags.insert(0, "--sort=path")
    padrao = r.choice(PADROES)
    caminhos = r.choice(CAMINHOS)
    forma = r.random()
    if r.random() < .05:
        # O clap do RTK toma `--help`, `-h` e `--version` que vierem antes do primeiro posicional;
        # depois dele, passam para o motor.
        ajuda = ["--help", "--version"] + (["-h"] if motor == "rg" else [])
        return [padrao, *caminhos, r.choice(ajuda)], "null", ""
    if any(f in ("-h", "-rh", "-hr") for f in flags):
        forma = .15   # o `-h` do grep antes do primeiro posicional e o `--help` do clap do RTK
    if forma < .08:
        args = flags + ["-e", padrao, *caminhos]
    elif forma < .12:
        args = flags + ["-f", "pats.txt", *caminhos]
    elif forma < .2:
        args = [padrao, *caminhos, *flags]
    elif forma < .25:
        args = flags + ["--", padrao, *caminhos]
    elif forma < .28:
        args = flags
    else:
        args = flags + [padrao, *caminhos]
    if motor == "rg" and any(a in args for a in ("--files", "--type-list", "--version")):
        args = [a for a in args if a != padrao or a in flags]
    tipo = r.choices(["null", "pipe", "arquivo"], weights=[70, 20, 10])[0]
    if tipo != "null" and r.random() < .6:
        # Sem caminho (ou com `-`) e com entrada legivel, o motor le a entrada: o caminho de streaming.
        sufixo = r.choice([[], ["-"]])
        args = [padrao, *sufixo, *flags] if any(f in ("-h", "-rh", "-hr") for f in flags) else flags + [padrao, *sufixo]
    return args, tipo, r.choice(ENTRADA)


def ambiente(casa: Path) -> dict:
    casa.mkdir(exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "HOME": str(casa), "NO_COLOR": "1", "RTK_NO_TRACK": "1", "LC_ALL": "C.UTF-8",
            "TERM": "dumb", "XDG_DATA_HOME": str(casa / "share"), "XDG_CONFIG_HOME": str(casa / "config")}


def rodar(argv: list[str], tipo: str, entrada: str, cwd: Path, env: dict, arq: Path):
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


def aplicar_mutacao(search, Ambiente) -> None:
    """`PARIDADE_MUTACAO=nome`: injeta um defeito conhecido no porte, para ver o oraculo acusar."""
    nome = os.environ.get("PARIDADE_MUTACAO")
    if not nome:
        return
    mutacoes = {
        "teto de resultados": lambda: setattr(search, "MAX_RESULTS", 199),
        "teto por arquivo": lambda: setattr(search, "GREP_MAX_PER_FILE", 24),
        "janela da linha longa": lambda: setattr(search, "MAX_LINE_LEN", 79),
        "caminho compacto": lambda: setattr(search, "compact_path", lambda p: p),
        "dobra da lista": lambda: setattr(search, "fold_path_prefix", lambda b: None),
        "sinal de nao lido": lambda: setattr(search, "unparsed_signal", lambda b: 0),
        "recursivo": lambda: setattr(search, "is_recursive_token", lambda e, k, t: False),
        "contexto": lambda: setattr(search, "is_context_token", lambda e, k, t: False),
        "slug da dica": lambda: setattr(search, "grep_slug", lambda i, p: f"grep_{i}"),
        "entrada legivel": lambda: setattr(Ambiente, "stdin_legivel", lambda self: False),
        "flag de formato": lambda: setattr(search, "is_format_flag_token", lambda e, k, t: False),
        "nao mostra arquivo": lambda: setattr(search, "wants_show_file", lambda p, f, a: False),
        "negacao do arquivo": lambda: setattr(search, "is_show_file_off_token", lambda e, k, t: False),
    }
    mutacoes[nome]()


def driver() -> int:
    """O porte, em outro processo: `paridade_rtk_busca.py --porte grep|rg ARGS...`."""
    sys.path.insert(0, str(RAIZ / "src"))
    from delegation_core.filtros_saida.modulos import base
    from delegation_core.filtros_saida.modulos.ambiente import Ambiente
    from delegation_core.filtros_saida.modulos.system import search
    base.PREFIXO = "rtk"
    aplicar_mutacao(search, Ambiente)
    amb = Ambiente()
    codigo = search.rodar(sys.argv[3:], amb, comando=sys.argv[2])
    amb.flush()
    return codigo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=400, help="casos por motor")
    ap.add_argument("--so", choices=["grep", "rg"])
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    total = ok = 0
    falhas = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        arvore = t / "arvore"
        montar_arvore(arvore)
        env_rtk, env_porte = ambiente(t / "casa-rtk"), ambiente(t / "casa-porte")
        if os.environ.get("PARIDADE_MUTACAO"):
            env_porte["PARIDADE_MUTACAO"] = os.environ["PARIDADE_MUTACAO"]
        for motor in ("grep", "rg"):
            if a.so and a.so != motor:
                continue
            for semente in range(a.n):
                r = random.Random(f"{motor}{semente}")
                args, tipo, entrada = sortear(r, motor)
                esperado = rodar([RTK, motor, *args], tipo, entrada, arvore, env_rtk, t / "entrada-rtk")
                obtido = rodar([sys.executable, str(Path(__file__).resolve()), "--porte", motor, *args], tipo, entrada,
                               arvore, env_porte, t / "entrada-porte")
                total += 1
                sem_ordem = motor == "rg" and not any(x.startswith("--sort") for x in args)
                if sem_ordem:
                    igual = (sorted(esperado[0].splitlines()) == sorted(obtido[0].splitlines())
                             and esperado[1:] == obtido[1:])
                else:
                    igual = esperado == obtido
                if igual:
                    ok += 1
                    if a.v:
                        print(f"ok   {motor} {args} [{tipo}]")
                    continue
                falhas.append((motor, args, tipo))
                print(f"DIFF {motor} {args} [{tipo}] entrada={entrada[:30]!r}")
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
