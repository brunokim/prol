# Prol: WAM demo

This is a simplified Warren Abstract Machine (WAM) implementation for Prolog, that showcases
the main instructions, compiling, register allocation and machine functions.

## Code organization

- model.py: Data objects representing terms, programs, and machine entities.
- compiler.py: Compiling of a list of rules into a list of instructions.
- interpreter.py: Interpreter that execute the instruction listing for a given query.

## Documentation

1. [About Prolog](docs/about-prolog.md): a hurried primer if you don't know what it is about.
1. [Resolution strategy](docs/resolution.md): how a query is actually solved in Prolog. 
1. [Warren Abstract Machine](docs/wam.md): details about the implementation attempted here.
1. [Stuff left out](docs/references.md): what this implementation has simplified from the WAM.
