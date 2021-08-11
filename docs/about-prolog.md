# About Prolog

1. [About Prolog](docs/about-prolog.md)
1. [Resolution strategy](docs/resolution.md)
1. [Warren Abstract Machine](docs/wam.md)
1. [Stuff left out](docs/references.md)

## Prolog primer

Prolog is a declarative, logic programming language that is very useful for solving constraint and combinatorial problems. Prolog programs are structured as a sequence of logic rules and facts over terms. Terms may be either

- an _atom_, which is a constant or symbol, like `1`, `a`, `x_123`. In this implementation, we don't have ints.
- a _var_, which represents an arbitrary term. Vars start with an uppercase letter or underscore, like `X`, `_123`, `Abs`.
- a _struct_, which represents a (named) sequence of terms. For example, a point may be represented like `point(1, 2)`, and a struct like `rect(red, point(0, 1), point(4, 5))` may represent a red rectangle with extremes in (0,1) and (4,5).

A _fact_ is a statement that is always true. It is represented as a struct ended with '.'. Different facts may not be true at the same time. For example, we can enumerate all atoms that represent bits like:

```prolog
bit(0).
bit(1).
```

We can read these facts as "bit(0) is true OR bit(1) is true". Together, these facts form a predicate with _functor_ `bit/1`, which means "set of rules for `bit` with 1 argument". If we pose a _query_ like `bit(X)`, we will obtain as answer all X's that satisfy the above facts:

```prolog
?- bit(X).
  X = 0 ;
  X = 1 .
```

We may pose multiple terms that we desire to be satisfied. By adding the following facts about primary colors:

```prolog
color(red).
color(green).
color(blue).
```

We may query for all combinations of bits and colors by querying for both `bit(X)` AND `color(Y)`, which is done with a comma:

```prolog
?- bit(X), color(Y).
  X = 0, Y = red ;
  X = 0, Y = green ;
  X = 0, Y = blue ;
  X = 1, Y = red ;
  X = 1, Y = green .
```

Note that `bit(X), color(X)` can't be satisfied, because there's no `color(0)` or `bit(red)` that would satisfy both facts simultaneously:

```prolog
?- bit(X), color(X).
  false
```

We can express facts about anything, like connections between stations in São Paulo's subway network:

```prolog
%                                   |
%                             .--- luz
%                       .-----'     |
%          .------------'       são_bento
%         /                         |
% --- república --- anhangabaú --- sé ---
%       /                           |

connection(sé, são_bento).
connection(são_bento, luz).
connection(sé, anhangabaú).
connection(anhangabaú, república).
connection(república, luz).
```

In the case above, we want our database to mean that if there's a connection between A and B, we can walk both from A to B, and from B to A. As we are lazy, we don't want to repeat all reflected connections, so we introduce a rule `walk`:

```prolog
walk(A, B) :- connection(A, B).
walk(A, B) :- connection(B, A).
```

We read this predicate as "walk(A, B) is satisfied if connection(A, B) is satisfied OR connection(B, A) is satisfied". The right side of the clause is the _body_ of the clause, and the left is the _head_.

We can also use conjunctions (ANDs) as we did with queries in clause bodies:

```prolog
% Return stations 2-steps removed.
walk2(A, B) :-   % A is 2 steps from B if...
    walk(A, C),  % ...there's a walk between A and C...
    walk(C, B),  % ...AND there's a walk between C and B...
    A \== B.     % ...AND A is different from B.
```

This becomes more valuable when we use multiple clauses to implement a recursive predicate:

```prolog
walkN(A, B, N) :-    % A is N steps from B if...
    N > 1,           % ...N is larger than 1...
    walk(A, C),      % ...and there's a walk between A and some C...
    N1 #= N - 1,     % ...and with N1 = N - 1, in an arithmetic sense,...
    walkN(C, B, N1). % ...and C is N1 steps from B.

walkN(A, B, 1) :-    % A is 1 step from B if...
    walk(A, B).      % ...there's a walk between A and B.
```

If we issue a query like `walkN(são_bento, X, 5)`, it will recursively explore all
`são_bento`'s neighbors with N=4, then all _their_ neighbors with N=3, then N=2, then N=1.
This is the base case of the recursion, handled by the second clause, where we delegate
to the existing `walk(A, B)` predicate.

### Abstract execution

To hammer down how a Prolog program finds solutions from a set of rules, let's
consider the `walk2` predicate again:

```prolog
walk2(A, B) :- walk(A, C), walk(C, B), A \== B.
```

For `walk2(., .)` to succeed, it's necessary that all three other predicates in its body also succeed, under the same restrictions. So, for example, the query

```prolog
?- walk2(são_bento, X).
```

has the variables `A` and `B` in the body of the clause replaced with `são_bento` and `X`, respectively. It is then equivalent to this query:

```prolog
?- walk(são_bento, C), walk(C, X), são_bento \== X.
```

Now, `walk(.,.)` has two clauses that match with the first term of the query.
Let's imagine that it is possible to consider both of them in parallel, so we then
replace the first occurrence of `walk` in the query above with their body:

```prolog
?- connection(são_bento, C), walk(C, X), são_bento \== X.
?- connection(C, são_bento), walk(C, X), são_bento \== X.
```

We then look for `connection(.,.)` facts in our database that satisfy the above restrictions. For the first we find that `C = luz` and for the second `C = sé`.

```prolog
?- connection(são_bento, luz), walk(luz, X), são_bento \== X.
?- connection(sé, são_bento), walk(sé, X), são_bento \== X.
```

There's nothing else to be done with these facts, since they are true, and so we may advance to the next term in the query:

```prolog
?- walk(luz, X), são_bento \== X.
?- walk(sé, X), são_bento \== X.
```

Now, each of the queries need to be split in two more in parallel, for the two clauses in `walk`:

```prolog
?- connection(luz, X), são_bento \== X.
?- connection(X, luz), são_bento \== X.
?- connection(sé, X), são_bento \== X.
?- connection(X, sé), são_bento \== X.
```

Now, some of these facts accept multiple values for `X`, and we consider those in
parallel, too. Also, some facts do not "match" with any other in the database:

```prolog
?- connection(luz, X), são_bento \== X.                  % No X satisfies this
?- connection(são_bento, luz), são_bento \== são_bento.  % X = são_bento
?- connection(república, luz), são_bento \== república.  % X = república
?- connection(sé, são_bento), são_bento \== são_bento.   % X = são_bento
?- connection(sé, anhangabaú), são_bento \== anhangabaú. % X = anhangabaú
?- connection(X, sé), são_bento \== X.                   % No X satisfies this
```

Cleaning up the unsatisfiable queries, and the true `connection` terms, we have the
last term to consider, that uses the not-equivalent-to operator:

```prolog
?- são_bento \== são_bento.  % X = são_bento
?- são_bento \== república.  % X = república
?- são_bento \== são_bento.  % X = são_bento
?- são_bento \== anhangabaú. % X = anhangabaú
```

The 1st and 3rd queries are not satisfiable (`são_bento` is equivalent to `são_bento`!).
Finally, the bindings that satisfy the query are output:

```prolog
?- walk2(são_bento, X).
  X = república ;
  X = anhangabaú .
```

