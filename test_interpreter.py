import pytest
from model import *
from interpreter import *

package = [
    # member(E, [H|T]) :- member_(T, E, H).
    # member_(_, E, E).
    # member_([H|T], E, _) :- member_(T, E, H).
    Clause(Struct("member", Var("E"), Struct(".", Var("H"), Var("T"))),
           Struct("member_", Var("T"), Var("E"), Var("H"))),
    Clause(Struct("member_", Var("_"), Var("E"), Var("E"))),
    Clause(Struct("member_", Struct(".", Var("H"), Var("T")), Var("E"), Var("_")),
           Struct("member_", Var("T"), Var("E"), Var("H"))),

    # length([], 0).
    # length([_|T], s(L)) :- length(T, L).
    Clause(Struct("length", Atom("[]"), Atom("0"))),
    Clause(Struct("length", Struct(".", Var("_"), Var("T")), Struct("s", Var("L"))),
           Struct("length", Var("T"), Var("L"))),

    # nat(0).
    # nat(s(X)) :- nat(X).
    Clause(Struct("nat", Atom("0"))),
    Clause(Struct("nat", Struct("s", Var("X"))),
           Struct("nat", Var("X"))),
]

testdata = [
    ([
        # ?- length(L, s(s(s(0)))), member(a, L).
        Struct("length", Var("L"), Struct("s", Struct("s", Struct("s", Atom("0"))))),
        Struct("member", Atom("a"), Var("L")),
    ], [
        Solution({Var("L"): to_list([Atom("a"), Var("_"), Var("_")])}),
        Solution({Var("L"): to_list([Var("_"), Atom("a"), Var("_")])}),
        Solution({Var("L"): to_list([Var("_"), Var("_"), Atom("a")])}),
    ]),
    ([
        # ?- nat(X).
        Struct("nat", Var("X")),
    ], [
        Solution({Var("X"): Atom("0")}),
        Solution({Var("X"): Struct("s", Atom("0"))}),
        Solution({Var("X"): Struct("s", Struct("s", Atom("0")))}),
        Solution({Var("X"): Struct("s", Struct("s", Struct("s", Atom("0"))))}),
    ]),
    ([
        # ?- member(f(X), [a, f(b), g(c), f(d)]).
        Struct("member", Struct("f", Var("X")), to_list([
            Atom("a"),
            Struct("f", Atom("b")),
            Struct("g", Atom("c")),
            Struct("f", Atom("d")),
        ])),
    ], [
        Solution({Var("X"): Atom("b")}),
        Solution({Var("X"): Atom("d")}),
    ]),
]


def ignore_vars(term: Term) -> Term:
    if isinstance(term, Atom):
        return term
    if isinstance(term, Var):
        return Var("_")
    if isinstance(term, Struct):
        return Struct(term.name, *(ignore_vars(arg) for arg in term.args))
    raise ValueError(f"unexpected term type {type(term)}")


def ignore_vars_in_solution(solution: Solution) -> Solution:
    return Solution({x: ignore_vars(term) for x, term in solution.items()})


@pytest.mark.parametrize("query, solutions", testdata)
def test_interpreter(query, solutions):
    wam = Machine(package, query)
    for got, want in zip(wam.run(), solutions):
        got = ignore_vars_in_solution(got)
        assert got == want
