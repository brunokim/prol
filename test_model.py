import pytest
from model import *


@pytest.mark.parametrize("terms, expected", [
    ([], Atom("[]")),
    ([Atom("a")], Struct(".", Atom("a"), Atom("[]"))),
    ([Var("X"), Var("Y")], Struct(".", Var("X"), Struct(".", Var("Y"), Atom("[]")))),
    ([Var("A"), Var("B"), Var("C")], Struct(".", Var("A"), Struct(".", Var("B"), Struct(".", Var("C"), Atom("[]"))))),
])
def test_to_list(terms, expected):
    assert to_list(terms) == expected


@pytest.mark.parametrize("terms, tail, expected", [
    ([], Var("X"), Var("X")),
    ([Atom("a")], Atom("b"), Struct(".", Atom("a"), Atom("b"))),
    ([Var("X")], Struct(".", Var("Y"), Atom("[]")), Struct(".", Var("X"), Struct(".", Var("Y"), Atom("[]")))),
])
def test_to_list_tail(terms, tail, expected):
    assert to_list(terms, tail) == expected


@pytest.mark.parametrize("l, terms, tail", [
    (Struct(".", Var("A"), Var("B")), [Var("A")], Var("B")),
    (Atom("[]"), [], Atom("[]")),
    (Struct(".", Atom("a"), Atom("[]")), [Atom("a")], Atom("[]")),
    (Struct(".", Atom("a"), Struct(".", Atom("b"), Atom("[]"))), [Atom("a"), Atom("b")], Atom("[]")),
])
def test_from_list(l, terms, tail):
    assert from_list(l) == (terms, tail)


@pytest.mark.parametrize("terms", [
    [],
    [Atom("a")],
    [Atom("a"), Atom("b")],
    [Atom("a"), Atom("b"), Atom("c")],
])
def test_idempotent_to_from_list(terms):
    l = to_list(terms)
    assert (terms, Atom("[]")) == from_list(l)


@pytest.mark.parametrize("l", [
    Var("Z"),
    Struct(".", Var("A"), Var("B")),
    Struct(".", Atom("a"), Atom("[]")),
    Struct(".", Atom("a"), Struct(".", Atom("b"), Atom("[]"))),
    Struct(".", Struct(".", Atom("a"), Atom("[]")), Struct(".", Atom("b"), Atom("[]"))),
])
def test_idempotent_from_to_list(l):
    terms, tail = from_list(l)
    assert l == to_list(terms, tail)
