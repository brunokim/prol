# Stuff left out (or: further reading)

Not only a Python implementation glosses over memory handling, which is fundamental for a
low-level implementation, we've also removed some other instruction sets that can be
ignored or implemented in runtime.

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

## Epilog

I hope this repository is a nice study resource for all 4 of those interested in compilersand logic languages. Some known drawbacks:

- Register allocation doesn't know when a variable is no longer used; sometimes it's safe to overwrite it, but currently it first stashes the variable in a safe register;
- Struct compiling, for both "get" and "put" instructions, seems more complex than necessary;
- It shouldn't be too complex to compile clauses in an order that allows us to know how many registers each calling predicate may use. This may allow further savings on environment slot allocation. Topological sort to the rescue!

