# Parsing

Parsing is one area where logic languages shine, thanks to its ability to
assume a structure for a char or word stream, and backtrack arbitrarily
if it turns out not to be valid according to a grammar.
As such, I've decided to use a parser for the language itself as a sample
of its capabilities.

## Lists, incomplete lists

Prol doesn't spouse lists as a builtin object, but they can be easily
represented using _cons cells_, or a linked list. A cons cell is simply
a struct with `./2` functor, that can be used to define a list recursively:

- `[]` is the empty list
- `.(X, Y)` is a list containing the element `X` (head) followed by the
list `Y` (tail).

A list is then built by a chain of cons cells, such as the following
representation for the list `[a, b, c, d]`:

```prolog
.(a, .(b, .(c, .(d, []))))
```

Cons cells are so called for *construct*. They are the simplest and perhaps
most versatile data structure, being used to define the whole of the Lisp language
back in the 1950s.

The tail of a list not necessarily needs to be the empty list. If it is an
unbound variable, we call it an *incomplete list*, like

```prolog
.(a, .(b, .(c, .(d, X))))
```

This represents the list `[a, b, c, d|X]`, which can be read as
"the sequence of atoms `a`, `b`, `c`, `d`, followed by an unknown list
`X`".

A cons cell can have a value in its tail that is not a list, like `.(a, b)`.
In this case it's called an *improper list*.

Using incomplete lists can be useful to define a language recursively. For example,
the language `(ab|c)+` accepts the strings `ab`, `c`, `abab`, `abc`, `cab`, `cc`,
and so on. We can write a predicate that evaluates if a list of atoms is accepted
by this language:

```prolog
% Base case: [a, b] or [c]
lang_abc(.(a, .(b, []))).
lang_abc(.(c, [])).

% Recursive case
lang_abc(.(a, .(b, X))) :-
  lang_abc(X).
lang_abc(.(c, X)) :-
  lang_abc(X).
```

What is the result for the query `lang_abc(.(c, .(c, .(a, .(b, .(a, [])))))).`?
Can you trace the execution?

## Example: implementing `append/3`

A basic operation with lists is concatenating two of them to generate a third.
That is, the concatenation of `L0 = .(a, .(b, []))` and `L1 = .(c, .(d, .(e, [])))` must be
`L2 = .(a, .(b, .(c, .(d, .(e, [])))))`.
This is implemented in an `append(L0, L1, L2)` predicate below:

```prolog
% Base case: concatenation of [] and B is B
append([], B, B).

% Recursive case: L2 (= [Y|C]) is the concatenation of L0 (= [X|A]) and L1 (= B) if
% Y = X, and C is the concatenation of A and B.
append(.(X, A), B, .(X, C)) :-
    append(A, B, C).
```

This is the historical name of this operation, so keep in mind that, even though it evokes
some action, it still only describes a relation between three lists.
We can use it to solve logic problems where any of the arguments are unknown,
not only for direct concatenations where `L0` and `L1` are bound:

```prolog
% What is the concatenation of [a] and [b]?
?- A = .(a, []), B = .(b, []), append(A, B, X).
X = .(a, .(b, [])).

% What X, when concatenated onto [a, b], produces [a, b, z]?
?- A = .(a, .(b, [])), C = .(a, .(b, .(z, []))), append(A, X, C).
X = .(z, []).

% What X, when concatenated with [z], produces [z]?
?- B = .(z, []), C = .(z, []), append(X, B, C).
X = [].

% What concatenations of X and Y produce [a, b]?
?- append(X, Y, .(a, .(b, []))).
X = [], Y = .(a, .(b, [])) ;
X = .(a, []), Y = .(b, []) ;
X = .(a, .(b, [])), Y = [].
```

## Difference lists

A difference list is conceptually the pair of an incomplete list with its tail. That is,
the pair `[a, b, c|T] - T` defines the list `[a, b, c]` as the "difference" between
`[a, b, c|T]` and `T`.
This is an useful abstraction to write predicates dealing with a small section of a list,
unaware of what may be in the remainder of a larger list `T`.

For example, the language of balanced angle brackets like "<>", "<<>>", "<><<>>" can be
defined with the following definition:

- `L = "<>"`; or
- `L = L0 L1`, if L0 and L1 are part of the language; or
- `L = "<" L0 ">"`, if L0 is part of the language.

We can simplify the grammar a bit if we also accept the empty string; in this case, the
grammar becomes 

```ebnf
L ::= "" ;
L ::= "<" L ">" L ;
```

We can write a predicate without using difference lists, but it requires using `append/3`
and has poor performance:

```prolog
brackets([]).
brackets(.(<, L)) :-
    append(L0, L1, L),        % #1
    brackets(L1),
    append(L2, .(>, []), L0), % #2
    brackets(L2).
```

In note #1, we call `append(L0, L1, L)` to break the list `L` into two components.
This implementation attempts all possible splits in sequence, backtracking if
it finds later on that it has produced an invalid subsequence.

In note #2, `append/3` will traverse the entire list `L0` just to ensure that it ends
with a `>`, storing everything before in `L2`. That is, to consume a single char it needs
to walk through N others, which leads to a quadratic time complexity.

Now, compare with an alternative implementation using difference lists, where each clause
receives two arguments, corresponding to the parts of the difference:

```prolog
brackets(T, T).
brackets(.(<, L), T) :-
    brackets(L, .(>, T0)), % #1
    brackets(T0, T).
```

This is not only simpler, but also much more efficient. It may require some time to
understand, but let's dig in:

The first clause represents the difference list `T-T`, that is, the empty list.
The second clause conceptually "splits" the `L-T` difference list into `L-T0` and `T0-T`.
In a sense, `(L - T0) + (T0 - T) = L - T`.

In note #1, the difference list `L-[>|T0]` ensures that `L` ends with `>`.
To see that, consider that `A-B = (A-Z)-(Z+B)`, with `Z = [>]`, `A-Z = L` and `Z+B = [>|T0]`.

This approach is more efficient because it handles one char at a time, and not the whole list.
The constraint that an open bracket must be matched with a closing one is built gradually as an
incomplete list in the second argument.
When this list matches with a subsequence of the list, the closing brackets are consumed
and the resolution continues in the remainder of the list.
The time complexity is linear.

Can you trace the execution of `brackets(.(<, .(<, .(>, .(>, .(<, .(>, [])))))), [])`?
Can you do it using the non-difference-list version?

