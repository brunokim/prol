# Prol: WAM demo

This is a simplified Warren Abstract Machine (WAM) implementation for Prolog, that showcases
the main instructions, compiling, register allocation and machine functions.

## Code organization

- model.py: Data objects representing terms, programs, and machine entities.
- compiler.py: Compiling of a list of rules into a list of instructions.
- interpreter.py: Interpreter that execute the instruction listing for a given query.
- grammar.py: Sample application of interpreter, with a grammar that can parse itself.

## Documentation

1. [About Prolog](docs/about-prolog.md): a hurried primer if you don't know what it is about.
1. [Resolution strategy](docs/resolution.md): how a query is actually solved in Prolog. 
1. [Warren Abstract Machine](docs/wam.md): details about the implementation attempted here.
1. [Indexing](docs/indices.md): indexing implementation to fast-track some call patterns.
1. [Parsing](docs/parsing.md): explaining basic structures for parsing
1. [Grammar](docs/grammar.md): documentation for the sample application of grammar parsing.
1. [Stuff left out](docs/references.md): what this implementation has simplified from the WAM, and references.

