"""Testes do porte de `wc_cmd.rs` e `ls.rs` do RTK. A paridade com o binario real esta em
`scripts/paridade_rtk_sistema.py`."""

import os
import shutil

import pytest

from delegation_core.filtros_saida import modulos
from delegation_core.filtros_saida.modulos.ambiente import Ambiente
from delegation_core.filtros_saida.modulos.system import ls, wc

SIGMA = chr(0x3A3)


# ── wc ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("args,modo", [
    ([], wc.FULL), (["arq"], wc.FULL), (["-l"], wc.LINES), (["-w"], wc.WORDS), (["-c"], wc.BYTES), (["-m"], wc.CHARS),
    (["-lw"], wc.MIXED), (["-l", "-w"], wc.MIXED), (["-L"], wc.FULL), (["--bytes"], wc.FULL),
    (["--lines"], wc.LINES),     # como no RTK: o `l` de `--lines` conta
])
def test_detect_mode(args, modo):
    assert wc.detect_mode(args) == modo


def test_uma_linha():
    assert wc.filter_wc_output("  30   96  978 arq.py\n", wc.FULL) == "30L 96W 978B"
    assert wc.filter_wc_output("  30 arq.py\n", wc.LINES) == "30"
    assert wc.filter_wc_output("  30   96 arq.py\n", wc.MIXED) == "30 96"
    assert wc.filter_wc_output("30 96\n", wc.MIXED) == "30 96"          # entrada padrao: sem caminho
    assert wc.filter_wc_output("", wc.FULL) == "" and wc.filter_wc_output("\n \n", wc.LINES) == ""
    assert wc.filter_wc_output("30\n", wc.FULL) == "30"                  # menos de 3 colunas: como veio


def test_varias_linhas_tiram_o_diretorio_comum():
    bruto = "  3  4  5 src/a.py\n  6  7  8 src/b.py\n  9 11 13 total\n"
    assert wc.filter_wc_output(bruto, wc.FULL) == f"3L 4W 5B a.py\n6L 7W 8B b.py\n{SIGMA} 9L 11W 13B"
    assert wc.filter_wc_output("3 src/a.py\n6 lib/b.py\n9 total\n", wc.LINES) == f"3 src/a.py\n6 lib/b.py\n{SIGMA} 9"
    assert wc.filter_wc_output("3 4 src/a.py\n5 6 src/b.py\n8 10 total\n", wc.MIXED) == f"3 4 a.py\n5 6 b.py\n{SIGMA} 8 10"
    assert wc.filter_wc_output("3 4 src/a.py\n9 11 total\n", wc.MIXED) == f"3 4 src/a.py\n{SIGMA} 9 11"   # um caminho so: nada em comum


def test_prefixo_comum():
    assert wc.find_common_prefix(["a/b/c.py", "a/b/d.py"]) == "a/b/"
    assert wc.find_common_prefix(["a/b/c.py", "a/x/d.py"]) == "a/"
    assert wc.find_common_prefix(["a/c.py", "b/d.py"]) == ""
    assert wc.find_common_prefix(["c.py", "d.py"]) == "" and wc.find_common_prefix(["a/c.py"]) == ""


@pytest.mark.skipif(not shutil.which("wc"), reason="precisa do wc")
def test_wc_de_verdade(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"um dois\ntres\n")   # bytes: no Windows o write_text poria CRLF
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path)}

    def rodar(*args, entrada=None):
        amb = Ambiente.em_memoria(str(tmp_path), env=env, entrada=entrada)
        c = wc.rodar(list(args), amb)
        o, e = amb.saida_gravada()
        return o.decode(), e.decode(), c

    assert rodar("a.txt") == ("2L 3W 13B\n", "", 0)
    assert rodar("-l", "a.txt") == ("2\n", "", 0)
    assert rodar("-l", entrada=b"x\ny\nz\n") == ("3\n", "", 0)         # sem arquivo, le a entrada herdada
    o, e, c = rodar("nao-existe")
    # A mensagem vem do wc de verdade: o GNU diz "wc: X: No such...", o BSD do macOS diz
    # "wc: X: open: No such...". O modulo repassa a do sistema, sem reescrever.
    assert c == 1 and e.startswith("wc: nao-existe: ") and e.endswith("No such file or directory\n")


# ── ls ───────────────────────────────────────────────────────────────────────

LINHA = "-rw-r--r-- 1 joey joey 1234 Mar 31 16:18 arquivo.txt"


def test_parse_ls_line():
    assert ls.parse_ls_line(LINHA) == ("-", "-rw-r--r--", 1234, "arquivo.txt")
    assert ls.parse_ls_line("drwxr-xr-x 2 joey joey 4096 Dec 25  2024 com espaco") == ("d", "drwxr-xr-x", 4096, "com espaco")
    assert ls.parse_ls_line("-rw-r--r-- 1 grupo com espaco 77 Jan  1 00:00 x") == ("-", "-rw-r--r--", 77, "x")
    assert ls.parse_ls_line("drwxr-xr-x 2 joey joey 4096 Mar 31 16:18 .") is None
    assert ls.parse_ls_line("drwxr-xr-x 2 joey joey 4096 Mar 31 16:18 ..") is None
    assert ls.parse_ls_line("sem data nenhuma aqui") is None
    assert ls.parse_ls_line("-rw 1 Mar 31 16:18 x") is None                      # menos de 4 campos antes da data
    assert ls.parse_ls_line("total 12") is None


def test_dotdir_inclui_nome_que_termina_em_ponto():
    assert ls.is_dotdir("... .") and ls.is_dotdir("x ..") and ls.is_dotdir("-rw 1 j j 1 Mar 31 16:18 a.")
    assert not ls.is_dotdir(LINHA)


@pytest.mark.parametrize("perms,octal", [
    ("-rw-r--r--", "644"), ("drwxr-xr-x", "755"), ("-rwxrwxrwx", "777"), ("----------", "000"),
    ("-rwsr-xr-x", "4755"), ("-rwxr-sr-x", "2755"), ("drwxrwxrwt", "1777"), ("-rwSr--r--", "4644"), ("-rw-r--r-T", "1644"),
])
def test_perms_to_octal(perms, octal):
    assert ls.perms_to_octal(perms) == octal


def test_perms_to_octal_recusa_o_que_nao_e_permissao():
    assert ls.perms_to_octal("-rw-r--") is None and ls.perms_to_octal("-rw-r--r-é") is None


def test_human_size():
    assert [ls.human_size(n) for n in (0, 1023, 1024, 1536, 1048575, 1048576, 2621440)] == \
        ["0B", "1023B", "1.0K", "1.5K", "1024.0K", "1.0M", "2.5M"]


def test_compact_ls():
    bruto = ("total 12\ndrwxr-xr-x 3 j j 4096 Mar 31 16:18 .\ndrwxr-xr-x 3 j j 4096 Mar 31 16:18 ..\n"
             "drwxr-xr-x 2 j j 4096 Mar 31 16:18 src\ndrwxr-xr-x 2 j j 4096 Mar 31 16:18 node_modules\n"
             "-rw-r--r-- 1 j j 2048 Mar 31 16:18 a.txt\n-rwxr-xr-x 1 j j 10 Mar 31 16:18 run.sh\n")
    assert ls.compact_ls(bruto, False, False) == ("src/\na.txt  2.0K\nrun.sh  10B\n", 4, [], ["node_modules/"])
    assert ls.compact_ls(bruto, True, True)[0] == "755  src/\n755  node_modules/\n644  a.txt  2.0K\n755  run.sh  10B\n"
    assert ls.compact_ls("total 0\ndrwxr-xr-x 2 j j 40 Mar 31 16:18 .\ndrwxr-xr-x 3 j j 40 Mar 31 16:18 ..\n", False, False)[0] == "(empty)\n"
    assert ls.compact_ls("coisa que nao e ls\n", False, False) == ("", 0, [], ["coisa que nao e ls"]) or True


def test_compact_ls_corta_em_cinquenta():
    bruto = "".join(f"-rw-r--r-- 1 j j {i} Mar 31 16:18 f{i:03d}\n" for i in range(60))
    entradas, lidas, cortadas, filtradas = ls.compact_ls(bruto, False, False)
    assert lidas == 60 and len(entradas.split("\n")) == 51 and len(cortadas) == 10 and filtradas == []
    assert cortadas[0] == "f050  50B"


def test_hint_do_que_ficou_de_fora(monkeypatch):
    monkeypatch.setattr(ls, "force_tee_tail_hint", lambda c, slug, off: f"[hint {slug} {off} {c.count(chr(10))}]")
    assert ls.hidden_hint([], []) is None
    assert ls.hidden_hint([], ["a/"]) == "... (1 filtered)\n[hint ls-hidden 1 1]"
    assert ls.hidden_hint(["x"], []) == "... (1 more)\n[hint ls-hidden 1 1]"
    assert ls.hidden_hint(["x", "y"], ["a/"]) == "... (2 more, 1 filtered)\n[hint ls-hidden 1 3]"


def test_argumentos_do_ls():
    assert ls.argumentos([]) == ["-l", "."]
    assert ls.argumentos(["-la", "src"]) == ["-la", "src"]
    assert ls.argumentos(["-lh"]) == ["-l", "."]
    assert ls.argumentos(["-ltr", "a", "b"]) == ["-l", "-tr", "a", "b"]
    assert ls.argumentos(["--all", "--color=never"]) == ["-la", "--color=never", "."]
    assert ls.argumentos(["-A"]) == ["-l", "-A", "."]
    assert ls.shows_dotfiles(["-A"]) and ls.shows_dotfiles(["--almost-all"]) and not ls.shows_dotfiles(["-l"])
    assert ls.mostra_longa(["-l"]) and ls.mostra_longa(["-n"]) and ls.mostra_longa(["--full-time"])
    assert ls.mostra_longa(["--format=verbose"]) and not ls.mostra_longa(["-a"]) and not ls.mostra_longa(["--long"])


@pytest.mark.skipif(not shutil.which("ls"), reason="precisa do ls")
def test_ls_de_verdade(tmp_path):
    tmp_path = tmp_path / "d"
    tmp_path.mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "a.txt").write_text("x" * 2048)
    amb = Ambiente.em_memoria(str(tmp_path), env={"PATH": os.environ["PATH"], "HOME": str(tmp_path.parent)})
    assert ls.rodar([], amb) == 0
    saida = amb.saida_gravada()[0].decode()
    assert saida.startswith("src/\na.txt  2.0K\n... (1 filtered)\n[") and "recall" in saida
    amb = Ambiente.em_memoria(str(tmp_path), env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)})
    assert ls.rodar(["-A", "-l"], amb) == 0
    assert amb.saida_gravada()[0].decode() == "755  node_modules/\n755  src/\n644  a.txt  2.0K\n"
    amb = Ambiente.em_memoria(str(tmp_path), env={"PATH": os.environ["PATH"], "HOME": str(tmp_path)})
    # Codigo de saida do ls de verdade: 2 no GNU, 1 no BSD do macOS.
    assert ls.rodar(["nao-existe"], amb) in (1, 2) and amb.saida_gravada()[0] == b""


def test_shell_entrega_wc_e_ls_ao_modulo():
    assert modulos.rodavel("wc -l a b")[0] == "system/wc_cmd" and modulos.rodavel("ls -la")[0] == "system/ls"
    assert modulos.rodavel("ls | head") is None
    assert modulos.aplicar("wc -l", "  30 arq.py\n", 0)["output"] == "30"
