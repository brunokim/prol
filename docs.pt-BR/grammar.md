# Gramática

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Sintaxe

A gramática desta implementação de Prolog é bem direta em [BNF](https://en.wikipedia.org/wiki/Backus%E2%80%93Naur_form):

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

(Regras sobre espaço em branco foram omitidas para melhorar a legibilidade)

Vamos ver alguns elementos de exemplo:

- _Var_: `X`, `A1`, `Elem`, `_`, `_list_1`;
- _Atom_:
  - começando com minúsculas: `a`, `b51`, `anAtom`, `a_10`;
  - apenas dígitos: `123`;
  - apenas símbolos: `.`, `<->`, `[]`, `\==`;
  - entre aspas: `''`, `'a b'`, `'Caixa d''agua'`;
- _Struct_: `f()`, `'f'()`, `.(Head, Tail)`, `f(g(a), h(t(b)))`
- _Clause_: `vogal(a).`, `consoante(X) :- letter(X), not(vogal(X)).`

Dada uma lista de átomos representando um texto, queremos checar se ele corresponde
à especificação da gramática.
Precisamos então compor regras em outras, o que pode ser feito de uma maneira simples
utilizando diferença de listas.
Podemos construir uma checagem da diferença de listas L0-L4 contendo uma
cláusula ao compor as checagems de structs e termos:

```prolog
clause(L0, L4) :-
    struct(L0, L1),
    L1 = .(':', .('-', L2)),
    terms(L2, L3),
    L3 = .('.', L4).
```

Podemos também inserir as definições para `L1` e `L3`, obtendo a versão mais idiomática:

```prolog
clause(L0, L4) :-
    struct(L0, .(':', .('-', L2))),
    terms(L2, .('.', L4)).
```

Para checar vars, podemos checar se o primeiro caractere é maiúsculo (_upper_), e se os
restantes são caracteres de identificadores com `idents/2`.


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

Finalmente, precisamos listar todos os fatos sobre caracteres:

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

## Árvore de sintaxe abstrate (AST)

A maneira em que escrevemos o verificador da gramática nos permite apenas
checar se uma lista de átomos corresponde à gramática.
Com algumas mudanças, nós também conseguimos construir a estrutura em
árvore dos elementos parseados, para representar a estrutura do programa --
o que é chamado de _árvore de sintaxe abstrata_ (AST, de "abstract syntax tree").

Inicialmente, vejamos um exemplo do que queremos.
Dado o texto `f(x):-gh(a,X).` nós construímos uma lista de átomos com seus caracteres.
O predicado `clause/3` recebe um novo argumento `Tree` onde a AST é construída:

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

Mais visualmente:

```none
   Tree = clause(.,.)
                 | '-----------------[ struct(.,.)
              struct(.,.)                     | '--[ atom(.)
                     | '--[ var(.) ]         "gh"         |
                    "f"         |                        "a"
                               "X"                 , var(.)
                                                         |
                                                        "X"
                                                   ]
                                     ]
```

Isto é, uma `clause` contém dois elementos: a cabeça e o corpo (uma lista de termos).
Uma `struct` contém também dois termos: seu nome e os argumentos (uma lista de termos).
`atom` e `var` contém apenas seus nomes.
Os nomes acima são representados entre aspas duplas, mas na AST vê-se que são listas
de átomos.

Para obter a AST, então, o predicado `clause` se torna:

```prolog
clause(Tree, L0, L2) :-
    struct(Head, L0, .(':', .('-', L1))),
    terms(Body, L1, .('.', L2)),
    Tree = clause(Head, Body).
```

e `var` se torna:

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

Com uma AST para o código, podemos parsear o texto e construir estruturas de dados a partir
dele com as funções `decode_*` em [grammar.py](/grammar.py).
Conseguimos construir exatamente as mesmas estruturas que a gramática usada para parsear o
texto!
Da hora, né?

