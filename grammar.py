"""
Sample program of a parser that can generate its own instruction set.

This grammar can parse a program composed simply of atoms, vars and structs,
within the printable ASCII character set.

Atoms are reasonably capable, and can be either:
- composed of a lower case letter + identifier letters
- composed solely of digits
- composed solely of symbols
- having any char within single quotes. A single quote is itself represented by
two single quotes.

The grammar relies on two key concepts that are better explained in documentation:
lists as cons cells and incomplete lists.
"""

from interpreter import *
from model import *

from typing import cast, List, Iterable

__all__ = ['parse_term', 'parse_query', 'parse_kb']


def s0(name):
    return Struct(name)


def s(arg, *args):
    if isinstance(arg, Term):
        assert not args, f"{args} is not empty"
        return arg
    name = arg
    assert isinstance(name, str), f"{name} is not a string"
    if not args:
        if name[0] == '_' or name[0].isupper():
            return Var(name)
        return Atom(name)
    return Struct(name, *(s(arg) for arg in args))


def cons(head, tail):
    return s(".", head, tail)


def str_to_chars(text: str) -> Term:
    return to_list([Atom(ch) for ch in text])


def chars_to_str(chars: Term) -> str:
    atoms, tail = from_list(chars)
    if tail != Atom('[]'):
        raise ValueError(f"chars {chars} tail is not the empty atom")
    if not all(isinstance(atom, Atom) for atom in atoms):
        raise ValueError(f"some term is not an atom in {atoms}")
    chs = [atom.name for atom in cast(List[Atom], atoms)]
    if not all(len(ch) == 1 for ch in chs):
        raise ValueError(f"some atom doesn't contain a single character in {chars}")
    return ''.join(chs)


def query_term(term: Term) -> Struct:
    if isinstance(term, Var):
        return s("call", term)
    if isinstance(term, Atom):
        return s0(term.name)
    if isinstance(term, Struct):
        return term
    raise ValueError(f"unhandled term type {type(term)} ({term})")


def decode_term(encoded: Term) -> Term:
    if not isinstance(encoded, Struct):
        raise ValueError(f"decode_term: {encoded} is not a struct")
    term_type = encoded.name
    if term_type == 'atom':
        if len(encoded.args) != 1:
            raise ValueError(f"decode_term: encoded atom doesn't have exactly 1 arg: {encoded.args}")
        return Atom(chars_to_str(encoded.args[0]))
    if term_type == 'var':
        if len(encoded.args) != 1:
            raise ValueError(f"decode_term: encoded var doesn't have exactly 1 arg: {encoded.args}")
        return Var(chars_to_str(encoded.args[0]))
    if term_type == 'struct':
        if len(encoded.args) != 2:
            raise ValueError(f"decode_term: encoded struct doesn't have exactly 2 args: {encoded.args}")
        name_, args_ = encoded.args
        name = chars_to_str(name_)
        args = decode_terms(args_)
        return Struct(name, *args)
    raise ValueError(f"decode_term: unknown term type {term_type}")


def decode_terms(encoded: Term) -> List[Term]:
    terms, tail = from_list(encoded)
    if tail != Atom('[]'):
        raise ValueError(f"terms {encoded} tail is not the empty atom")
    return [decode_term(term) for term in terms]


def decode_clause(encoded: Term) -> Clause:
    if not isinstance(encoded, Struct):
        raise ValueError(f"decode_clause: {encoded} is not a struct")
    if encoded.name != "clause":
        raise ValueError(f"decode_clause: expected 'clause', got {encoded}")
    if len(encoded.args) == 1:
        head = decode_term(encoded.args[0])
        body = []
    elif len(encoded.args) == 2:
        head = decode_term(encoded.args[0])
        body = decode_terms(encoded.args[1])
    else:
        raise ValueError(f"decode_clause: expecting functor with 1 or 2 members, got {encoded}")

    if not isinstance(head, Struct):
        raise ValueError(f"decode_clause: clause head must be a struct, got {head}")
    return Clause(head, *(query_term(term) for term in body))


def decode_clauses(encoded: Term) -> List[Clause]:
    terms, tail = from_list(encoded)
    if tail != Atom('[]'):
        raise ValueError(f"clauses {encoded} tail is not the empty atom")
    return [decode_clause(term) for term in terms]


def parse_ast(text: str, grammar: str, *, store_deepest_state=False, debug_filename=None):
    try:
        chars = str_to_chars(text)
        m = Machine(facts + rules, [s(grammar, chars, "Tree")])
        m.store_deepest_state = store_deepest_state
        m.debug_filename = debug_filename
        solution = next(m.run())
        return solution[Var("Tree")]
    except StopIteration:
        if not m.deepest_state:
            raise RuntimeError(f"parse error, enable Machine.store_deepest_state for more info")
        envs = Env.stack(m.deepest_state.env)

        def env_frame(env):
            if not env.continuation:
                msg = "<none>"
            else:
                msg = str(env.continuation.functor)
            if env.num_executes:
                msg += f" + {env.num_executes} optimized frames"
            return msg
        call_stack = "\n    ".join(env_frame(env) for env in envs)
        raise RuntimeError(
            f"""parse error:\n  closest solution: {m.deepest_solution}\n  call stack:\n    {call_stack}""")


def parse_term(text: str, **kwargs) -> Term:
    return decode_term(parse_ast(text, "parse_term", **kwargs))


def parse_query(text: str, **kwargs) -> List[Struct]:
    terms = decode_terms(parse_ast(text, "parse_query", **kwargs))
    return [query_term(term) for term in terms]


def parse_kb(text: str, **kwargs) -> List[Clause]:
    return decode_clauses(parse_ast(text, "parse_kb", **kwargs))


# Set of facts about letters
facts = (
    [Clause(Struct("lower", Atom(chr(i)))) for i in range(ord('a'), ord('z')+1)] +
    [Clause(Struct("upper", Atom(chr(i)))) for i in range(ord('A'), ord('Z')+1)] +
    [Clause(Struct("digit", Atom(chr(i)))) for i in range(ord('0'), ord('9')+1)] +
    [Clause(Struct("space", Atom(ch))) for ch in " \n\t"] +
    [Clause(Struct("symbol", Atom(ch))) for ch in "\\=[].:-!@#$%&*+{}^~?/<>"]
)


# Actual grammar of this language. The comments are written in a higher Prolog
# syntax, with lists within brackets and using DCGs.
rules = [
    # parse_term(Chars, Term) :- parse_term(Term, Chars, []).
    # parse_term(Term) --> ws, term(Term), ws.
    Clause(s("parse_term", "Chars", "Term"),
           s("parse_term", "Term", "Chars", "[]")),
    Clause(s("parse_term", "Term", "T0", "T3"),
           s("ws", "T0", "T1"),
           s("term", "Term", "T1", "T2"),
           s("ws", "T2", "T3")),

    # parse_kb(Chars, Clauses) :- parse_kb(Clauses, Chars, []).
    # parse_kb(Clauses) --> ws, clauses(Clauses), ws.
    Clause(s("parse_kb", "Chars", "Clauses"),
           s("parse_kb", "Clauses", "Chars", "[]")),
    Clause(s("parse_kb", "Clauses", "T0", "T3"),
           s("ws", "T0", "T1"),
           s("clauses", "Clauses", "T1", "T2"),
           s("ws", "T2", "T3")),

    # parse_query(Chars, Terms) :- parse_query(Terms, Chars, []).
    # parse_query(Terms) --> ws, terms(Terms), ws, [.], ws.
    Clause(s("parse_query", "Chars", "Terms"),
           s("parse_query", "Terms", "Chars", "[]")),
    Clause(s("parse_query", "Terms", "T0", "T4"),
           s("ws", "T0", "T1"),
           s("terms", "Terms", "T1", "T2"),
           s("ws", "T2", cons(".", "T3")),
           s("ws", "T3", "T4")),

    # ws --> [Ch], {space(Ch)}, ws.
    # ws --> [].
    Clause(s("ws", cons("Ch", "T0"), "T1"),
           s("space", "Ch"),
           s("ws", "T0", "T1")),
    Clause(s("ws", "T", "T")),

    # ident(Ch) :- lower(Ch).
    # ident(Ch) :- upper(Ch).
    # ident(Ch) :- digit(Ch).
    # ident('_').
    Clause(s("ident", "Ch"), s("lower", "Ch")),
    Clause(s("ident", "Ch"), s("upper", "Ch")),
    Clause(s("ident", "Ch"), s("digit", "Ch")),
    Clause(s("ident", Atom("_"))),

    # idents([Ch|L]) --> [Ch], {ident(Ch)}, idents(L).
    # idents([]) --> [].
    Clause(s("idents", cons("Ch", "L"), cons("Ch", "T0"), "T1"),
           s("ident", "Ch"),
           s("idents", "L", "T0", "T1")),
    Clause(s("idents", "[]", "T", "T")),

    # symbols([Ch|L]) --> [Ch], {symbol(Ch)}, symbols(L).
    # symbols([]) --> [].
    Clause(s("symbols", cons("Ch", "L"), cons("Ch", "T0"), "T1"),
           s("symbol", "Ch"),
           s("symbols", "L", "T0", "T1")),
    Clause(s("symbols", "[]", "T", "T")),

    # digits([Ch|L]) --> [Ch], {digit(Ch)}, digits(L).
    # digits([]) --> [].
    Clause(s("digits", cons("Ch", "L"), cons("Ch", "T0"), "T1"),
           s("digit", "Ch"),
           s("digits", "L", "T0", "T1")),
    Clause(s("digits", "[]", "T", "T")),

    # atom(atom(L))      --> [''''], quoted(L).
    # atom(atom([Ch|L])) --> [Ch], {lower(Ch)}, idents(L).
    # atom(atom([Ch|L])) --> [Ch], {symbol(L)}, symbols(L).
    # atom(atom([Ch|L])) --> [Ch], {digit(L)}, digits(L).
    Clause(s("atom", s("atom", "L"), cons("'", "T0"), "T1"),
           s("quoted", "L", "T0", "T1")),
    Clause(s("atom", s("atom", cons("Ch", "L")), cons("Ch", "T0"), "T1"),
           s("lower", "Ch"),
           s("idents", "L", "T0", "T1")),
    Clause(s("atom", s("atom", cons("Ch", "L")), cons("Ch", "T0"), "T1"),
           s("symbol", "Ch"),
           s("symbols", "L", "T0", "T1")),
    Clause(s("atom", s("atom", cons("Ch", "L")), cons("Ch", "T0"), "T1"),
           s("digit", "Ch"),
           s("digits", "L", "T0", "T1")),

    # quoted([Ch|L])   --> [Ch], {Ch \== ''''}, quoted(L).
    # quoted([''''|L]) --> ['''', ''''], quoted(L).
    # quoted([]), [Ch] --> ['''', Ch], {Ch \== ''''}.
    # quoted([])       --> [''''].
    Clause(s("quoted", cons("Ch", "L"), cons("Ch", "T0"), "T1"),
           s(r"\==", "Ch", "'"),
           s("quoted", "L", "T0", "T1")),
    Clause(s("quoted", cons("'", "L"), cons("'", cons("'", "T0")), "T1"),
           s("quoted", "L", "T0", "T1")),
    Clause(s("quoted", "[]", cons("'", cons("Ch", "T")), cons("Ch", "T")),
           s(r"\==", "Ch", "'")),
    Clause(s("quoted", "[]", cons("'", "[]"), "[]")),

    # var(var([Ch|L])) --> [Ch], {upper(Ch)}, idents(L).
    # var(var(['_'|L])) --> ['_'], idents(L).
    Clause(s("var", s("var", cons("Ch", "L")), cons("Ch", "T0"), "T1"),
           s("upper", "Ch"),
           s("idents", "L", "T0", "T1")),
    Clause(s("var", s("var", cons(Atom("_"), "L")), cons(Atom("_"), "T0"), "T1"),
           s("idents", "L", "T0", "T1")),

    # struct(struct(Name, Args)) --> atom(atom(Name)), ['('], ws, terms(Args), ws, [')'].
    Clause(s("struct", s("struct", "Name", "Args"), "T0", "T4"),
           s("atom", s("atom", "Name"), "T0", cons("(", "T1")),
           s("ws", "T1", "T2"),
           s("terms", "Args", "T2", "T3"),
           s("ws", "T3", cons(")", "T4"))),

    # term(Term) --> struct(Term).
    # term(Term) --> atom(Term).
    # term(Term) --> var(Term).
    Clause(s("term", "Term", "T0", "T1"), s("struct", "Term", "T0", "T1")),
    Clause(s("term", "Term", "T0", "T1"), s("atom", "Term", "T0", "T1")),
    Clause(s("term", "Term", "T0", "T1"), s("var", "Term", "T0", "T1")),

    # terms([Term|Terms]) --> term(Term), ws, [','], ws, terms(Terms).
    # terms([Term])       --> term(Term).
    # terms([])           --> [].
    Clause(s("terms", cons("Term", "Terms"), "T0", "T4"),
           s("term", "Term", "T0", "T1"),
           s("ws", "T1", cons(",", "T2")),
           s("ws", "T2", "T3"),
           s("terms", "Terms", "T3", "T4")),
    Clause(s("terms", cons("Term", "[]"), "T0", "T1"),
           s("term", "Term", "T0", "T1")),
    Clause(s("terms", "[]", "T", "T")),

    # clause(clause(Fact)) --> struct(Fact), ws, [.].
    # clause(clause(Head, Body)) --> struct(Head), ws, [:, -], ws, terms(Body), ws, [.].
    Clause(s("clause", s("clause", "Fact"), "T0", "T2"),
           s("struct", "Fact", "T0", "T1"),
           s("ws", "T1", cons(".", "T2"))),
    Clause(s("clause", s("clause", "Head", "Body"), "T0", "T5"),
           s("struct", "Head", "T0", "T1"),
           s("ws", "T1", cons(":", cons("-", "T2"))),
           s("ws", "T2", "T3"),
           s("terms", "Body", "T3", "T4"),
           s("ws", "T4", cons(".", "T5"))),

    # clauses([Clause|L]) --> clause(Clause), ws, clauses(L).
    # clauses([]) --> []
    Clause(s("clauses", cons("Clause", "L"), "T0", "T3"),
           s("clause", "Clause", "T0", "T1"),
           s("ws", "T1", "T2"),
           s("clauses", "L", "T2", "T3")),
    Clause(s("clauses", "[]", "T", "T")),
]


def main():
    grammar = r"""
        parse_term(Chars, Term) :- parse_term(Term, Chars, []).
        parse_term(Term, T0, T3) :-
            ws(T0, T1),
            term(Term, T1, T2),
            ws(T2, T3).

        parse_kb(Chars, Clauses) :- parse_kb(Clauses, Chars, []).
        parse_kb(Clauses, T0, T3) :-
            ws(T0, T1),
            clauses(Clauses, T1, T2),
            ws(T2, T3).

        parse_query(Chars, Terms) :- parse_query(Terms, Chars, []).
        parse_query(Terms, T0, T4) :-
            ws(T0, T1),
            terms(Terms, T1, T2),
            ws(T2, .(., T3)),
            ws(T3, T4).

        ws(.(Ch, T0), T1) :-
            space(Ch),
            ws(T0, T1).
        ws(T, T).

        ident(Ch) :- lower(Ch).
        ident(Ch) :- upper(Ch).
        ident(Ch) :- digit(Ch).
        ident('_').

        idents(.(Ch, L), .(Ch, T0), T1) :-
            ident(Ch),
            idents(L, T0, T1).
        idents([], T, T).

        symbols(.(Ch, L), .(Ch, T0), T1) :-
            symbol(Ch),
            symbols(L, T0, T1).
        symbols([], T, T).

        digits(.(Ch, L), .(Ch, T0), T1) :-
            digit(Ch),
            digits(L, T0, T1).
        digits([], T, T).

        atom(atom(L), .('''', T0), T1) :-
            quoted(L, T0, T1).
        atom(atom(.(Ch, L)), .(Ch, T0), T1) :-
            lower(Ch),
            idents(L, T0, T1).
        atom(atom(.(Ch, L)), .(Ch, T0), T1) :-
            symbol(Ch),
            symbols(L, T0, T1).
        atom(atom(.(Ch, L)), .(Ch, T0), T1) :-
            digit(Ch),
            digits(L, T0, T1).

        quoted(.(Ch, L), .(Ch, T0), T1) :-
            \==(Ch, ''''),
            quoted(L, T0, T1).
        quoted(.('''', L), .('''', .('''', T0)), T1) :-
            quoted(L, T0, T1).
        quoted([], .('''', .(Ch, T)), .(Ch, T)) :-
            \==(Ch, '''').
        quoted([], .('''', []), []).

        var(var(.(Ch, L)), .(Ch, T0), T1) :-
            upper(Ch),
            idents(L, T0, T1).
        var(var(.('_', L)), .('_', T0), T1) :-
            idents(L, T0, T1).

        struct(struct(Name, Args), T0, T4) :-
            atom(atom(Name), T0, .('(', T1)),
            ws(T1, T2),
            terms(Args, T2, T3),
            ws(T3, .(')', T4)).

        term(Term, T0, T1) :- struct(Term, T0, T1).
        term(Term, T0, T1) :- atom(Term, T0, T1).
        term(Term, T0, T1) :- var(Term, T0, T1).

        terms(.(Term, Terms), T0, T4) :-
            term(Term, T0, T1),
            ws(T1, .(',', T2)),
            ws(T2, T3),
            terms(Terms, T3, T4).
        terms(.(Term, []), T0, T1) :-
            term(Term, T0, T1).
        terms([], T, T).

        clause(clause(Fact), T0, T2) :-
            struct(Fact, T0, T1),
            ws(T1, .(., T2)).
        clause(clause(Head, Body), T0, T5) :-
            struct(Head, T0, T1),
            ws(T1, .(:, .(-, T2))),
            ws(T2, T3),
            terms(Body, T3, T4),
            ws(T4, .(., T5)).

        clauses(.(Clause, L), T0, T3) :-
            clause(Clause, T0, T1),
            ws(T1, T2),
            clauses(L, T2, T3).
        clauses([], T, T).
    """
    kb = parse_kb(grammar)
    for i, (want, got) in enumerate(zip(rules, kb)):
        if want != got:
            raise AssertionError(f"clause #{i+1}:\n{want}\n\t!=\n{got}")
    for clause in kb:
        print(clause)


if __name__ == '__main__':
    main()
