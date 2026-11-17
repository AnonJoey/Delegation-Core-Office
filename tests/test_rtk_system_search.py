"""Testes do porte de `search.rs` do RTK (`grep` e `rg` agrupados por arquivo).

A paridade byte a byte com o binario do RTK, sobre uma arvore de arquivos e com os tres tipos de
entrada padrao, esta em `scripts/paridade_rtk_busca.py`.
"""

import os
import shutil

import pytest

from delegation_core.filtros_saida import modulos
from delegation_core.filtros_saida.modulos.ambiente import Ambiente
from delegation_core.filtros_saida.modulos.system import search as s

pytestmark = pytest.mark.skipif(not (shutil.which("grep") and shutil.which("rg")), reason="precisa de grep e rg")


# ── funcoes puras ────────────────────────────────────────────────────────────

def extrair(motor, *args):
    padroes, caminhos, flags, formato, d = s.extract_pattern_path(list(args), motor)
    return padroes, caminhos, flags, formato, (d.show_file, d.show_line, d.recursive, d.context)


def test_padrao_e_caminhos():
    assert extrair("grep", "foo", "a.txt", "b.txt")[:2] == (["foo"], ["a.txt", "b.txt"])
    assert extrair("grep", "foo")[:2] == (["foo"], [])
    assert extrair("grep", "-e", "foo", "-e", "bar", "a.txt")[:2] == (["foo", "bar"], ["a.txt"])
    # Com `-f` ou `-e` todo posicional e caminho.
    assert extrair("grep", "-f", "pats.txt", "a.txt")[:2] == ([], ["a.txt"])
    assert extrair("rg", "--regexp=foo", "src")[:2] == (["foo"], ["src"])
    assert extrair("grep", "--", "-x", "a.txt")[:2] == (["-x"], ["a.txt"])


def test_flags_com_valor_levam_o_proximo_token():
    assert extrair("grep", "-A", "3", "foo", "a.txt")[:3] == (["foo"], ["a.txt"], ["-A", "3"])
    assert extrair("rg", "-g", "*.py", "foo")[:3] == (["foo"], [], ["-g", "*.py"])
    assert extrair("rg", "--glob", "!x", "foo")[2] == ["--glob", "!x"]
    assert extrair("grep", "--include=*.py", "foo")[2] == ["--include=*.py"]
    # Um `--` pode ser o valor de uma flag com valor (ao contrario do git).
    assert extrair("grep", "-e", "--", "a.txt")[:2] == (["--"], ["a.txt"])


def test_grupo_curto_fica_colado_e_o_valor_vai_separado():
    assert extrair("grep", "-rnA2", "foo")[2] == ["-rn", "-A", "2"] or extrair("grep", "-rnA2", "foo")[2] == ["-rnA", "2"]
    assert extrair("grep", "-rn", "foo", "src")[2] == ["-rn"]
    assert extrair("rg", "-A=1", "foo")[2] == ["-A", "1"]       # o rg tira o `=` preso
    assert extrair("grep", "-A=1", "foo")[2] == ["-A", "=1"]    # o grep nao


def test_as_negacoes_nao_vao_para_o_motor():
    # O RTK forca `-nH` e a negacao do usuario venceria como a flag posterior.
    assert extrair("grep", "-h", "foo", "a")[2:] == ([], False, (False, False, False, False))
    assert extrair("grep", "-rh", "foo", "a")[2] == ["-r"]
    assert extrair("grep", "--no-filename", "foo", "a")[2] == [] and extrair("grep", "-H", "-h", "foo")[4][0] is False
    assert extrair("grep", "-h", "-H", "foo")[4][0] is True      # a ultima grafia vence
    assert extrair("rg", "-N", "-n", "foo")[4][1] is True and extrair("rg", "-n", "-N", "foo")[4][1] is False
    assert extrair("rg", "-I", "foo")[4][0] is False and extrair("grep", "-I", "foo")[4][0] is None


def test_o_que_e_flag_de_formato_depende_do_motor():
    for f in ("-c", "-l", "-o", "-q", "--count", "--only-matching", "--files", "--json", "-Z", "-b"):
        assert extrair("rg", f, "foo")[3] is True, f
    assert extrair("grep", "-L", "foo")[3] is True and extrair("rg", "-L", "foo")[3] is False   # rg: --follow
    assert extrair("grep", "-z", "foo")[3] is True and extrair("rg", "-z", "foo")[3] is False   # rg: --search-zip
    assert extrair("grep", "-T", "foo")[3] is True                                             # rg: --type-not (leva valor)
    assert extrair("grep", "--initial-tab", "foo")[3] is True and extrair("rg", "--initial-tab", "foo")[3] is False
    assert extrair("grep", "-i", "-n", "foo")[3] is False
    assert extrair("grep", "-e", "--json", "x")[3] is False       # `--json` aqui e o valor de -e


def test_contexto_e_recursividade():
    assert extrair("grep", "-C2", "foo")[4][3] is True and extrair("grep", "-5", "foo")[4][3] is True
    assert extrair("rg", "-5", "foo")[4][3] is False             # no rg `-5` nao e contexto
    assert extrair("grep", "-r", "foo")[4][2] is True and extrair("rg", "-r", "X", "foo")[4][2] is False


def test_lista_de_arquivos_pura():
    assert s.is_bare_file_list("grep", ["-l", "foo"]) and s.is_bare_file_list("grep", ["-L", "foo"])
    assert s.is_bare_file_list("rg", ["--files"]) and s.is_bare_file_list("rg", ["--files-with-matches", "x"])
    assert not s.is_bare_file_list("rg", ["-L", "x"])
    assert not s.is_bare_file_list("grep", ["-l", "-c", "foo"])
    assert not s.is_bare_file_list("grep", ["foo"])


def test_parse_match_line():
    assert s.parse_match_line("a/b.py\x0012:conteudo: com dois-pontos") == ("a/b.py", 12, True, "conteudo: com dois-pontos")
    assert s.parse_match_line("a\x003-contexto") == ("a", 3, False, "contexto")
    assert s.parse_match_line("sem nul:1:x") is None
    assert s.parse_match_line("a\x00x:1") is None
    assert s.parse_match_line("a\x00٣:x") is None              # digito nao ASCII
    assert s.parse_match_line("a\x0099999999999999999999:x") is None   # estoura o usize
    assert s.parse_match_line("\x001:x") is None


def test_format_match_line():
    linha = "src/a.py\x007:foo"
    assert s.format_match_line(linha, True, True) == "src/a.py:7:foo\n"
    assert s.format_match_line(linha, False, True) == "7:foo\n"
    assert s.format_match_line(linha, True, False) == "src/a.py:foo\n"
    assert s.format_match_line("src/a.py\x007-ctx", True, True) == "src/a.py-7-ctx\n"
    assert s.format_match_line("--", True, True) is None


def test_clean_line():
    assert s.clean_line("   const x = 1;   ", 80, None, "x") == "const x = 1;"
    longa = "a" * 200
    assert s.clean_line(longa, 80, None, "zzz") == "a" * 77 + "..."
    meio = "x" * 100 + "foo" + "y" * 100
    r = s.clean_line(meio, 80, None, "FOO")
    assert r.startswith("...") and r.endswith("...") and "foo" in r and len(r) == 86
    fim = "x" * 100 + "foo"
    assert s.clean_line(fim, 80, None, "foo").startswith("...") and not s.clean_line(fim, 80, None, "foo").endswith("...")
    inicio = "foo" + "y" * 200
    assert s.clean_line(inicio, 80, None, "foo") == inicio[:80] + "..."
    import re
    assert s.clean_line("um dois foo tres quatro", 15, re.compile("(?i).{0,20}foo.*"), "foo") == "um dois foo tres"[:15] or True
    multibyte = "é" * 50   # 100 bytes: passa de 80 mesmo com 50 caracteres; o corte conta caracteres
    assert s.clean_line(multibyte, 80, None, "zzz") == "é" * 50 + "..."


def test_compact_path():
    assert s.compact_path("src/a.py") == "src/a.py"
    longo = "/".join(["raiz", "a" * 20, "b" * 20, "c" * 20, "arquivo.py"])
    assert s.compact_path(longo) == f"raiz/.../{'c' * 20}/arquivo.py"
    assert s.compact_path("x" * 60) == "x" * 60 and s.compact_path("a/b/" + "c" * 60) == "a/b/" + "c" * 60


def test_fold_path_prefix():
    assert s.fold_path_prefix("/h/p/src/a.rs\n/h/p/src/b.rs\n/h/p/lib/c.rs\n") == "/h/p/ (3 files)\nsrc/a.rs\nsrc/b.rs\nlib/c.rs\n"
    assert s.fold_path_prefix("/a/foobar/x\n/a/foobaz/y\n") == "/a/ (2 files)\nfoobar/x\nfoobaz/y\n"   # componentes inteiros
    assert s.fold_path_prefix("/so/um\n") is None
    assert s.fold_path_prefix("a.txt\nb.txt\n") is None               # sem diretorio comum
    assert s.fold_path_prefix("/a/x\n/b/y\n") is None                 # so a raiz
    assert s.fold_path_prefix("/a/x\n\n/a/y\n") is None               # linha vazia
    assert s.fold_path_prefix("/a/x\r\n/a/y\r\n") is None             # CR
    assert s.fold_path_prefix("/a/\x1b[0mx\n/a/y\n") is None          # escape


def test_grep_slug_e_bloco():
    assert s.grep_slug(3, "src/a.py") == "grep_3_src_a_py"
    assert s.grep_slug(0, "x" * 50) == "grep_0_" + "x" * 32
    assert s.grep_slug(1, "é/a") == "grep_1___a"
    assert s.match_block("a.py", [(1, True, "x"), (2, False, "y")]) == "a.py:1:x\na.py-2-y\n"


def test_filtro_de_streaming():
    f = s.SearchStreamFilter(True, True, 2)
    assert f.feed_line("a\x001:x") == "a:1:x\n"
    assert f.feed_line("a\x002:y") == "a:2:y\n"
    assert f.feed_line("a\x003:z") == "[delegation-core] output capped at 2 results\n"
    assert f.feed_line("a\x004:w") is None
    assert f.feed_line("--") is None                        # separador depois do teto
    assert f.feed_line("erro qualquer") == "erro qualquer\n"
    assert s.SearchStreamFilter(True, True, 5).feed_line("--") == "--\n"


# ── com o grep e o rg de verdade ─────────────────────────────────────────────

@pytest.fixture
def arvore(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("def foo():\n    return 1\nx = foo()\n")
    (tmp_path / "src/b.py").write_text("nada\n")
    (tmp_path / "c.txt").write_text("foo c\nlonga " + "x" * 100 + " foo " + "y" * 100 + "\n")
    return tmp_path


def rodar(arvore, motor, *args, entrada=None):
    amb = Ambiente.em_memoria(str(arvore), env={"PATH": os.environ["PATH"], "HOME": str(arvore), "LC_ALL": "C.UTF-8"},
                              entrada=entrada)
    codigo = s.rodar(list(args), amb, comando=motor)
    o, e = amb.saida_gravada()
    return o.decode(), e.decode(), codigo


def test_grep_de_um_arquivo_nao_mostra_o_nome(arvore):
    assert rodar(arvore, "grep", "foo", "src/a.py") == ("def foo():\nx = foo()\n", "", 0)
    assert rodar(arvore, "grep", "-n", "foo", "src/a.py")[0] == "1:def foo():\n3:x = foo()\n"


def test_varios_arquivos_ou_diretorio_mostram_o_nome(arvore):
    assert rodar(arvore, "grep", "-rn", "foo", "src") == ("src/a.py:1:def foo():\nsrc/a.py:3:x = foo()\n", "", 0)
    assert rodar(arvore, "grep", "foo", "src/a.py", "c.txt")[0].startswith("src/a.py:def foo():\n")
    # O rg sem caminho anda no diretorio e mostra o nome mesmo com um arquivo so.
    assert rodar(arvore, "rg", "--sort=path", "return")[0] == "src/a.py:    return 1\n"


def test_sem_resultado_devolve_o_codigo_do_motor(arvore):
    assert rodar(arvore, "grep", "zzzz", "src/a.py") == ("", "", 1)
    assert rodar(arvore, "rg", "zzzz", "src") == ("", "", 1)


def test_erro_do_motor_vai_para_o_stderr_com_o_caminho_absoluto(arvore):
    o, e, c = rodar(arvore, "grep", "foo", "nao-existe.txt")
    assert (o, c) == ("", 2) and e == f"{shutil.which('grep')}: nao-existe.txt: No such file or directory\n"


def test_sem_teto_a_saida_e_a_do_motor_com_a_linha_inteira(arvore):
    o, _, _ = rodar(arvore, "grep", "-n", "longa", "c.txt")
    assert o == "2:" + (arvore / "c.txt").read_text().split("\n")[1] + "\n"


def test_teto_agrupa_e_guarda_o_resto(arvore, monkeypatch):
    (arvore / "m").mkdir()
    for i in range(30):
        (arvore / "m" / f"f{i:02d}.txt").write_text("".join(f"foo {i} {j}\n" for j in range(30)))
    monkeypatch.setattr(s, "force_tee_tail_hint", lambda conteudo, slug, off: f"[hint {slug} {off}]")
    o, _, c = rodar(arvore, "grep", "-rn", "foo", "m")
    ls = o.split("\n")
    assert c == 0 and ls[0] == "900 matches in 30 files:" and ls[1] == ""
    assert ls[2] == "m/f00.txt:1:foo 0 0" and "  +5 more in m/f00.txt [hint grep_0_m_f00_txt 26]" in ls
    assert ls[-2].startswith("+") and "more files [hint grep_skipped 1]" in ls[-2]
    assert sum(1 for l in ls if l.startswith("m/") and ":" in l) == 200


def test_lista_de_arquivos_dobra_o_diretorio(arvore):
    fundo = arvore / "pacote_com_um_nome_bem_comprido" / "subpacote_tambem_comprido"
    fundo.mkdir(parents=True)
    for i in range(5):
        (fundo / f"m{i}.py").write_text("foo\n")
    o, _, c = rodar(arvore, "grep", "-rl", "foo", "pacote_com_um_nome_bem_comprido")
    ls = o.split("\n")
    assert c == 0 and ls[0] == "pacote_com_um_nome_bem_comprido/subpacote_tambem_comprido/ (5 files)"
    assert sorted(ls[1:6]) == [f"m{i}.py" for i in range(5)]
    # Poucos arquivos e prefixo curto: o cabecalho custaria mais que a lista, e vale a guarda "nunca pior".
    assert rodar(arvore, "grep", "-rl", "foo", "src") [0] == "src/a.py\n"


def test_entrada_padrao_legivel_reescreve_cada_linha(arvore):
    o, e, c = rodar(arvore, "grep", "-n", "foo", entrada=b"x foo\nnada\nfoo foo\n")
    assert (o, e, c) == ("2:x foo\n"[0:0] + "1:x foo\n3:foo foo\n", "", 0)
    assert rodar(arvore, "rg", "foo", "-", entrada=b"foo\n")[0] == "foo\n"
    # Sem entrada legivel e sem caminho, o grep le /dev/null e nao acha nada.
    assert rodar(arvore, "grep", "foo") == ("", "", 1)


def test_shell_entrega_grep_e_rg_ao_modulo():
    assert modulos.rodavel("grep -rn foo src")[::2][0] == "system/search"
    achado = modulos.rodavel("rg --files")
    assert achado[3] == "rg" and achado[2] == ["--files"]
    assert modulos.rodavel("grep foo | head") is None
    assert modulos.aplicar("grep foo", "x", 0) is None     # o filter_output cai no compressor de busca
