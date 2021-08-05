# Prol: WAM demo

This is a simplified Warren Abstract Machine (WAM) implementation for Prolog, that showcases
the main instructions, compiling, register allocation and machine functions.

## Prolog

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

## Resolution strategy and unification

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

## Warren Abstract Machine

For efficient execution of Prolog programs, it's necessary to compile it into a lower
level architecture.
David S. Warren proposed in 1983 a set of abstract instructions to be executed by an
abstract machine, which was more amenable to implementation in machine code.
The proposed abstract machine was named after him, and to understand it in full,
Hassan Aït-Kaci tutorial is the best introduction -- or keep reading!

This implementation is not concerned with all lower level details, specially not memory
management.
This simplifies many assumptions and instructions, that need to take care of moving and
pointing data from volatile to permanent memory.
Here, all data is stored as regular Python objects, so they are kept accessible as long
as there is a pointer to them.

The WAM is a register machine, and predicates are seen as functions.
Referencing a predicate within the body of another is akin to a function call.
The calling convention is passing the arguments via the registers X0-Xn to the function
being invoked.
Since predicate execution regularly moves registers around, any variable that needs to
be preserved between calls is stored in an environment (stack frame).
Some care is taken to minimize the number of register moves and environment allocations.

In a nutshell, a clause of the form

```prolog
pred(X, Y, Z) :-
  f(Y, X, a),
  Z \== q(X),
  g(Z, r(s(1, 2), s(3, 4))).
```

is translated to the following instructions:

```text
% Get arguments passed in registers X0-X2
get X0, @X
get X1, @Y
get X2, @Z

% Put arguments to call f(Y, X, a)
put X0, @Y
put X1, @X
put X2, @a
call f/3

% Build the struct q(X) in register X0
put X0, q/1
set_arg @X

% \== is a builtin function
builtin \==, @Z, X0

% Put first argument for calling g/2 in X0
put X0, @Z

% Build s(1, 2) in register X2
put X2, s/2
set_arg 1
set_arg 2

% Build s(3, 4) in register X3
put X3, s/2
set_arg 3
set_arg 4

% Build r(s(...), s(...)) in register X1
put X1, r/2
set_arg X2
set_arg X3

% Call g/2 with registers X0, X1 populated.
call g/2
```

There's more nuance here because there are variants of each of these instructions,
that we shall present better below. First, we need to present the memory cell types:

### Memory cell types

There are three cell types, corresponding to each term type:

- AtomCell: holds an atom
- StructCell: holds a struct with fixed name and arity. May not have all args set.
- Ref: pointer to another cell. May be unbound (value = None) or bound (value is set).

Cells can be stored in registers or in environment slots. When referencing register we
write `Xi`, and for env slots we use `Yi`. When any can be used, we use `Addr`.

### Get and unify instructions

There are four "get" instructions for reading arguments passed into the predicate:

- `get_var <Xi>, <Addr>`: used for variables not yet referenced within the clause. Moves
the cell in Xi to Addr.
- `get_val <Xi>, <Addr>`: used for variables already referenced and stored in Addr. Unify
contents of Xi with Addr.
- `get_atom <Xi>, <Atom>`: used for constants in arguments. Unify contents of Xi with atom.
- `get_struct <Xi>, <f/n>`: used for structs in arguments. The following "unify"
instructions handle each arg.
If an unbound Ref was passed in Xi, starts to build a struct bound to it;
if a StructCell was passed, starts to read its arguments.

If structs are expected in the clause head, then during execution we may either bind this
struct to a var, or unify it arg by arg. Say, the following fact:

```prolog
pred(X, 1, f(X, g(a)), X).
```

may be called with any of the following queries:

```prolog
?- pred(b, 1, F, b).
?- pred(b, 1, f(b, G), b).
```

In the first case, we want to bind `F = f(X, g(a))`.
In the second, we just need to walk the existing struct and unify their corresponding 
args `X=b, g(a)=G`.
This is accomplished by setting a read/write mode when getting a struct:
read if the cell is a StructCell, write if it is a Ref.
The per-arg instructions are called "unify", accomodating both modes, and also have
variants:

- `unify_var <Addr>`: used for variables nested in structs not yet referenced in the
clause head. In read mode, move arg to Addr; in write mode, create an unbound Ref in Addr.
- `unify_val <Addr>`: used for variables nested in structs and already referenced in the
clause head. In read mode, unify arg and Addr; in write mode, set the arg to the contents of Addr.
- `unify_atom <Atom>`: used for atoms nested in structs. In read mode, unify arg and atom;
in write mode, copy atom to arg.

Note that there's no `unify_struct`. Structs nested within structs in arguments are
handled like they are new variables bound to these structs, recursively.

The example above would be compiled to:

```text
% pred/4
get_var    X0, X5   % X is stored in X5
get_atom   X1, 1
get_struct X2, f/2  % Start to handle f(.,.)
unify_val  X5       %   Arg #1: X was already referenced and stored in X5
unify_var  X6       %   Arg #2: nested struct g(a) will be read/written in X6
get_val    X5       % X was already referenced and stored in X5

get_struct X6, g/1  % Nested struct is unified in X6
unify_atom a        %   Arg #1: unify atom with arg
```

### Put instructions

There are four "put" instructions for putting arguments in place for calling:

- `put_var <Xi>, <Addr>`: used for variables not referenced within the clause body.
Creates an unbound ref and places it both in Xi and Addr.
- `put_val <Xi>, <Addr>`: used for variables already referenced and stored in Addr.
Simply set the register Xi with the cell stored in Addr.
- `put_atom <Xi>, <Atom>`: used for constant parameters, setting Xi to the AtomCell.
- `put_struct <Xi>, <f/n>`: used to build structs as argument. Sets the mode to write
and use the same "unify" instructions for arguments.

For example the clause below:

```prolog
p(X) :-
    q(X, 1, f(a, g(Y)), Y).
```

Becomes

```none
% p/1
% Clause head
get_var X0, X4  % X is stored in X4.

% Body
% Build nested struct g(Y)
put_struct X5, g/1  % Build struct in X5
unify_var  X6       %   Arg #1: Y is stored in X6

put_val    X0, X4  % Put X from X4 in X0
put_atom   X1, 1   %
put_struct X2, f/2 % Write args of f(.,.)
unify_atom a       %   Arg #1: write atom 'a'
unify_val  X5      %   Arg #2: write struct built in X5
put_val    X3, X6  % Y was already referenced, stored in X6

call q/4
```

Aït-Kaci argues that it's better to have separate "set" instructions instead of reusing
the "unify" instructions for this case, because then we avoid checking the mode at every
step (since it should always be on write). I concur, but for this project I'm minimizing
the instructions set instead.

### Control instructions

The `call <f/n>` instruction changes the machine instruction pointer to the first clause
of the predicate indicated by _f/n_. If there are more clauses in the predicate, it
pushes a choice point onto a choice stack, storing the current machine state.

Once a clause completes execution, it's necessary to return control to just after the
original `call` instruction (called _continuation_).
The sequence of calls may run arbitrarily deep, so the machine also keeps a stack of
_environments_, or stack frames, where each one stores the continuation at that position.

An environment is created and pushed with an `allocate` instruction, and popped with
`deallocate`. At first sight, every clause should start with `allocate` and end with
`deallocate`, but we can actually avoid creating them on several cases:

1. if the clause doesn't perform `call`s at all, as happens with facts;
2. if the `call` is the last instruction of the clause, we simply trampoline
into the next function, keeping the same continuation as before;

The second case is a more generic optimization than tail-call optimization: any call
in the last position is invoked keeping the same environment, so there's no
memory impact in arbitrarily deep recursive function calls.

To mark the end of a clause that doesn't use `allocate`/`deallocate`, we have the
`proceed` instruction, which just returns the execution to the current continuation.

### Temporary and permanent variables

As already hinted, we can store cells in registers or environment slots. Permanent
variables are stable and survive across multiple calls, but require more memory and data
moving. For this reason, we seek to use registers as efficiently as possible, since all
values need to be present there per the calling convention, anyway.

During compilation, we annotate which variables can be left in registers (temporary)
and which will need to be made permanent and moved to a slot.
The `allocate <n>` instruction actually receives the number of slots necessary for this
environment.

For example, in the clause

```prolog
walk2(A, B) :-
    walk(A, C),
    walk(C, B).
```

Initially, A will be in register X0, and B in X1.
Our naive compiler doesn't check if the `walk` call will use 0, 1 or 1000 registers;
it just assumes that keeping any variable in registers is unsafe if we need to use it
after the call.
That's not the case for A, since it won't be used again, but it is for B and C --
so A is temporary while B, C are permanent.
The clause is compiled to:

```none
% walk2/2

allocate 2      % Slots for B, C
                % A is kept in register X0
get_var X1, Y0  % Move B to Y0 env slot
put_var X1, Y1  % Create C in Y1 env slot and put it into X1
call walk/2     % Call walk(A, C)

put_val X0, Y1  % Put C in X0
put_val X1, Y0  % Put B in X1
deallocate      % Pop environment, which is no longer needed
call walk/2     % Call (trampoline) to walk(C, B)
```

Notice that above we could keep A in the same register, because it'd be the argument
in the same position for the next call. This is not always the case, for example,

```prolog
p(A, B, C) :- q(B, C, A).
```

requires us to use an additional register X4 to rotate all others:

```none
% p/3
get_var X0, X4  % Stash A in X4 from X0
get_var X1, X0  % Move B from X1 to X0
get_var X2, X1  % Move C from X2 to X1
put_var X2, X4  % Put A from X4 in X2
call q/3
```

Choosing registers where each variable is stored until it's placed in the proper position
for a function call is a difficult problem, known as _register allocation_. We use the
algorithm from Saumya K. Debray, which is good enough to minimize data moves and
trim down on instructions.

### Stuff left out (or: further reading)

Not only a Python implementation glosses over memory handling, which is fundamental for a
low-level implementation, we've also removed some other instruction sets that can be
ignored or implemented in runtime:

The WAM uses specialized instructions to push, update and pop choice points: `try_me_else`/`retry_me_else`/`trust_me`, respectively.
These instructions are placed at the beginning of clauses in a multi-clause predicate,
forming a linked list that the machine walks on backtrack. Here, we rely instead on
checking if a predicate has multiple clauses during runtime.

The WAM also presents several instructions related to _indexing_ clauses.
When given the parameters for a predicate invocation, it's possible to immediately rule
out many clauses that can't possibly be unified.
For example, if the first argument is an atom we can rule out clauses that expect a
struct.
The WAM provides instructions like `switch_on_term`/`switch_on_atom`/`switch_on_struct`
that choose a clause based on the term type, while preserving the same resolution order.
In addition, when there are multiple clauses with the same type, it may also walk only on
them using a linked list created with `try`/`retry`/`trust` instructions.

### Epilog

I hope this repository is a nice study resource for all 4 of those interested in compilersand logic languages. Some known drawbacks:

- Register allocation doesn't know when a variable is no longer used; sometimes it's safe to overwrite it, but currently it first stashes the variable in a safe register;
- Struct compiling, for both "get" and "put" instructions, seems more complex than necessary;
- It shouldn't be too complex to compile clauses in an order that allows us to know how many registers each calling predicate may use. This may allow further savings on environment slot allocation. Topological sort to the rescue!
