# Estratégia de resolução e unificação

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Resolução em profundidade

A estratégia de resolução de consultas em Prolog não é executada em paralelo como
mostrado no exemplo da seção anterior, mas sim em profundidade.
Quando um predicado com múltiplas cláusulas bate com o termo atual, nós empilhamos
um _choice point_ ("ponto de escolha") em uma pilha.

Um _choice point_ é uma estrutura que armazena o estado atual da máquina, apontando
para a próxima cláusula a se tentar no predicado.
O fluxo de execução continua testando a primeira cláusula; se o fluxo falhar, isto é,
se ele chegar em um estado sem solução, o último _choice point_ é desempilhado e o
estado é restaurado, mas agora usando a cláusula subsequente.
Isto é chamado _backtracking_ ("recuar").
Múltiplos _choice points_ podem ser empilhados, representando ramos ainda inexplorados
na árvore de soluções.

No diagrama abaixo, temos o fluxo de resolução do exemplo da seção anterior. Cada
ramificação insere um _choice point_ na pilha.
Ao alcançar um estado sem solução (marcado com ✗), este _choice point_ é removido e
o estado restaurado, para explorar outra possibilidade.
Uma solução é encontrada no passo #10 com `X = república` (marcada com ✓).
Um _choice point_ ainda existe na pilha, marcado com `*`, inserido logo antes do
passo #3.
Seria possível restaurar este estado para buscar novas soluções.

```none
  (1)              1) andar2(são_bento, X).
   |               2) andar(são_bento, C),   andar(C, X),     são_bento \== X.
  (2)              *) conexão(C, são_bento), andar(C, X),     são_bento \== X.
   |               3) conexão(são_bento, C), andar(C, X),     são_bento \== X.
   +----[*]        4) C = luz,               andar(luz, X),   são_bento \== X.
   |               5)                        conexão(luz, X), são_bento \== X.
  (3)              6)                        conexão(X, luz), são_bento \== X.
   |               7)                        X = são_bento,   são_bento \== são_bento.
  (4)              8)                                         são_bento \== são_bento.
   |               9)                        X = república,   são_bento \== república.
   +----.         10)                                         são_bento \== república. 
   |    |          
  (5)  (6)
   |    |
   ✗    +----.
        |    |
       (7)  (9)
        |    |
       (8)  (10)
        |    |
        ✗    ✓ 
```

Ao prosseguir em uma hipótese, nós acumulamos um conjunto de ligações (_bindings_) de
variáveis, isso é, um conjunto de valores que correspondem a alguma das variáveis.
Uma variável que tenha um termo associado é dita _ligada_ (_bound_); um termo que
não tenha nenhuma variável livre é dito _fechado_ (_ground_).
É possível alcançar um estado insatisfeito, onde as ligações presentes levam a uma
falha lógica, tal que nenhum fato corresponda ao termo atual.
Neste caso, ao recuar, nós desfazemos todas as ligações que foram criadas desde o
_choice point_, realmente restaurando ao mesmo estado anterior.

## Unificação

Já dissemos que esperamos que termos "batam" ou "correspondam", mas não fomos
precisos aqui. Esta "correspondência" se chama _unificação_, e consiste em um
conjunto simples de regras que fazem com que dois termos tornem-se o mesmo:

1. Dois átomos unificam se eles forem idênticos;
2. Duas structs unificam se o seu functor _f/n_ é o mesmo, e todos seus
argumentos unificam, em ordem;
3. Uma variável livre unifica com qualquer termo, e se torna ligada a ele;
4. Uma variável ligada unifica com um termo se o termo e a ligação da variável unificam;
5. Caso contrário, a unificação falha.

Em Prolog a unificação é feita com o operador `=`.
A consulta a seguir seria unificada como segue:

```prolog
?- P1 = p(X, a, f(b)), P2 = p(f(Y), Y, X), P1 = P2.
```

* `P1 = p(X, a, f(b))` da regra 3 (ligação: `P1 = p(X, a, f(b))`)
* `P2 = p(f(Y), Y, X)` da regra 3 (ligação: `P2 = p(f(Y), Y, X)`)
* `P1 = P2`
* `p(X, a, f(b)) = P2` da regra 4 (aplicada a P1)
* `p(X, a, f(b)) = p(f(Y), Y, X)` da regra 4 (aplicada a P2)
* `X = f(Y), a = Y, f(b) = X` da regra 2 (functor: `p/3`)
* `a = Y, f(b) = X` da regra 3 (ligação: `X = f(Y)`)
* `f(b) = X` da regra 3 (ligação: `Y = a`)
* `f(b) = f(Y)` da regra 4 (aplicada a X)
* `b = Y` da regra 2 (functor: `f/1`)
* `b = a` da regra 4 (aplicada a Y)
* Falha, da regra 1

