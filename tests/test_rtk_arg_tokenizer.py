"""Testes do `arg_tokenizer.rs` do RTK, no dialeto POSIX (traduzidos a mao e revisados)."""

from delegation_core.filtros_saida.modulos.arg_tokenizer import (
    DASH_DASH, LONG, POSITIONAL, SHORT, ValueSpec, before_dashdash, dashdash_index, is_digit_run,
    tokenize, tokenize_grammar)


def test_attached_only_bars_a_separate_value_in_both_kinds():
    # Curta: `-M`/`-U` do git levem um numero preso e nunca o token seguinte.
    t = tokenize_grammar(["-M", "50", "f.txt"], lambda k, n: ValueSpec.attached() if n == "M" else None)
    assert t[0].text == "M" and t[0].linked is None and t[0].value(t) is None
    assert t[1].is_free_positional()
    # Longa.
    t = tokenize_grammar(["--min-parents", "2"], lambda k, n: ValueSpec.attached() if n == "min-parents" else None)
    assert t[0].linked is None and t[1].is_free_positional()
    # A forma presa continua valendo nas duas.
    t = tokenize_grammar(["-M50", "--min-parents=2"],
                         lambda k, n: ValueSpec.attached() if n in ("M", "min-parents") else None)
    assert t[0].value(t) == "50" and t[1].value(t) == "2"


def test_solo_only_restricts_a_short_flag_to_the_whole_argument():
    takes = lambda k, n: ValueSpec.solo() if n == "n" else None  # noqa: E731
    t = tokenize_grammar(["-n", "2"], takes)
    assert t[0].value(t) == "2"
    # Agrupada: `git log -pn 2` o git rejeita, e o 2 fica posicional.
    t = tokenize_grammar(["-pn", "2"], takes)
    n = next(x for x in t if x.text == "n")
    assert n.value(t) is None
    assert t[-1].is_free_positional()


def test_claiming_dash_dash_is_per_flag_not_global():
    args = ["-e", "--", "f.txt"]
    t = tokenize_grammar(args, lambda k, n: ValueSpec.value() if n == "e" else None)
    assert t[0].value(t) is None and t[1].kind == DASH_DASH
    t = tokenize_grammar(args, lambda k, n: ValueSpec.value().claiming_dash_dash() if n == "e" else None)
    assert t[0].value(t) == "--"
    assert all(x.kind != DASH_DASH for x in t)


def test_empty_args_yield_no_tokens():
    assert tokenize([]) == []


def test_dash_p_after_double_dash_is_positional_not_a_flag():
    t = tokenize(["--", "-p"])
    assert (t[0].kind, t[1].kind, t[1].text) == (DASH_DASH, POSITIONAL, "-p")


def test_second_double_dash_is_positional_text_not_another_separator():
    t = tokenize(["--", "--", "file"])
    assert [(x.kind, x.text) for x in t] == [(DASH_DASH, ""), (POSITIONAL, "--"), (POSITIONAL, "file")]


def test_value_taking_long_flag_consumes_and_links_next_token():
    t = tokenize_grammar(["--grep", "-p"], lambda k, n: ValueSpec.value() if (k, n) == (LONG, "grep") else None)
    assert len(t) == 2
    assert (t[0].kind, t[0].text, t[0].linked) == (LONG, "grep", 1)
    assert (t[1].kind, t[1].text, t[1].linked) == (POSITIONAL, "-p", 0)


def test_value_taking_flag_never_swallows_the_unseen_boundary_dashdash():
    t = tokenize_grammar(["--grep", "--", "pattern"], lambda k, n: ValueSpec.value() if n == "grep" else None)
    assert t[0].linked is None
    assert [x.kind for x in t] == [LONG, DASH_DASH, POSITIONAL]
    t = tokenize_grammar(["-A", "--", "pattern"], lambda k, n: ValueSpec.value() if (k, n) == (SHORT, "A") else None)
    assert t[0].linked is None and t[1].kind == DASH_DASH and t[2].text == "pattern"


def test_short_cluster_is_scanned_char_by_char_and_shares_one_source_index():
    t = tokenize(["-xyz", "arq"])
    assert [(x.kind, x.text, x.source_index) for x in t] == [
        (SHORT, "x", 0), (SHORT, "y", 0), (SHORT, "z", 0), (POSITIONAL, "arq", 1)]


def test_digit_run_is_one_short_token():
    t = tokenize(["-20"])
    assert [(x.kind, x.text) for x in t] == [(SHORT, "20")]
    assert is_digit_run("20") and not is_digit_run("") and not is_digit_run("2a") and not is_digit_run("٣")


def test_value_attached_to_a_short_cluster_is_the_remainder():
    t = tokenize_grammar(["-pU3", "x"], lambda k, n: ValueSpec.attached() if n == "U" else None)
    assert [(x.text, x.attached) for x in t[:2]] == [("p", None), ("U", "3")]
    assert t[2].is_free_positional()


def test_long_flag_equals_splits_at_the_first_equals_only():
    t = tokenize(["--format=%h=%s"])
    assert (t[0].text, t[0].attached, t[0].double_dash) == ("format", "%h=%s", True)


def test_lone_dash_is_positional():
    assert [(x.kind, x.text) for x in tokenize(["-"])] == [(POSITIONAL, "-")]


def test_before_dashdash_and_index():
    t = tokenize(["-a", "--", "-b"])
    assert dashdash_index(t) == 1
    assert [x.text for x in before_dashdash(t)] == ["a"]
    assert before_dashdash(tokenize(["-a"])) == tokenize(["-a"])


def test_value_with_a_stale_link_index_never_raises():
    t = tokenize_grammar(["--grep", "x"], lambda k, n: ValueSpec.value() if n == "grep" else None)
    # Fatiado depois da flag: o indice de `linked` ja nao existe nesta fatia.
    assert t[0].value(t[:1]) is None
