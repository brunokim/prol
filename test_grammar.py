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
