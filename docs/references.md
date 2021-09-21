# Stuff left out (or: further reading)

1. [About Prolog](about-prolog.md)
1. [Resolution strategy](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexing](indices.md)
1. [Stuff left out](references.md)

## Memory layout

The Warren Abstract Machine is proposed as a suitable target for implementing a low-level
interpreter or compiler.
As such, it assumes a linear memory layout, where the runtime is responsible with managing
cell location and eventual cleanup.
It divides the memory in the following regions:

- *Registers*, which should ideally correspond to the actual machine's register bank.
- *Stack*, a volatile region that grows storing environments and choicepoints, and
shrinks on backtrack or on an environment deallocation.
- *Heap*, region where longer-lived cells are placed, which should always be referenced by
other cells in the register or stack.
- *Trail*, where bound references are kept to be unwound on backtrack.
- *Push-down list*, a small region to execute unification of terms.

Since the registers are a fundamentally limited resource, a low-level WAM must have some strategy
for *spilling* cells to the stack when a clause requires more registers than are available.

In this implementation, we rely on Python's GC to keep an object in memory while it is
referenced. This simplifies a number of features of the WAM:
- A deallocated environment can still be referenced by a buried choice point.
The WAM cleverly organizes them in the stack such that an environment is not *actually* deallocated
if there's still a choice point referencing it.
- Cells in the heap should never reference a cell in the registers or stack, which are fundamentally
volatile.
This situation is checked during runtime for potentially "unsafe" values, and if it happens
the cell in the volatile region is promoted to the heap.
- Although the original paper doesn't concerns itself with this, the heap may be polluted with
cells that are no longer referenced.
An effective implementation would consider cleaning and reusing the available space.

In our implementation, the trail is broken down and associated with each choicepoint.
In the WAM, the trail is a contiguous region, that grows when a conditional ref is bound, and shrinks
on backtrack.

## Removed WAM instructions

The WAM uses specialized instructions to push, update and pop choice points:
`try_me_else`/`retry_me_else`/`trust_me`, respectively.
These instructions are placed at the beginning of clauses in a multi-clause predicate,
forming a linked list that the machine walks on backtrack. Here, we rely instead on
checking if a predicate has multiple clauses during runtime.

This implementation performs indexing partly at runtime: the first argument of a
calling term is used to build a list of clauses whose head may unify with the term.
The WAM also performs indexing, but these lists are built cleverly at compile time!
Basically, the entry point for a predicate is not the first clause, but a special
header that directs the execution flow to the underlying clauses.
Instructions like `switch_on_term`/`switch_on_atom`/`switch_on_struct` choose a clause
based on the term type, while preserving the same resolution order.
When there are multiple clauses with the same type, it also walk only on
them using a linked list created with `try`/`retry`/`trust` instructions.

## Epilog

I hope this repository is a nice study resource for all 4 of you interested in learning
a logic language compiler. Some known drawbacks:

- Register allocation doesn't know when a variable is no longer used; sometimes it's safe to overwrite it,
but currently it first stashes the variable in a safe register;
- Struct compiling, for both "get" and "put" instructions, seems more complex than necessary;
- It shouldn't be too complex to compile clauses in an order that allows us to know how many registers
each calling predicate may use.
This may allow further savings on environment slot allocation. Topological sort to the rescue!
- We are not handling cases of singleton or nil vars. That is, in `f(_, _, a)` the first two variables will
be considered the same, and we'd be forced to write `f(_1, _2, a)` to have the same intended effect.
