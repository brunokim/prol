# Indices

Prolog's semantics requires that clauses are visited in the same order that they are
placed in source code. For example, the following predicate `vowel/1`

```prolog
vowel(a).
vowel(e).
vowel(i).
vowel(o).
vowel(u).
```

would always return the vowels in the same order for the query

```prolog
?- vowel(X).
  X = a ;
  X = e ;
  X = i ;
  X = o ;
  X = u .
```

However, there's an optimization for less general cases that wouldn't require us to visit
every clause of a predicate.
Assuming that the fact database is static, `vowel(u)` should be trivially true, and
`vowel(s(A))` should be trivially false.
We may approach this ideal by _indexing_ clauses based on their atomic or structured arguments.

## Level 0: by functor

The first level of indexing is almost trivial: when looking for clauses that may unify with a
term, we only consider clauses that form a predicate, that is, that share the same functor.
So, if we have the term `f(a, X)`, we will look only for clauses that have the same `f/2` functor.
Any other would never unify. 

## Level 1: constants vs variables

For this simplified implementation, we will only use the _first_ argument as an index key.
Using more arguments, or even constants nested within struct arguments, leads to more complex and
efficient indexing structures, but are also out of my abilities.
The original WAM used only first-argument indexing, too.

If the first argument in a predicate call is an unbound ref, there's no indexing possible --
it may match with any other first argument. In this case we need only walk through all clauses
in a predicate, in database order.

However, if the first argument is an atom or struct, even if non-ground, we can ignore a
host of clauses whose first parameter wouldn't match structurally.
We still need to match clauses whose first param is a variable, since that can still match with
anything.
As we need to try clauses in database order, the first indexing is splitting the clause list in
constant vs variable runs:

                      Only look at first argument
      ↓        ↓        ↓           ↓         ↓           ↓        ↓
    f(X, 0). f(a, 1). f(g(_), 2). f(a, 10). f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------
    variable            constants                variables        constant

For query `f(A, B)`, it's necessary to try all 7 clauses, in order:

    f(X, 0). f(a, 1). f(g(_), 2). f(a, 10). f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------

For query `f(a, B)`, it's necessary to try all that have a var as first param, but only those that 
have `a` as first constant param:

    f(X, 0). f(a, 1).             f(a, 10). f(Y, s(Y)). f(Z, a).             
    -------  -----------------------------  -------------------  ----------

For query `f(g(A), B)`, it's also necessary to try all that have a var as first param, but only those that 
have `g/1` as first constant functor:

    f(X, 0).          f(g(_), 2).           f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------

Finally, for the query `f(x, B)`, we need only walk over the ones that are only variables:

    f(X, 0).                                f(Y, s(Y)). f(Z, a).            
    -------  -----------------------------  -------------------  ----------

## Level 2: Constant structure

As said in the previous section, we need only consider clauses that may match structurally with a given term.
We can fast-track checks for atoms and struct functors with hash tables that map to a list of terms within a
run of constants, in database order.

                f(a, 1). f(g(_), 2). f(a, 10). f(b, 10).
                -------  ----------  --------  --------

Index all constants for each atom and functor:

    (atom) a:   f(a, 1).             f(a, 10).
           -    -------  ----------  --------  --------
    (atom) b:                                  f(b, 10).
           -    -------  ----------  --------  --------
    (func) g/1:          f(g(_), 2).
           ---  -------  ----------  --------  --------
  
If the first arg is an atom or functor, return all clauses in its corresponding list. If it is a var, return all.
