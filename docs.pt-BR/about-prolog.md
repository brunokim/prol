# Sobre Prolog

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Introdução ao Prolog

Prolog é uma linguagem de programação lógica e declarativa, que é muito útil para resolver problemas
combinatórias e com restrições.
Programas em Prolog são estruturados como uma sequência de regras e fatos lógicos sobre termos.
Termos podem ser

- _átomos_, que são uma constante ou símbolos, como `1`, `a`, `x_123`. Nesta implementação, nós não temos inteiros.
- _variáveis_ ou _vars_, que representam um termo arbitrário e indefinido. Vars começam com uma letra maiúscula ou
_underline_, como `X`, `_123`, `Abs`.
- _estruturas_ ou _structs_, que representam uma sequência (nomeada) de termos. Por exemplo, um ponto pode ser
representado como `ponto(1, 2)`, e uma estrutura como `ret(vermelho, ponto(0, 1), ponto(4, 5))` pode representar
um retângulo vermelho com extremos em (0,1) e (4,5).

Um _fato_ é uma afirmação que é sempre verdadeira. Eles são representados como uma struct terminada com '.'
Fatos diferentes podem não ser verdadeiros ao mesmo tempo.
Por exemplo, podemos enumerar todos os átomos que representam bits com

```prolog
bit(0).
bit(1).
```

Podemos ler estes fatos como "bit(0) é verdade OU bit(1) é verdade".
Juntos, estes fatos formam um predicado com _functor_ `bit/1`, que significa "conjunto de regras para `bit` com 1 argumento".
Se fizermos uma _consulta_ como `bit(X)`, vamos obter como resposta todos os X's que satisfazem os fatos acima:

```prolog
?- bit(X).
  X = 0 ;
  X = 1 .
```

Podemos consultar múltiplos termos que queremos que sejam satisfeitos. Vamos adicionar mais alguns fatos sobre as
cores primárias:

```prolog
cor(vermelho).
cor(verde).
cor(azul).
```

Podemos consultar por todas as combinações de bits e cores ao buscar por ambos `bit(X)` E TAMBÉM `color(Y)`,
o que é feito com uma vírgula:

```prolog
?- bit(X), cor(Y).
  X = 0, Y = vermelho ;
  X = 0, Y = verde ;
  X = 0, Y = azul ;
  X = 1, Y = vermelho ;
  X = 1, Y = verde ;
  X = 1, Y = azul .
```

Note que `bit(X), cor(X)` não pode ser satisfeito, porque não existe nenhum `cor(0)` ou `bit(vermelho)` que
satisfaça os dois fatos simultaneamente

```prolog
?- bit(X), cor(X).
  false
```

Podemos expressar fatos sobre qualquer coisa, como conexões entre estações na rede de metrô de São Paulo:

```prolog
%                                   |
%                             .--- luz
%                       .-----'     |
%          .------------'       são_bento
%         /                         |
% --- república --- anhangabaú --- sé ---
%       /                           |

conexão(sé, são_bento).
conexão(são_bento, luz).
conexão(sé, anhangabaú).
conexão(anhangabaú, república).
conexão(república, luz).
```

No caso acima, gostaríamos que o termo `conexão` signifique, se há essa relação entre A e B, nós podemos andar
tanto de A pra B, quanto de B pra A.
Como nós somos preguiçosos, não queremos repetir todas essas conexões refletidas, então introduzimos a regra `andar`:

```prolog
andar(A, B) :- conexão(A, B).
andar(A, B) :- conexão(B, A).
```

Nós lemos esse predicado como "andar(A, B) é satisfeito se conexão(A, B) é satisfeito OU ENTÃo se conexão(B, A) é satisfeita".
Ele é composto de duas cláusulas, que ao contrário dos fatos, são verdadeiros condicionalmente.
O lado direito da cláusula é dito o _corpo_ da cláusula, e o esquerdo é a _cabeça_.

Podemos também usar conjunções (ANDs) no corpo das cláusulas, como fizemos com as consultas:

```prolog
% Retorna estações distantes 2 paradas.
andar2(A, B) :-   % A está a 2 paradas de B se...
    andar(A, C),  % ...dá pra andar entre A e C...
    andar(C, B),  % ...E TAMBÉM se dá pra andar entre C e B...
    A \== B.      % ...E TAMBÉM se A é diferente de B.
```

Isto se torna mais valioso quando usamos múltiplas cláusulas para implementar um predicado recursivo:

```prolog
andarN(A, B, N) :-    % A está a N paradas de B se...
    N > 1,            % ...N é maior que 1...
    andar(A, C),      % ...e dá pra andar entre A e C...
    N1 #= N - 1,      % ...e N1 = N-1, em um sentido aritmético...
    andarN(A, B, N1). % ...e C está a N1 paradas de B.

andarN(A, B, 1) :-    % A está a 1 parada de B se...
    andar(A, B).      % ...dá pra andar entre A e B.
```

Ao fazer uma consulta como `andarN(são_bento, X, 5)`, o _solver_ do Prolog vai recursivamente
explorar todos os vizinhos de `são_bento` com N=4, e todos os vizinhos _deles_ com N=3, e
então com N=2, então N=1.
Este é o caso base da recursão, que é tratado pela segunda cláusula, onde delegamos para
o predicato `andar(A, B)` existente.

### Execução abstrata

Para martelar como um programa Prolog encontra soluções a partir de um conjunto de regras,
vamos considerar o predicado `andar2` de novo:

```prolog
andar2(A, B) :- andar(A, C), andar(C, B), A \== B.
```

Para que `andar2(., .)` seja bem-sucedido, é necessário que todos os outros três outros
predicados no seu corpo sejam bem-sucedidos, sob as mesmas restrições.
Então, por exemplo, para a consulta

```prolog
?- andar2(são_bento, X).
```

as variáveis `A` e `B` no corpo da cláusula são substituídas por `são_bento` e `X`, respectivamente.
Ela é então equivalente à seguinte consulta:

```prolog
?- andar(são_bento, C), andar(C, X), são_bento \== X.
```

Agora, `andar(.,.)` possui duas cláusulas que batem com o primeiro termo da consulta.
Vamos imaginar que seria possível considerar ambas em paralelo, então nós podemos
substituir a primeira ocorrência de `andar(...)` na consulta acima com o corpo de cada
uma

```prolog
?- conexão(são_bento, C), andar(C, X), são_bento \== X.
?- conexão(C, são_bento), andar(C, X), são_bento \== X.
```

Nós então buscamos por fatos com `conexão(.,.)` no nosso banco de dados que satisfazem as restrições acima.
Para o primeiro nós encontramos que `C = luz` e para o segundo, encontramos `C = sé`.

```prolog
?- conexão(são_bento, luz), andar(luz, X), são_bento \== X.
?- conexão(sé, são_bento), andar(sé, X), são_bento \== X.
```

Não há nada mais pra se fazer com estes fatos, dado que eles são verdadeiros, então avançamos para o
próximo termo da consulta:

```prolog
?- andar(luz, X), são_bento \== X.
?- andar(sé, X), são_bento \== X.
```

Agora, cada uma das consultas precisa ser dividia em duas mais em paralelo, para as duas cláusulas de
`andar`:

```prolog
?- conexão(luz, X), são_bento \== X.
?- conexão(X, luz), são_bento \== X.
?- conexão(sé, X), são_bento \== X.
?- conexão(X, sé), são_bento \== X.
```

Agora, alguns desses fatos aceitam múltiplos valores para X, e nós também os consideramos em paralelo.
Também, alguns dos fatos não batem com nenhum outro no banco de dados:

```prolog
?- conexão(luz, X), são_bento \== X.                  % Nenhum X satisfaz isso
?- conexão(são_bento, luz), são_bento \== são_bento.  % X = são_bento
?- conexão(república, luz), são_bento \== república.  % X = república
?- conexão(sé, são_bento), são_bento \== são_bento.   % X = são_bento
?- conexão(sé, anhangabaú), são_bento \== anhangabaú. % X = anhangabaú
?- conexão(X, sé), são_bento \== X.                   % Nenhum X satisfaz isso
```

Removendo as consultas não satisfeitas, e os termos `conexão` verdadeiros, nós temos
um último termo a considerar, que usa o operador não-é-equivalente `\==`

```prolog
?- são_bento \== são_bento.  % X = são_bento
?- são_bento \== república.  % X = república
?- são_bento \== são_bento.  % X = são_bento
?- são_bento \== anhangabaú. % X = anhangabaú
```

A 1a. e a 3a. consultas não são satisfeitas (`são_bento` é equivalente a `são_bento`!).
Finalmente, as substituições (_bindings_) que satisfazem a consulta são retornadas:

```prolog
?- andar2(são_bento, X).
  X = república ;
  X = anhangabaú .
```

