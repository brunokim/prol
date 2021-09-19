from model import *
from grammar import *
import pytest


@pytest.mark.parametrize('text, term', [
    ('a', Atom('a')),
    ('  a', Atom('a')),
    (' a  ', Atom('a')),
    ('a\n  ', Atom('a')),
    ('b', Atom('b')),
    ('z', Atom('z')),
    ('a123', Atom('a123')),
    (':', Atom(':')),
    (':-', Atom(':-')),
    ('[]', Atom('[]')),
    ("'('", Atom('(')),
    ("'a123'", Atom('a123')),
    ("'_123'", Atom('_123')),
    ("a_123", Atom('a_123')),
    ("123", Atom('123')),
    ("_123", Var('_123')),
    ("X123", Var('X123')),
    ("f()", Struct("f")),
    ("f(  )", Struct("f")),
    ("f( a )", Struct("f", Atom("a"))),
    ("f(a ,b)", Struct("f", Atom("a"), Atom("b"))),
    ("f(a,b)", Struct("f", Atom("a"), Atom("b"))),
    ("f(a, b)", Struct("f", Atom("a"), Atom("b"))),
    ("f(a , b)", Struct("f", Atom("a"), Atom("b"))),
    ("f(a, b )", Struct("f", Atom("a"), Atom("b"))),
    ("f(a, g())", Struct("f", Atom("a"), Struct("g"))),
    ("f(a, g(X))", Struct("f", Atom("a"), Struct("g", Var("X")))),
])
def test_parse_term(text, term):
    assert parse_term(text) == term


@pytest.mark.parametrize('text, query', [
    ("f().", [Struct("f")]),
    ("f(X).", [Struct("f", Var("X"))]),
    ("f(X), a.", [Struct("f", Var("X")), Struct("a")]),
    (" X, a .", [Struct("call", Var("X")), Struct("a")]),
])
def test_parse_query(text, query):
    assert parse_query(text) == query


@pytest.mark.parametrize('text, clauses', [
    ("f().", [Clause(Struct("f"))]),
    ("f(). g().", [Clause(Struct("f")), Clause(Struct("g"))]),
    ("f(a).", [Clause(Struct("f", Atom("a")))]),
    ("f(a, b).", [Clause(Struct("f", Atom("a"), Atom("b")))]),
    ("f() :- a.", [Clause(Struct("f"), Struct("a"))]),
    ("f(X) :- g(X).", [Clause(Struct("f", Var("X")), Struct("g", Var("X")))]),
    ("""f(X) :- g(X).
        g(a).
    """, [
        Clause(Struct("f", Var("X")), Struct("g", Var("X"))),
        Clause(Struct("g", Atom("a"))),
    ]),
    ("p() :- a, X, q().", [Clause(Struct("p"), Struct("a"), Struct("call", Var("X")), Struct("q"))]),
    ("""
        parse_term(Chars, Term) :- parse_term(Term, Chars, []).
     """, [
        Clause(Struct("parse_term", Var("Chars"), Var("Term")),
            Struct("parse_term", Var("Term"), Var("Chars"), Atom("[]"))),
    ]),
])
def test_parse_kb(text, clauses):
    assert parse_kb(text) == clauses
