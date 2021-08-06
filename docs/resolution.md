# Resolution strategy and unification

The Prolog query resolution strategy is not executed in parallel like shown above,
but in depth.
When a predicate with multiple clauses match the current term, we push a _choice point_
onto a stack.

A choice point is a structure that stores the current machine state, pointing to the
next clause to try in this predicate.
The execution flow continues testing the first clause; if the flow fails, that is,
reaches an unsatisfiable state, the latest choice point is popped and the state
restored, but now using the subsequent clause.
This is called _backtracking_.
Multiple choice points may be stacked representing branches yet to explore.

As we proceed on an hypothesis, we accumulate a set of variable bindings, that is, a
set of values that correspond to some of the variables.
A variable that has a term associated is said to be _bound_; a term that has no unbound
variable is said to be _ground_.
We may reach an unsatisfiable state, where the current bindings lead to a logic failure,
such as no facts matching the present term.
In this case, on backtrack, we undo all bindings that were created since the choice point,
really restoring to the same state.

We've said that we expect terms to "match", but weren't precise there. 
This "matching" is called _unification_, and consists in a very 
simple set of rules:

1. Two atoms unify if they are the same;
2. Two structs unify if their functor _f/n_ is the same, and all their args unify;
3. An unbound var unifies with any term and becomes bound to it;
4. A bound var unifies with a term if the term and the var's bound term unify;
5. Otherwise, unification fails.

In Prolog the unification is done with the `=` operator. The following query would be unified like follows:

```prolog
?- P1 = p(X, a, f(b)), P2 = p(f(Y), Y, X), P1 = P2.
```

* `P1 = p(X, a, f(b))` from rule 3 (binding: `P1 = p(X, a, f(b))`)
* `P2 = p(f(Y), Y, X)` from rule 3 (binding: `P2 = p(f(Y), Y, X)`)
* `P1 = P2`
* `p(X, a, f(b)) = P2` from rule 4 (applied to P1)
* `p(X, a, f(b)) = p(f(Y), Y, X)` from rule 4 (applied to P2)
* `X = f(Y), a = Y, f(b) = X` from rule 2 (functor: `p/3`)
* `a = Y, f(b) = X` from rule 3 (binding: `X = f(Y)`)
* `f(b) = X` from rule 3 (binding: `Y = a`)
* `f(b) = f(Y)` from rule 4 (applied to X)
* `b = Y` from rule 2 (functor: `f/1`)
* `b = a` from rule 4 (applied to Y)
* Fail, from rule 1

