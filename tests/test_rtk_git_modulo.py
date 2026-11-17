"""Testes do porte de `git_cmd.rs` do RTK (status, add, fetch, diff, log, show).

Os de funcao pura sao traducoes revisadas dos testes do Rust; os de ponta a ponta rodam
num repositorio de verdade (datas fixas) e conferem a saida inteira. A paridade com o
binario do RTK esta em `scripts/paridade_rtk_git.py`.
"""

import os
import subprocess
import sys

import pytest

from delegation_core.filtros_saida import modulos
from delegation_core.filtros_saida.modulos.ambiente import Ambiente
from delegation_core.filtros_saida.modulos.git import git as g

TRACO = chr(0x2014)  # o travessao da linha de status limpo do RTK, sem o caractere no arquivo


# ── funcoes puras ────────────────────────────────────────────────────────────

def test_analisar_remonta_as_opcoes_globais_na_ordem_do_rtk():
    assert g.analisar(["status"]) == ([], "status", [])
    assert g.analisar(["--no-pager", "-c", "a=b", "-C", "/x", "diff", "--stat"]) == (
        ["-C", "/x", "-c", "a=b", "--no-pager"], "diff", ["--stat"])
    assert g.analisar(["-C/x", "--git-dir=/y", "--work-tree", "/z", "log"]) == (
        ["-C", "/x", "--git-dir", "/y", "--work-tree", "/z"], "log", [])
    assert g.analisar(["-C", "/a", "-C", "/b", "show"])[0] == ["-C", "/a", "-C", "/b"]


def test_analisar_deixa_para_o_git_o_que_o_modulo_nao_porta():
    for args in (["commit", "-m", "x"], ["push"], ["--paginate", "status"], ["-C"], [], ["-p", "log"],
                 ["--git-dir=a", "--git-dir=b", "status"]):
        assert g.analisar(args) is None
        assert not g.executa(args)


def test_log_e_diff_levam_a_gramatica_de_flags_do_git():
    t = g.tokenize_git_log_args(["-n", "3", "--grep", "-p", "-pn", "2"])
    assert t[0].value(t) == "3"                       # -n solitario leva valor
    grep = next(x for x in t if x.text == "grep")
    assert grep.value(t) == "-p"                      # --grep engole o -p
    n = [x for x in t if x.text == "n"][1]
    assert n.value(t) is None                         # -pn 2 o git rejeita
    # `-l` agrupa em diff (`-wl 100`) e e solitario em log.
    assert g.tokenize_git_diff_args(["-wl", "100"])[1].value(g.tokenize_git_diff_args(["-wl", "100"])) == "100"
    assert g.tokenize_git_log_args(["-cl", "2"])[1].value(g.tokenize_git_log_args(["-cl", "2"])) is None


def test_status_caminho_compacto_so_para_branch_e_short():
    for args in ([], ["-b"], ["-sb"], ["--short", "--branch"], ["--"], ["-sb", "--"]):
        assert g.uses_compact_status_path(args), args
    # `-s` sozinho pede o formato curto sem o branch: o git responde, com o filtro minimo.
    for args in (["-s"], ["--short"], ["-v"], ["--porcelain"], ["src"], ["--", "src"], ["-uno"], ["-z"]):
        assert not g.uses_compact_status_path(args), args


def test_format_status_output():
    assert g.format_status_output("") == "Clean working tree"
    assert g.format_status_output("## main...origin/main\n") == f"* main...origin/main\nclean {TRACO} nothing to commit"
    assert g.format_status_output("## main\n M a.py\n?? b.py\n") == "* main\n M a.py\n?? b.py"
    assert g.format_status_output("## HEAD (no branch)\n", "HEAD detached at abc123") == \
        f"* HEAD detached at abc123\nclean {TRACO} nothing to commit"
    assert g.format_status_output("## ## x\n") == "* x\nclean " + TRACO + " nothing to commit"
    assert g.format_status_output(" M a.py\n") == " M a.py"  # sem a linha de branch


@pytest.mark.parametrize("texto,esperado", [
    ("You are currently rebasing branch 'x' on 'y'.", "rebase in progress"),
    ("You are currently editing a commit while rebasing", "rebase in progress"),
    ("You have unmerged paths.", "merge in progress. unresolved conflicts"),
    ("All conflicts fixed but you are still merging.", "merge in progress. no conflicts"),
    ("You are currently cherry-picking commit abc.", "cherry-pick in progress"),
    ("You are currently reverting commit abc.", "revert in progress"),
    ("You are currently bisecting, started from branch 'main'.", "bisect in progress"),
    ("You are in the middle of an am session.", "am session in progress"),
    ("You are in a sparse checkout with 10% of tracked files present.", "sparse checkout enabled"),
])
def test_extract_state_header(texto, esperado):
    assert g.extract_state_header(f"On branch main\n{texto}\n  (use ...)\n") == esperado


def test_extract_state_header_para_no_primeiro_bloco_de_arquivos():
    bruto = "On branch main\nChanges not staged for commit:\n  modified: a\nYou are currently rebasing\n"
    assert g.extract_state_header(bruto) is None
    assert g.extract_state_header("On branch main\nnothing to commit, working tree clean\n") is None


def test_extract_detached_head():
    assert g.extract_detached_head("HEAD detached at v1\nnothing to commit\n") == "HEAD detached at v1"
    assert g.extract_detached_head("  HEAD detached from abc\n") == "HEAD detached from abc"
    assert g.extract_detached_head("On branch main\n") is None


def test_filter_status_with_args():
    bruto = ('On branch main\n\nChanges not staged for commit:\n  (use "git add <file>..." to update)\n'
             '\tmodified:   a.py\n\nno changes added to commit (use "git add" and/or "git commit -a")\n')
    # A linha final tem `(use "git add"` no meio e sai com as dicas.
    assert g.filter_status_with_args(bruto) == 'On branch main\nChanges not staged for commit:\n\tmodified:   a.py\n'.rstrip("\n")
    assert g.filter_status_with_args("On branch main\nnothing to commit, working tree clean\n") == \
        "On branch main\nnothing to commit, working tree clean"
    assert g.filter_status_with_args("\n\n") == "ok"


def test_filter_log_output_formato_do_rtk():
    saida = ("abc1234 primeiro (2 days ago) <Ana>\ncorpo um\nSigned-off-by: X <x@y>\n---END---\n"
             "def5678 segundo (3 days ago) <Bia>\n\n---END---\n")
    assert g.filter_log_output(saida, 10, False, False) == (
        "abc1234 primeiro (2 days ago) <Ana>\n  corpo um\ndef5678 segundo (3 days ago) <Bia>")


def test_filter_log_output_corpo_e_largura():
    corpo = "\n".join(f"linha {i}" for i in range(6))
    saida = f"abc1234 {'x' * 100} (1 day ago) <Ana>\n{corpo}\n---END---\n"
    r = g.filter_log_output(saida, 10, False, False)
    ls = r.split("\n")
    assert len(ls[0]) == 80 and ls[0].endswith("...")
    assert ls[1:] == ["  linha 0", "  linha 1", "  linha 2", "  [+3 lines omitted]"]
    assert len(g.filter_log_output(saida, 10, True, False).split("\n")[0]) == 120  # -N do usuario: mais largo


def test_filter_log_output_limite_e_formato_do_usuario():
    commits = "".join(f"h{i} assunto {i}\n---END---\n" for i in range(5))
    assert g.filter_log_output(commits, 3, False, False).count("assunto") == 3
    assert g.filter_log_output(commits, 3, True, False).count("assunto") == 5
    linhas = "\n".join(f"{i:07x} commit {i}" for i in range(8))
    assert len(g.filter_log_output(linhas, 5, False, True).split("\n")) == 5
    assert len(g.filter_log_output(linhas, 5, True, True).split("\n")) == 8
    assert g.truncate_line("é" * 10, 8) == "é" * 5 + "..."


def test_filter_log_output_multibyte_nao_quebra():
    saida = "abc1234 " + "\U0001F600" * 100 + " (1 day ago) <Ana>\n---END---\n"
    assert g.filter_log_output(saida, 10, False, False).endswith("...")


def test_limite_do_log():
    def lim(*args):
        return g.parse_limit_from_tokens(g.tokenize_git_log_args(list(args)))
    assert lim("-20") == 20 and lim("-n", "5") == 5 and lim("--max-count=7") == 7 and lim("--max-count", "9") == 9
    assert lim("--oneline") is None and lim("-n", "x") is None
    t = g.tokenize_git_log_args(["-pn", "2"])
    assert not g.has_limit_flag(t)  # `n` agrupado nao capturou valor: e uma letra inerte
    assert not g.has_limit_flag(g.tokenize_git_log_args(["--grep", "-20"]))  # valor de --grep, nao limite
    assert g.has_limit_flag(g.tokenize_git_log_args(["-5"]))


@pytest.mark.parametrize("args,cru", [
    (["-p"], True), (["--stat"], True), (["--name-only"], True), (["--cc"], True), (["-c"], True),
    (["-U3"], True), (["--line-prefix=x"], True), (["--diff-merges=first-parent"], True),
    (["--diff-merges=off"], False), (["--oneline"], False), (["-W"], False), (["--", "-p"], False),
    (["--grep", "-p"], False), (["--author=x"], False), (["--format=%s"], False),
])
def test_log_forma_crua(args, cru):
    t = g.tokenize_git_log_args(args)
    assert any(g.log_wants_raw_shape(x, t) for x in t) is cru


def test_diff_e_show_formas_cruas():
    def cru(f, *args):
        t = g.tokenize_git_diff_args(list(args))
        return any(f(x, t) for x in t)
    # `diff --quiet` e cru; em `show` `--quiet` e sinonimo de -s (resumo compacto).
    assert cru(g.diff_wants_raw_shape, "--quiet") and not cru(g.show_wants_raw_shape, "--quiet")
    assert cru(g.show_wants_raw_shape, "--check") and cru(g.show_wants_raw_shape, "--exit-code")
    # -p/-U/--patch ja sao o que diff e show imprimem: nao sao forma crua.
    for f in ("-p", "-U5", "--patch", "--unified=3", "-u"):
        assert not cru(g.show_wants_raw_shape, f)
    assert cru(g.show_wants_raw_shape, "--stat") and cru(g.show_wants_raw_shape, "-c")
    assert cru(g.show_wants_raw_shape, "--diff-merges=cc") and not cru(g.show_wants_raw_shape, "--diff-merges=first-parent")


def test_supressao_do_corpo_segue_o_ultimo_flag():
    def sup(*args):
        return g.body_is_suppressed(g.tokenize_git_diff_args(list(args)))
    assert sup("-s") and sup("--no-patch") and sup("--quiet")
    assert not sup("-s", "-p") and sup("-p", "-s")
    assert not sup("--quiet", "-p") and not sup("-p", "--quiet")
    assert not sup()


def test_word_diff():
    def wd(*args):
        return g.emits_word_diff(g.tokenize_git_log_args(list(args)))
    for f in ("--word-diff", "--word-diff=plain", "--word-diff=porcelain", "--word-diff-regex=.", "--color-words", "--color-words=."):
        assert wd(f), f
    assert not wd("--stat") and not wd("-U10") and not wd()
    assert not wd("--word-diff=none") and not wd("--word-diff", "--word-diff=none")
    assert wd("--word-diff=none", "--word-diff") and wd("--color-words=none")
    assert not wd("--author", "--word-diff") and wd("-M", "--word-diff") and not wd("--", "--word-diff")


def test_args_sem_a_forma_de_patch():
    def sem(*args):
        a = list(args)
        return g.args_without_patch_shape(a, g.tokenize_git_diff_args(a))
    assert sem("-p", "HEAD", "--", "f") == ["HEAD", "--", "f"]
    assert sem("-pl", "100", "HEAD") == ["-l", "100", "HEAD"]   # so a letra do patch sai do grupo
    assert sem("-U3", "--unified=2", "-W", "--function-context", "x") == ["x"]
    assert sem("--", "-p") == ["--", "-p"]                       # pathspec depois de `--` fica
    a = ["--oneline", "-p", "abc"]
    assert g.args_without_oneline(a, g.tokenize_git_diff_args(a)) == ["-p", "abc"]
    a = ["abc", "--", "--oneline"]
    assert g.args_without_oneline(a, g.tokenize_git_diff_args(a)) == a


def test_show_positionals_ignora_valores_de_flags_e_pathspecs():
    assert g.show_positionals(["-S", "url:1", "HEAD:f"]) == ["HEAD:f"]
    assert g.show_positionals(["-wG", "a:b", "HEAD:big"]) == ["HEAD:big"]
    assert g.show_positionals(["-Sfoo", "HEAD"]) == ["HEAD"]       # valor preso: nao consome o seguinte
    assert g.show_positionals(["HEAD", "--", "weird:name"]) == ["HEAD"]
    assert g.show_positionals(["--grep", "x:y", "--stat", "HEAD"]) == ["HEAD"]


def test_is_blob_show_arg():
    for ok in ("HEAD:f.txt", "v1:src/a.py", ":f.txt", ":2:f.txt"):
        assert g.is_blob_show_arg(ok), ok
    for no in ("HEAD", ":/texto", ":(exclude)f", ":!f", ":^f", "--pretty=format:%s", ":", "::"):
        assert not g.is_blob_show_arg(no), no


def test_rotas_do_show():
    assert g.show_route(["HEAD:f"]) == g.BLOB
    assert g.show_route(["--stat", "HEAD:f"]) == g.BLOB         # blob vence --stat e --format
    assert g.show_route(["--stat"]) == g.STAT_OR_FORMAT
    assert g.show_route(["--format=%s"]) == g.STAT_OR_FORMAT
    assert g.show_route(["--word-diff"]) == g.STAT_OR_FORMAT
    assert g.show_route(["HEAD", "--", "a:b"]) == g.COMMIT_DIFF  # dois-pontos depois de `--` e pathspec
    assert g.show_route([]) == g.COMMIT_DIFF
    assert g.show_route(["--oneline"]) == g.COMMIT_DIFF


def test_blob_truncation():
    pequeno = "a\n" * 10
    assert g.blob_truncation(pequeno, 8192) is None
    grande = "".join(f"linha {i:04d} de um arquivo\n" for i in range(1000))
    inicio, restantes, deslocamento = g.blob_truncation(grande, 8192)
    assert len(inicio.encode()) <= 8192 and inicio.endswith("\n") and grande.startswith(inicio)
    assert restantes == 1000 - inicio.count("\n") and deslocamento == inicio.count("\n") + 1
    assert g.blob_truncation("x" * 20000, 8192) is None               # uma linha so: nao ha onde cortar
    assert g.blob_truncation(grande + "\0", 8192) is None             # binario
    assert g.blob_truncation(grande + "�", 8192) is None         # decodificado com perda
    assert g.blob_truncation("é" * 5000 + "\n" + "b\n" * 5000, 8192) is None   # a quebra de linha esta alem do orcamento
    multi = "é" * 3000 + "\n" + "é" * 3000 + "\n" + "b\n" * 5000
    inicio, _, _ = g.blob_truncation(multi, 8192)                     # o orcamento cai no meio de um caractere
    assert inicio == "é" * 3000 + "\n"


def test_dica_do_blob_cita_o_comando_sem_filtro():
    grande = "".join(f"linha {i:04d} de um arquivo\n" for i in range(1000))
    r = g.compact_blob_show(grande, "HEAD:lock.json", ["-C", "/meu repo"])
    assert "... (+" in r and r.endswith("| tail -n +" + str(g.blob_truncation(grande, 8192)[2]) + "]\n")
    assert "git '-C' '/meu repo' show 'HEAD:lock.json' | tail" in r
    assert "rtk proxy" not in r
    assert g.compact_blob_show("curto\n", "HEAD:f", []) == "curto\n"


def test_filtrar_do_filter_output():
    assert g.filtrar("On branch x\n\n(use \"git add\")\n", 0, ["status"]) == "On branch x"
    assert g.filtrar("From o\n * [new branch] a -> o/a\n   1..2  b -> o/b\n", 0, ["fetch"]) == "ok fetched (2 new refs)"
    assert g.filtrar("", 0, ["fetch"]) == "ok fetched"
    assert g.filtrar("erro", 1, ["fetch"]) == "erro"
    assert g.filtrar("", 0, ["diff"]) == "No diff"
    d = "diff --git a/f b/f\n@@ -1 +1 @@\n-a\n+b\n"
    assert "+1 -1" in g.filtrar(d, 0, ["diff"])
    assert g.filtrar("abc1234 x\n" * 100, 0, ["log", "--oneline"]).count("\n") == 49
    assert g.filtrar("qualquer coisa", 0, ["show"]) == "qualquer coisa"


def test_trata_decide_o_que_o_filter_output_assume():
    assert g.trata(["status"]) and g.trata(["fetch"]) and g.trata(["diff"])
    assert not g.trata(["diff", "--stat"]) and not g.trata(["diff", "--no-compact"])
    assert g.trata(["log", "--oneline"]) and not g.trata(["log"]) and not g.trata(["show"]) and not g.trata(["add"])
    assert not g.trata(["commit"])


# ── ponta a ponta, num repositorio de verdade ────────────────────────────────

class Repo(os.PathLike):
    """O diretorio do repositorio, mais `git(...)` (datas fixas) e o ambiente de processos."""

    def __init__(self, caminho, git, env):
        self.caminho, self.git, self.env = caminho, git, env

    def __fspath__(self):
        return str(self.caminho)

    def __truediv__(self, outro):
        return self.caminho / outro

    def __str__(self):
        return str(self.caminho)


@pytest.fixture
def repo(tmp_path):
    casa = tmp_path / "casa"
    casa.mkdir()
    # autocrlf = input: no Windows o write_text grava CRLF, e o blob no repositorio precisa ser LF
    # para o `git show` sair igual nos tres sistemas (CI de 17/11/2026).
    (casa / "gitconfig").write_text("[user]\n\tname = T\n\temail = t@x.y\n[init]\n\tdefaultBranch = main\n"
                                    "[core]\n\tautocrlf = input\n\tsafecrlf = false\n")
    r = tmp_path / "repo"
    r.mkdir()
    env = {"PATH": os.environ["PATH"], "HOME": str(casa), "GIT_CONFIG_NOSYSTEM": "1", "LC_ALL": "C",
           "GIT_CONFIG_GLOBAL": str(casa / "gitconfig")}

    def git(*args, dia=1):
        e = dict(env, GIT_AUTHOR_DATE=f"2020-01-{dia:02d} 10:00:00", GIT_COMMITTER_DATE=f"2020-01-{dia:02d} 10:00:00")
        subprocess.run(["git", *args], cwd=r, env=e, check=True, capture_output=True)

    git("init", "-q")
    for i in (1, 2, 3):
        (r / f"f{i}.txt").write_text(f"linha {i}\n")
        git("add", ".")
        git("commit", "-q", "-m", f"commit {i}", "-m", f"corpo {i}", dia=i)
    return Repo(r, git, env)


def rodar(repo, *args):
    amb = Ambiente.em_memoria(str(repo), env=repo.env)
    codigo = g.rodar(list(args), amb)
    o, e = amb.saida_gravada()
    return o.decode(), e.decode(), codigo


def test_status_limpo_e_sujo(repo):
    assert rodar(repo, "status") == (f"* main\nclean {TRACO} nothing to commit\n", "", 0)
    (repo / "f1.txt").write_text("mudou\n")
    (repo / "novo.txt").write_text("x\n")
    assert rodar(repo, "status") == ("* main\n M f1.txt\n?? novo.txt\n", "", 0)
    assert rodar(repo, "status", "-sb")[0] == "* main\n M f1.txt\n?? novo.txt\n"
    o, _, c = rodar(repo, "status", "--porcelain")
    assert c == 0 and o == " M f1.txt\n?? novo.txt"          # caminho nao compacto: filtro minimo, sem \n final


def test_status_fora_de_um_repositorio(tmp_path):
    amb = Ambiente.em_memoria(str(tmp_path), env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
                                                  "GIT_CEILING_DIRECTORIES": str(tmp_path.parent)})
    codigo = g.rodar(["status"], amb)
    assert codigo == 128 and amb.saida_gravada() == (b"", b"Not a git repository\n")


def test_status_mostra_o_rebase_em_andamento(repo):
    repo.git("checkout", "-q", "-b", "x")
    (repo / "f1.txt").write_text("x\n")
    repo.git("commit", "-qam", "x", dia=9)
    # Editor de sequencia em Python: `sed -i` sem extensao falha no sed BSD do macOS, e no
    # Windows nao ha sed. O caminho do interpretador vai entre aspas por causa de espacos.
    python = sys.executable.replace("\\", "/")
    editor = f'"{python}" -c "import sys; p = sys.argv[1]; s = open(p).read(); open(p, \'w\').write(s.replace(\'pick\', \'edit\', 1))"'
    subprocess.run(["git", "-c", f"sequence.editor={editor}", "rebase", "-q", "-i", "main~1"],
                   cwd=repo, env=repo.env, capture_output=True)
    o, _, _ = rodar(repo, "status")
    assert o.startswith("rebase in progress\n* ")


def test_add_conta_o_que_foi_preparado(repo):
    (repo / "novo.txt").write_text("a\nb\n")
    assert rodar(repo, "add", "novo.txt") == ("ok 1 file changed, 2 insertions(+)\n", "", 0)
    assert rodar(repo, "add", "novo.txt") == ("ok 1 file changed, 2 insertions(+)\n", "", 0)  # ja preparado: o diff continua
    o, e, c = rodar(repo, "add", "nao-existe")
    assert (o, c) == ("", 128) and e.startswith("FAILED: git add\n")


def test_add_sem_efeito_e_silencioso(repo):
    assert rodar(repo, "add") == ("", "", 0)


def test_diff_compacta_e_dobra_para_a_forma_crua(repo):
    (repo / "f1.txt").write_text("linha 1\nnova\n")
    o, e, c = rodar(repo, "diff")
    assert c == 0 and e == ""
    # O cabecalho e o stat sem o espaco inicial (o RTK faz trim), depois `Changes:` e o diff compacto.
    assert o == "f1.txt | 1 +\n 1 file changed, 1 insertion(+)\n\nChanges:\n\nf1.txt\n@@ -1 +1,2 @@\n linha 1\n+nova\n  +1 -0\n"
    cru = rodar(repo, "diff", "--stat")
    assert cru[0].startswith(" f1.txt | 1 +\n") and "Changes:" not in cru[0]   # cru: com o espaco do git
    assert rodar(repo, "diff", "--no-compact")[0].startswith("diff --git a/f1.txt b/f1.txt\n")
    assert rodar(repo, "diff", "--quiet")[2] == 1 and rodar(repo, "diff", "--quiet")[0] == ""
    assert rodar(repo, "diff", "inexistente")[2] == 128


def test_log_formato_padrao_e_limite(repo):
    o, e, c = rodar(repo, "log")
    assert c == 0 and e == ""
    ls = o.split("\n")
    assert ls[0].startswith("%s " % subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, env=repo.env,
                                                    capture_output=True, text=True).stdout.strip())
    assert "commit 3" in ls[0] and "<T>" in ls[0] and ls[1] == "  corpo 3"
    assert o.count("commit ") == 3
    um = rodar(repo, "log", "-1")[0]
    assert um.count("commit ") == 1
    ol = rodar(repo, "log", "--oneline")[0].split("\n")
    assert len(ol) == 4 and ol[-1] == ""                          # `--oneline` sem limite: -50, println final
    assert rodar(repo, "log", "inexistente")[2] == 128


def test_log_cru_avisa_do_teto_de_dez(repo):
    for i in range(12):
        (repo / "g.txt").write_text(f"{i}\n")
        repo.git("add", ".")
        repo.git("commit", "-q", "-m", f"extra {i}", dia=10 + i % 5)
    o, e, c = rodar(repo, "log", "--stat")
    assert c == 0 and o.count("\ncommit ") + o.startswith("commit ") == 10
    assert e == "[delegation-core] capped at 10 commits; pass -n <count> for more\n"
    o, e, c = rodar(repo, "log", "--stat", "-n", "3")
    assert e == "" and o.count("commit ") >= 3


def test_show_resumo_stat_e_diff(repo):
    (repo / "f1.txt").write_text("linha 1\nsegunda\n")
    repo.git("commit", "-qam", "muda f1", dia=5)
    o, e, c = rodar(repo, "show")
    assert c == 0 and e == ""
    ls = o.split("\n")
    assert " muda f1 (" in ls[0] and ls[0].endswith("<T>")
    assert "\nf1.txt | 1 +\n" in o and "\nf1.txt\n@@ -1 +1,2 @@\n" in o and "\n+segunda\n" in o
    assert rodar(repo, "show", "-s")[0].count("\n") == 1                # so o resumo
    assert rodar(repo, "show", "--format=%s", "-s")[0] == "muda f1\n"   # formato do usuario: cru


def test_show_blob_pequeno_e_grande(repo):
    assert rodar(repo, "show", "HEAD:f1.txt") == ("linha 1\n", "", 0)
    (repo / "grande.txt").write_text("".join(f"linha numero {i:05d} do arquivo grande\n" for i in range(2000)))
    repo.git("add", ".")
    repo.git("commit", "-qm", "grande", dia=6)
    o, _, c = rodar(repo, "show", "HEAD:grande.txt")
    assert c == 0 and len(o.encode()) < 9000 and "... (+" in o and "| tail -n +" in o
    assert rodar(repo, "show", "HEAD:nao-existe")[2] == 128


def test_show_blob_latin1_passa_inteiro(repo):
    bruto = "acentua\xe7\xe3o\n".encode("latin-1") * 3000
    (repo / "l1.txt").write_bytes(bruto)
    repo.git("add", ".")
    repo.git("commit", "-qm", "latin1", dia=6)
    amb = Ambiente.em_memoria(str(repo), env=repo.env)
    assert g.rodar(["show", "HEAD:l1.txt"], amb) == 0
    assert amb.saida_gravada()[0] == bruto                              # byte a byte, sem janela


def test_globais_levam_para_outro_diretorio(repo, tmp_path):
    amb = Ambiente.em_memoria(str(tmp_path), env=repo.env)
    assert g.rodar(["-C", str(repo), "status"], amb) == 0
    assert amb.saida_gravada()[0] == f"* main\nclean {TRACO} nothing to commit\n".encode()


def test_fetch_conta_as_referencias_novas(repo, tmp_path):
    origem = tmp_path / "origem"
    subprocess.run(["git", "clone", "-q", "--bare", str(repo), str(origem)], env=repo.env, check=True)
    repo.git("remote", "add", "origin", str(origem))
    assert rodar(repo, "fetch") == ("ok fetched (1 new refs)\n", "", 0)  # origin/main e a unica novidade
    assert rodar(repo, "fetch") == ("ok fetched\n", "", 0)
    o, e, c = rodar(repo, "fetch", "inexistente")
    assert o == "" and c == 128 and e.startswith("FAILED: git fetch\n")


# ── o `shell` entrega o comando ao modulo ────────────────────────────────────

def test_shell_entrega_comando_simples_ao_modulo():
    ach = modulos.rodavel("git status -sb")
    assert ach is not None and ach[0] == "git/git_cmd" and ach[2] == ["status", "-sb"]
    assert modulos.rodavel("git -C /tmp 'log' --oneline")[2] == ["-C", "/tmp", "log", "--oneline"]
    assert modulos.rodavel("git commit -m x") is None                    # nao portado: segue como estava
    assert modulos.rodavel("git status && ls") is None                   # composto: nunca
    assert modulos.rodavel("git status | head") is None
    assert modulos.rodavel("echo oi") is None


@pytest.mark.skipif(sys.platform == "win32", reason="o sh do Git Bash expande ~ como /c/Users/...")
def test_shell_expande_o_que_o_shell_expandiria(tmp_path, monkeypatch):
    monkeypatch.setenv("ALVO", "src")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    assert modulos.argumentos_do_shell('git add *.py "$ALVO" \'x y\' ~') == \
        ["add", "a.py", "b.py", "src", "x y", os.path.expanduser("~")]
    assert modulos.argumentos_do_shell("git") == []
    assert modulos.argumentos_do_shell("git add --") == ["add", "--"]


def test_cmd_run_usa_o_modulo(repo, monkeypatch, capsys):
    from delegation_core.filtros_saida import cli
    for k, v in repo.env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(repo)
    class A:  # o argparse entrega so o texto do comando
        comando = "git status"
    assert cli.cmd_run(A) == 0
    assert capsys.readouterr().out == f"* main\nclean {TRACO} nothing to commit\n"


def test_filter_output_usa_o_modulo_quando_sabe_reduzir():
    r = modulos.aplicar("git status", "On branch x\n\n(use \"git add\")\n", 0)
    assert r["rtk_module"] == "git/git_cmd" and r["ported"] and r["output"] == "On branch x"
    assert modulos.aplicar("git log", "qualquer", 0) is None            # cai no compressor anotado
    assert modulos.aplicar("git status && ls", "x", 0) is None
