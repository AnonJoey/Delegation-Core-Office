"""Testes do `compact_diff` e do cabecalho de diff do `git_cmd.rs` do RTK (traduzidos a mao e revisados).

A paridade byte a byte com o binario do RTK, sobre diffs sinteticos, esta em
`scripts/paridade_rtk_gh.py` (o `gh pr diff` entrega o texto cru ao `compact_diff`).
"""

from delegation_core.filtros_saida.modulos.git.compact_diff import (
    USIZE_MAX, compact_diff, diff_header_path, hunk_truncation_note, parse_hunk_header, unescape_path)


def _linhas(texto):
    return texto.split("\n")


def test_compact_diff():
    diff = 'diff --git a/foo.rs b/foo.rs\n--- a/foo.rs\n+++ b/foo.rs\n@@ -1,3 +1,4 @@\n fn main() {\n+    println!("hello");\n }\n'
    r = compact_diff(diff, 100)
    assert "foo.rs" in r and "+" in r


def test_hunk_lines_are_grep_anchorable():
    diff = ("diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n@@ -1,5 +1,4 @@\n"
            " keep1\n-DELETED_A\n keep2\n-DELETED_B\n+ADDED\n")
    r = compact_diff(diff, 100)
    ls = _linhas(r)
    assert [l for l in ls if l.startswith("-")] == ["-DELETED_A", "-DELETED_B"]
    assert [l for l in ls if l.startswith("+")] == ["+ADDED"]
    # O saldo do RTK fica indentado para que o mesmo grep nao o conte como linha do diff.
    assert "  +1 -2" in r
    assert " keep1" in ls and " keep2" in ls


def test_keeps_content_starting_with_plus_or_minus():
    diff = "diff --git a/f.sql b/f.sql\n--- a/f.sql\n+++ b/f.sql\n@@ -1,2 +1,2 @@\n--- sql comment\n+++i;\n"
    r = compact_diff(diff, 100)
    assert "--- sql comment" in _linhas(r) and "+++i;" in _linhas(r)
    assert "  +1 -1" in r


def test_leading_context_has_its_own_budget():
    diff = "diff --git a/f.rs b/f.rs\n@@ -1,120 +1,120 @@\n"
    diff += "".join(f" ctx{i}\n" for i in range(20)) + "".join(f"-del{i}\n" for i in range(100))
    ls = _linhas(compact_diff(diff, 1000))
    assert sum(1 for l in ls if l.startswith(" ctx")) == 3
    assert sum(1 for l in ls if l.startswith("-del")) == 100
    assert "truncated" not in "\n".join(ls)


def test_leading_context_is_adjacent_to_the_change():
    diff = "diff --git a/f.rs b/f.rs\n@@ -1,11 +1,11 @@\n" + "".join(f" ctx{i}\n" for i in range(1, 11)) + "-old\n+new\n"
    ls = _linhas(compact_diff(diff, 500))
    assert [l for l in ls if l.startswith(" ctx")] == [" ctx8", " ctx9", " ctx10"]


def test_combined_diff_headers_are_not_hunk_content():
    secao = ("index ba2906d,e45c9c2..0000000\n--- a/{0}\n+++ b/{0}\n@@@ -1,1 -1,1 +1,5 @@@\n"
             "++<<<<<<< HEAD\n +main\n++=======\n+ side\n++>>>>>>> side\n")
    diff = "diff --cc a.txt\n" + secao.format("a.txt") + "diff --cc z.txt\n" + secao.format("z.txt")
    r = compact_diff(diff, 500)
    ls = _linhas(r)
    assert not any(l.startswith("+++ b/") for l in ls)
    assert "z.txt" in r
    # Uma coluna de marcador por pai: ` +main` e acrescimo contra o segundo pai.
    assert r.count("  +5 -0") == 2
    assert sum(1 for l in ls if l.startswith("+")) == 8


def test_mbox_signature_is_not_a_deletion():
    diff = ("From abc Mon Sep 17 00:00:00 2001\nSubject: [PATCH 1/2] one\n\n---\n f.txt | 2 +-\n\n"
            "diff --git a/f.txt b/f.txt\n--- a/f.txt\n+++ b/f.txt\n@@ -1,2 +1,2 @@\n-old1\n+new1\n tail1\n-- \n2.40.0\n\n"
            "From def Mon Sep 17 00:00:00 2001\nSubject: [PATCH 2/2] two\n\n---\n"
            "diff --git a/g.txt b/g.txt\n--- a/g.txt\n+++ b/g.txt\n@@ -1,2 +1,2 @@\n-old2\n+new2\n tail2\n-- \n2.40.0\n")
    r = compact_diff(diff, 500)
    assert [l for l in _linhas(r) if l.startswith("-")] == ["-old1", "-old2"]
    assert "Subject:" not in r
    assert "  +1 -1" in r


def test_extra_range_does_not_strand_a_hunk():
    out = compact_diff("diff --cc f\n@@@ -1 -1 -1 +0,0 @@@\n--x\n-- \n2.40.0\n", 100)
    assert "--x" in out and "2.40.0" not in out and "-- " not in out
    assert "+0 -1" in out


def test_missing_range_keeps_the_body():
    out = compact_diff("diff --cc f\n@@@ -1 +1 @@@\n +kept\n -lost\n", 100)
    assert " +kept" in out and " -lost" in out


def test_non_ascii_body_line_without_a_marker_does_not_fail():
    # `--word-diff` nao tem coluna de marcador e o conteudo pode comecar por varios bytes.
    out = compact_diff("diff --git a/f b/f\n@@ -1,2 +1,2 @@\nééé sem marcador\n+x\n", 100)
    assert "+x" in out


def test_hunk_over_the_limit_is_cut_and_says_how_much():
    diff = "diff --git a/f b/f\n@@ -1,0 +1,150 @@\n" + "".join(f"+linha{i}\n" for i in range(150))
    r = compact_diff(diff, 1000)
    ls = _linhas(r)
    assert sum(1 for l in ls if l.startswith("+linha")) == 100
    assert "  ... (50 additions truncated)" in ls
    assert "  +150 -0" in ls
    assert ls[-1] == "[full diff: delegation-core shell 'git diff --no-compact']"


def test_diff_over_max_lines_is_cut():
    diff = "".join(f"diff --git a/f{i} b/f{i}\n@@ -1 +1 @@\n-a\n+b\n" for i in range(300))
    r = compact_diff(diff, 100)
    assert "\n... (more changes truncated)" in r
    assert r.endswith("[full diff: delegation-core shell 'git diff --no-compact']")


def test_hunk_truncation_note_counts_one_as_singular():
    assert hunk_truncation_note(0, 0) is None
    assert hunk_truncation_note(0, 1) == "  ... (1 addition truncated)"
    assert hunk_truncation_note(1, 0) == "  ... (1 deletion truncated)"
    assert hunk_truncation_note(2, 3) == "  ... (2 deletions, 3 additions truncated)"
    assert hunk_truncation_note(1, 1) == "  ... (1 deletion, 1 addition truncated)"


def test_hunk_header_keeps_the_function_context():
    out = compact_diff("diff --git a/f b/f\n@@ -10,2 +10,2 @@ def funcao(x):\n-a\n+b\n", 100)
    assert "@@ -10,2 +10,2 @@ def funcao(x):" in _linhas(out)


def test_parse_hunk_header_counts():
    h = parse_hunk_header("@@ -1,3 +4,5 @@ ctx")
    assert (h.parents, h.new, h.prefix_width) == ([3], 5, 1)
    h = parse_hunk_header("@@ -1 +1 @@")  # sem contagem: vale 1
    assert (h.parents, h.new) == ([1], 1)
    assert parse_hunk_header("@ -1 +1 @") is None
    assert parse_hunk_header("texto") is None
    assert parse_hunk_header("@@ -1,x +1 @@") is None


def test_parse_hunk_header_reconciles_ranges_with_marker_columns():
    h = parse_hunk_header("@@@ -1 +1 @@@")
    assert h.prefix_width == 2 and h.parents == [1, USIZE_MAX]
    h = parse_hunk_header("@@@ -1 -1 -1 +0,0 @@@")
    assert h.prefix_width == 2 and h.parents == [1, 1]


def test_parse_hunk_header_count_is_a_usize():
    assert parse_hunk_header("@@ -1,+3 +1 @@").parents == [3]
    assert parse_hunk_header("@@ -1,-3 +1 @@") is None
    assert parse_hunk_header("@@ -1,99999999999999999999 +1 @@") is None
    assert parse_hunk_header("@@ -1,٣ +1 @@") is None


def test_diff_header_path_keeps_spaces():
    assert diff_header_path("diff --git a/my file.txt b/my file.txt") == "my file.txt"
    assert diff_header_path("diff --cc my file.txt") == "my file.txt"
    assert diff_header_path("diff --combined my file.txt") == "my file.txt"


def test_diff_header_path_splits_the_pair_at_its_midpoint():
    # Um diretorio chamado `x b` nao parte o caminho na primeira ocorrencia de ` b/`.
    assert diff_header_path("diff --git a/x b/y.txt b/x b/y.txt") == "x b/y.txt"
    assert diff_header_path("diff --git x/same.txt y/same.txt") == "same.txt"
    assert diff_header_path("diff --git a/old.txt b/new.txt") == "new.txt"


def test_diff_header_path_does_not_split_single_path_headers():
    assert diff_header_path("diff --cc dup dup") == "dup dup"
    assert diff_header_path("diff --git") == "unknown"


def test_diff_header_path_unescapes_gits_default_quoting():
    q = '"a/\\303\\251t\\303\\251.txt" "b/\\303\\251t\\303\\251.txt"'
    assert diff_header_path("diff --git " + q) == "été.txt"
    assert diff_header_path('diff --cc "\\303\\251t\\303\\251.txt"') == "été.txt"
    assert diff_header_path('diff --git a/plain.txt "b/\\303\\251t.txt"') == "ét.txt"
    assert diff_header_path('diff --git "a/\\303\\251t.txt" b/plain.txt') == "plain.txt"
    assert diff_header_path('diff --cc "tab\\there.txt"') == "tab\there.txt"
    assert diff_header_path('diff --cc "quote\\"here.txt"') == 'quote"here.txt'
    assert diff_header_path('diff --cc "back\\\\slash.txt"') == "back\\slash.txt"


def test_unescape_path_keeps_a_backslash_that_is_not_an_octal_escape():
    assert unescape_path("a\\8b") == "a\\8b"      # 8 nao e algarismo octal
    assert unescape_path("a\\777b") == "a\\777b"  # 511 nao cabe num byte
    assert unescape_path("fim\\") == "fim\\"
    assert unescape_path("\\101") == "A"
