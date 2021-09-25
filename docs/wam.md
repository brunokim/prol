# Warren Abstract Machine

1. [About Prolog](about-prolog.md)
1. [Resolution strategy](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexing](indices.md)
1. [Parsing](parsing.md)
1. [Grammar](grammar.md)
1. [Stuff left out](references.md)

## Rationale

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

is translated to the following instructions (`@X` means "address of X", which needs to be
spelled out in the actual instructions):

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

## Memory cell types

There are three cell types, corresponding to each term type:

- AtomCell: holds an atom
- StructCell: holds a struct with fixed name and arity. May not have all args set.
- Ref: pointer to another cell. May be unbound (value = None) or bound (value is set).

Cells can be stored in registers or in environment slots. When referencing register we
write `Xi`, and for env slots we use `Yi`. When any can be used, we use `Addr`.

## Get and unify instructions

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

## Put instructions

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

## Control instructions

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

## Temporary and permanent variables

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

