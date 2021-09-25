## Grammar

1. [About Prolog](about-prolog.md)
1. [Resolution strategy](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexing](indices.md)
1. [Parsing](parsing.md)
1. [Grammar](grammar.md)
1. [Stuff left out](references.md)

## Syntax

Prol's grammar is straightforward in [BNF](https://en.wikipedia.org/wiki/Backus%E2%80%93Naur_form):

```ebnf
Clause ::= Struct "."
         | Struct ":-" Terms "."
         ;
  Term ::= Atom
         | Var
         | Struct
         ;
  Atom ::= lower ident*
         | digit+
         | symbol+
         | "'" (char - "'" | "'" "'") "'"
         ;
   Var ::= (upper | "_") ident* ;
Struct ::= Atom "(" Terms? ")" ;
 Terms ::= Term ("," Term)* ;

 lower ::= [a-z] ;
 upper ::= [A-Z] ;
 digit ::= [0-9] ;
symbol ::= [!@#$%&*=+{}[\]^~/\|<>.;-] ;
 ident ::= lower | upper | digit | "_" ;
``` 

(Whitespace handling omitted to improve readability)

Let's see some example elements:

- Var: `X`, `A1`, `Elem`, `_`, `_list_1`;
- Atom:
  - starting with lowercase: `a`, `b51`, `anAtom`, `a_10`;
  - only digits: `123`;
  - only symbols: `.`, `<->`, `[]`, `\==`;
  - quoted: `''`, `'a b'`, `'I won''t fail!'`;
- Struct: `f()`, `'f'()`, `.(Head, Tail)`, `f(g(a), h(t(b)))`
- Clause: `vowel(a).`, `consonant(X) :- letter(X), not(vowel(X)).`

Given a list of atoms representing text, we want to check that it matches
the grammar specification.
We need to compose rules into others, which can be done in a simple way using difference lists.
We can build a check that the L0-L4 difference list contains a clause by
composing it with checks for struct and terms:

```prolog
clause(L0, L4) :-
    struct(L0, L1),
    L1 = .(':', .('-', L2)),
    terms(L2, L3),
    L3 = .('.', L4).
```

We can also inline the definitions for `L1` and `L3`, getting the more
idiomatic option

```prolog
clause(L0, L4) :-
    struct(L0, .(':', .('-', L2))),
    terms(L2, .('.', L4)).
```

To check for vars, we check that the first char is an uppercase char,
and the remaining are all identifier chars with `idents/2`. 


```prolog
var(.(Ch, L0), L1) :-
    upper(Ch),
    idents(L1, L2).
idents(L, L).
idents(.(Ch, L0), L1) :-
    ident(Ch),
    idents(L0, L1).

ident(Ch) :- lower(Ch).
ident(Ch) :- upper(Ch).
ident(Ch) :- digit(Ch).
ident('_').
```

Finally, we need to list all facts about chars:

```prolog
% upper/1
upper('A').
upper('B').
..
upper('Z').

% lower/1
lower(a).
lower(b).
..
lower(z).

% digit/1
digit(0).
..
digit(9).

% symbol/1
symbol(!).
symbol(@).
..
symbol(-).
```

## Abstract syntax tree

The form we wrote for the grammar allows us only checking that a 
given list of atoms matches the grammar.
We can also build a tree of the parsed elements while parsing,
to represent the program structure -- what is called an abstract
syntax tree (AST).

First, an example of what we want. Given the text `f(x):-gh(a,X).` we
build a list of atoms with their chars.
The predicate `clause/3` receives a new argument `Tree` where the AST is built:

```prolog
?- Chars = .(f, .('(', .('X', .(')', .(':', .('-', .(g, .(h, .('(', .(a, .(',', .('X', .(')', .('.', [])))))))))))))),
   clause(Tree, Chars, []).
Tree = clause(
    struct(.(f, []),
           .(var(.('X', [])),
             [])),
    .(struct(.(g, .(h, [])),
             .(atom(.(a, [])),
               .(var(.('X', [])),
                 []))),
      [])).
```

The `clause` predicate becomes:

```prolog
clause(Tree, L0, L2) :-
    struct(Head, L0, .(':', .('-', L1))),
    terms(Body, L1, .('.', L2)),
    Tree = clause(Head, Body).
```

and `var` becomes:

```prolog
var(Tree, .(Ch, L0), L1) :-
    upper(Ch),
    idents(Idents, L1, L2),
    Tree = var(.(Ch, Idents)).
idents([], L, L).
idents(Idents, .(Ch, L0), L1) :-
    ident(Ch),
    idents(Chars, L0, L1),
    Idents = .(Ch, Chars).
```

With an AST for the code, we parse the text and build data structures from it at the `decode_*`
functions in [grammar.py](/grammar.py).
We are able to build the exact same structures as the grammar built to parse it! Cool, huh?

