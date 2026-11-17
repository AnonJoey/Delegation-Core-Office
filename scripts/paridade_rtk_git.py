"""Paridade do porte de `git` (status, add, fetch, diff, log, show) com o binario real do RTK.

Uso: RTK_BIN=/caminho/rtk python scripts/paridade_rtk_git.py [-n FUZZ] [--so CENARIO] [-v]

Diferente de mypy, pytest e ruff (que rodam sobre um executavel falso), o git do
RTK consulta o git varias vezes por comando, entao o oraculo e um repositorio de
verdade: cada cenario monta o repositorio (datas fixas, para o `%ar` ser estavel),
roda `rtk git ...` e o porte sobre ele, e compara stdout, stderr e codigo de saida,
byte a byte. Os comandos que mudam o repositorio (`add`, `fetch`) recomecam do
cenario antes de cada lado.

Depois da grade fixa, `-n N` sorteia N combinacoes de flags por subcomando.
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from delegation_core.filtros_saida.modulos import base  # noqa: E402
from delegation_core.filtros_saida.modulos.ambiente import Ambiente  # noqa: E402
from delegation_core.filtros_saida.modulos.git import git  # noqa: E402

RTK = os.environ.get("RTK_BIN", "rtk")
AVISO_DO_RTK = b"[rtk] /!\\ No hook installed"
MUTANTES = ("add", "fetch")


# ── repositorios ─────────────────────────────────────────────────────────────

class Repo:
    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.casa = raiz / "casa"
        self.dir = raiz / "repo"
        self.env = {"PATH": os.environ["PATH"], "HOME": str(self.casa), "LC_ALL": "C", "NO_COLOR": "1",
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(self.casa / "gitconfig"),
                    "RTK_NO_TRACK": "1", "XDG_DATA_HOME": str(self.casa / "share"),
                    "XDG_CONFIG_HOME": str(self.casa / "config"), "TERM": "dumb"}

    def g(self, *args, data: str = "2020-01-01 10:00:00", ok: bool = True, entrada: bytes | None = None):
        env = dict(self.env, GIT_AUTHOR_DATE=data, GIT_COMMITTER_DATE=data)
        p = subprocess.run(["git", *args], cwd=self.dir, env=env, capture_output=True, input=entrada)
        if ok and p.returncode != 0:
            raise RuntimeError(f"git {args}: {p.stderr.decode()}")
        return p

    def escrever(self, nome: str, texto: str | bytes) -> None:
        caminho = self.dir / nome
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(texto if isinstance(texto, bytes) else texto.encode())

    def commit(self, msg: str, corpo: str = "", dia: int = 1) -> None:
        self.g("add", "-A")
        args = ["commit", "-q", "-m", msg] + (["-m", corpo] if corpo else [])
        self.g(*args, data=f"2020-02-{dia:02d} 10:00:00")

    def salvar(self) -> None:
        shutil.rmtree(self.raiz / "snap", ignore_errors=True)
        shutil.copytree(self.dir, self.raiz / "snap", symlinks=True)

    def restaurar(self) -> None:
        shutil.rmtree(self.dir)
        shutil.copytree(self.raiz / "snap", self.dir, symlinks=True)

    def zerar(self) -> None:
        shutil.rmtree(self.raiz, ignore_errors=True)
        self.casa.mkdir(parents=True)
        (self.casa / "gitconfig").write_text("[user]\n\tname = Tester\n\temail = t@example.com\n"
                                              "[init]\n\tdefaultBranch = main\n[advice]\n\tdetachedHead = false\n")
        self.dir.mkdir()
        self.g("init", "-q")


def _historia(r: Repo) -> None:
    r.escrever("README.md", "# projeto\n")
    r.escrever("src/a.py", "".join(f"linha {i}\n" for i in range(40)))
    r.commit("primeiro commit", "corpo do primeiro", 1)
    r.escrever("src/a.py", "".join(f"linha {i}\n" for i in range(40)).replace("linha 5\n", "linha cinco\n"))
    r.commit("ajusta a linha cinco", "", 2)
    r.escrever("src/b.py", "def f():\n    return 1\n")
    r.commit("adiciona b.py\n", "Signed-off-by: Fulano <f@x.y>\nCo-authored-by: Beltrano <b@x.y>\nBREAKING CHANGE: muda f", 3)
    r.g("tag", "v1")
    r.g("checkout", "-q", "-b", "lateral")
    r.escrever("lateral.txt", "so na lateral\n")
    r.commit("trabalho na lateral", "", 4)
    r.g("checkout", "-q", "main")
    r.escrever("src/c.py", "x = 1\n")
    r.commit("c.py na main", "", 5)
    r.g("merge", "-q", "--no-ff", "-m", "mescla a lateral", "lateral", data="2020-02-06 10:00:00")
    for i in range(14):
        r.escrever("src/a.py", "".join(f"linha {j}\n" for j in range(40 + i)))
        r.commit(f"commit numero {i} com um assunto bem comprido para passar de oitenta caracteres sem esforco algum " * (1 + i % 2),
                 "\n".join(f"linha {k} do corpo" for k in range(i % 6)), 7 + i)


def cenario_historia(r: Repo) -> None:
    r.zerar()
    _historia(r)


def cenario_sujo(r: Repo) -> None:
    cenario_historia(r)
    r.escrever("src/a.py", "alterado\n" * 5)
    r.escrever("novo.txt", "novo\n")
    r.escrever("preparado.txt", "p\n")
    r.g("add", "preparado.txt")
    (r.dir / "README.md").unlink()
    r.g("mv", "src/b.py", "src/renomeado.py")
    r.escrever("com espaco/arq x.txt", "x\n")
    r.escrever("acentuação/ção.txt", "x\n")


def cenario_conflito(r: Repo) -> None:
    cenario_historia(r)
    r.g("checkout", "-q", "-b", "c1", "v1")
    r.escrever("README.md", "versao c1\n")
    r.commit("c1", "", 20)
    r.g("checkout", "-q", "main")
    r.escrever("README.md", "versao main\n")
    r.commit("main altera", "", 21)
    r.g("merge", "c1", ok=False)


def cenario_merge_sem_conflito(r: Repo) -> None:
    cenario_historia(r)
    r.g("checkout", "-q", "-b", "c2", "v1")
    r.escrever("c2.txt", "c2\n")
    r.commit("c2", "", 20)
    r.g("checkout", "-q", "main")
    r.g("merge", "--no-commit", "--no-ff", "c2", ok=False)


def cenario_destacado(r: Repo) -> None:
    cenario_historia(r)
    r.g("checkout", "-q", "--detach", "v1")
    r.escrever("solto.txt", "x\n")


def cenario_rebase(r: Repo) -> None:
    cenario_historia(r)
    subprocess.run(["git", "-c", "sequence.editor=sed -i 1s/pick/edit/", "rebase", "-q", "-i", "v1"],
                   cwd=r.dir, env=r.env, capture_output=True)


def cenario_cherry_pick(r: Repo) -> None:
    cenario_historia(r)
    r.g("checkout", "-q", "-b", "cp", "v1")
    r.escrever("README.md", "cp\n")
    r.commit("cp altera", "", 20)
    r.g("checkout", "-q", "main")
    r.escrever("README.md", "main\n")
    r.commit("main altera", "", 21)
    r.g("cherry-pick", "cp", ok=False)


def cenario_bisect(r: Repo) -> None:
    cenario_historia(r)
    r.g("bisect", "start", "HEAD", "v1")


def cenario_grande(r: Repo) -> None:
    cenario_historia(r)
    for i in range(12):
        r.escrever(f"grande/arq{i}.txt", "".join(f"linha {j} do arquivo {i}\n" for j in range(150)))
    r.commit("muitos arquivos", "", 30)
    for i in range(12):
        r.escrever(f"grande/arq{i}.txt", "".join(f"nova {j} do arquivo {i}\n" for j in range(150)))
    r.escrever("grande/x y/dentro.txt", "x\n")
    r.g("add", "-N", "grande/x y/dentro.txt")


def cenario_blobs(r: Repo) -> None:
    cenario_historia(r)
    r.escrever("grande.txt", "".join(f"linha numero {i} do arquivo grande, com texto de enchimento\n" for i in range(400)))
    r.escrever("pequeno.txt", "so uma linha\n")
    r.escrever("latin1.txt", "acentua\xe7\xe3o\n".encode("latin-1") * 2000)
    r.escrever("bin.dat", bytes(range(256)) * 50)
    r.escrever("sem-quebra.txt", "x" * 20000)
    r.commit("blobs", "", 30)
    r.escrever("grande.txt", "alterado\n")


def cenario_remoto(r: Repo) -> None:
    cenario_historia(r)
    origem = r.raiz / "origem"
    shutil.rmtree(origem, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", "--bare", str(r.dir), str(origem)], env=r.env, check=True)
    r.g("remote", "add", "origin", str(origem))
    r.g("fetch", "-q", "origin")
    clone = r.raiz / "outro"
    shutil.rmtree(clone, ignore_errors=True)
    subprocess.run(["git", "clone", "-q", str(origem), str(clone)], env=r.env, check=True)
    envc = dict(r.env, GIT_AUTHOR_DATE="2020-03-01 10:00:00", GIT_COMMITTER_DATE="2020-03-01 10:00:00")
    (clone / "n.txt").write_text("n\n")
    for args in (["add", "n.txt"], ["commit", "-q", "-m", "do outro"], ["checkout", "-q", "-b", "nova-ramo"],
                 ["tag", "v2"], ["push", "-q", "origin", "main", "nova-ramo", "v2"]):
        subprocess.run(["git", *args], cwd=clone, env=envc, check=True, capture_output=True)


def cenario_vazio(r: Repo) -> None:
    r.zerar()
    r.escrever("a.txt", "a\n")


def cenario_fora(r: Repo) -> None:
    r.zerar()
    shutil.rmtree(r.dir / ".git")


CENARIOS = {
    "historia": cenario_historia, "sujo": cenario_sujo, "conflito": cenario_conflito,
    "merge": cenario_merge_sem_conflito, "destacado": cenario_destacado, "rebase": cenario_rebase,
    "cherry-pick": cenario_cherry_pick, "bisect": cenario_bisect, "grande": cenario_grande,
    "blobs": cenario_blobs, "remoto": cenario_remoto, "vazio": cenario_vazio, "fora": cenario_fora,
}

# ── a grade de comandos ──────────────────────────────────────────────────────

GRADE = {
    "status": [[], ["-s"], ["-sb"], ["-b"], ["--short"], ["--branch"], ["-s", "-b"], ["--porcelain"], ["-v"],
               ["--", "src"], ["-uno"], ["--ignored"], ["-sb", "--"], ["src"], ["--long"], ["-z"]],
    "add": [[], ["."], ["-A"], ["-u"], ["-n", "."], ["novo.txt"], ["inexistente"], ["--"], ["-p"], ["-f", "x"],
            ["-v", "."], ["--dry-run"], ["src/a.py", "novo.txt"]],
    "fetch": [[], ["origin"], ["--all"], ["--tags"], ["inexistente"], ["-q"], ["--dry-run"], ["origin", "main"],
              ["--prune"]],
    "diff": [[], ["--cached"], ["--staged"], ["HEAD"], ["HEAD~1"], ["HEAD~3..HEAD"], ["v1"], ["--stat"],
             ["--no-compact"], ["-U0"], ["-U1"], ["-U10"], ["--word-diff"], ["--word-diff=none"], ["--name-only"],
             ["--name-status"], ["--numstat"], ["--shortstat"], ["--check"], ["-s"], ["--quiet"], ["--no-patch"],
             ["--", "src/a.py"], ["src"], ["--no-prefix"], ["inexistente"], ["-p", "-U5"], ["--stat", "-p"],
             ["--exit-code"], ["-w"], ["-b"], ["--color-words"], ["-M"], ["--patch-with-stat"], ["HEAD~1", "HEAD"],
             ["--raw"], ["--summary"], ["--diff-algorithm=patience"], ["--ws-error-highlight=all"], ["-l", "100"],
             ["-wl", "100"], ["--src-prefix=x/", "--dst-prefix=y/"], ["--binary"], ["--function-context"],
             ["-W"], ["-G", "linha", "HEAD~5"], ["--unified=2"]],
    "log": [[], ["-5"], ["-n", "3"], ["-n3"], ["--max-count=2"], ["--oneline"], ["--oneline", "-n", "3"],
            ["--oneline", "-3"], ["-p"], ["-p", "-3"], ["--stat"], ["--stat", "-n", "2"], ["--graph", "--oneline"],
            ["HEAD~5..HEAD"], ["--format=%H"], ["--pretty=oneline"], ["--merges"], ["--no-merges"],
            ["--author=Tester"], ["-S", "linha", "-p"], ["-S", "linha"], ["--name-only"], ["--skip=2"], ["inexistente"],
            ["--all"], ["--", "src/a.py"], ["src/a.py"], ["-1", "--", "src"], ["--since=2020-02-10"], ["-c"],
            ["--cc"], ["--diff-merges=first-parent"], ["--diff-merges=off"], ["--min-parents=2"], ["--first-parent"],
            ["--oneline", "--skip", "2"], ["--exit-code"], ["--summary"], ["--shortstat"], ["--numstat"],
            ["-U1"], ["--grep=commit"], ["--reverse"], ["--format=%h %s", "-n", "4"], ["-z"],
            ["--line-prefix=> "], ["--output=/dev/null"], ["-L", "1,3:src/a.py"], ["-pn", "2"], ["-n", "2", "-p"]],
    "show": [[], ["HEAD"], ["HEAD~1"], ["--stat"], ["-s"], ["--quiet"], ["--oneline"], ["--oneline", "-p"],
             ["HEAD:README.md"], ["HEAD:src/a.py"], ["HEAD:grande.txt"], ["HEAD:latin1.txt"], ["HEAD:bin.dat"],
             ["HEAD:sem-quebra.txt"], ["HEAD:pequeno.txt"], ["HEAD:src"], ["HEAD:nao-existe"], [":README.md"],
             ["-p", "HEAD"], ["--name-only"], ["--format=%s"], ["--pretty=oneline"], ["HEAD", "--", "src"],
             ["--check"], ["v1"], ["lateral"], ["-c", "HEAD"], ["--cc", "HEAD"], ["inexistente"], ["-U1"], ["-U10"],
             ["--word-diff"], ["-pq", "HEAD"], ["-s", "-p"], ["-p", "-s"], ["--no-patch"], ["HEAD~3", "HEAD"],
             ["HEAD:README.md", "HEAD:src/a.py"], ["--textconv", "HEAD:README.md"], ["HEAD:README.md", "--", "src"],
             ["-S", "linha", "HEAD"], ["-wG", "a:b", "HEAD"], [":/primeiro"], ["HEAD", "-M"], ["--stat", "-p"],
             ["--summary"], ["--raw"], ["-w"], ["HEAD^{tree}"], ["--diff-merges=c"], ["--first-parent", "-m", "HEAD"]],
}

GLOBAIS = [[], ["--no-pager"], ["-c", "color.ui=always"], ["-c", "core.quotepath=false"], ["-C", "."]]


def sortear(r: random.Random, sub: str) -> list[str]:
    pool = [a for args in GRADE[sub] for a in args if a.startswith("-")]
    extras = ["HEAD", "HEAD~1", "src", "src/a.py", "README.md", "v1", "--", "main", "lateral", "HEAD:README.md"]
    n = r.randint(0, 4)
    return [r.choice(pool + extras) for _ in range(n)]


# ── comparacao ───────────────────────────────────────────────────────────────

def _limpa(stderr: bytes) -> bytes:
    return b"".join(l for l in stderr.splitlines(keepends=True) if not l.startswith(AVISO_DO_RTK))


def rtk_real(repo: Repo, args: list[str]):
    p = subprocess.run([RTK, "git", *args], cwd=repo.dir, env=repo.env, capture_output=True)
    return p.stdout, _limpa(p.stderr), p.returncode


def porte(repo: Repo, args: list[str]):
    amb = Ambiente.em_memoria(str(repo.dir), env=repo.env)
    codigo = git.rodar(args, amb)
    o, e = amb.saida_gravada()
    return o, e, codigo


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=0, help="combinacoes sorteadas por subcomando e cenario")
    ap.add_argument("--so", action="append", help="so este cenario (repetivel)")
    ap.add_argument("--sub", action="append", help="so este subcomando (repetivel)")
    ap.add_argument("-v", action="store_true", help="mostra tambem os que batem")
    a = ap.parse_args()
    base.PREFIXO = "rtk"
    total = ok = 0
    falhas: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = Repo(Path(tmp) / "mundo")
        for nome, montar in CENARIOS.items():
            if a.so and nome not in a.so:
                continue
            montar(repo)
            repo.salvar()
            sorteio = random.Random(nome)
            for sub, comandos in GRADE.items():
                if a.sub and sub not in a.sub:
                    continue
                lista = [([], c) for c in comandos] + [(g, []) for g in GLOBAIS[1:]]
                lista += [(sorteio.choice(GLOBAIS), sortear(sorteio, sub)) for _ in range(a.n)]
                for globais, args in lista:
                    completo = [*globais, sub, *args]
                    if sub in MUTANTES:
                        repo.restaurar()
                    esperado = rtk_real(repo, completo)
                    if sub in MUTANTES:
                        repo.restaurar()
                    obtido = porte(repo, completo)
                    total += 1
                    if esperado == obtido:
                        ok += 1
                        if a.v:
                            print(f"ok   {nome}: git {' '.join(completo)}")
                    else:
                        falhas.append(f"{nome}: git {' '.join(completo)}")
                        print(f"DIFF {nome}: git {' '.join(completo)}")
                        for rotulo, x, y in (("stdout", esperado[0], obtido[0]), ("stderr", esperado[1], obtido[1]),
                                              ("codigo", esperado[2], obtido[2])):
                            if x != y:
                                print(f"   {rotulo} rtk : {repr(x)[:400]}\n   {rotulo} porte: {repr(y)[:400]}")
    print(f"{ok}/{total} identicos, {len(falhas)} diferentes")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
