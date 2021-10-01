# Índices

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Indexando

A semântica de Prolog requer que as cláusulas sejam visitadas na mesma ordem em que
foram posicionadas no código-fonte. Por exemplo, o predicado `vogal/1` a seguir

```prolog
vogal(a).
vogal(e).
vogal(i).
vogal(o).
vogal(u).
```

sempre retorna as vogais na mesma ordem para a consulta

```prolog
?- vogal(X).
  X = a ;
  X = e ;
  X = i ;
  X = o ;
  X = u .
```

Existe uma otimização para casos menos genéricos que não requer visitar todas as cláusulas
de um predicado.
Assumindo que a base de fatos é estática, `vogal(u)` deveria ser trivialmente verdadeiro, e
`vogal(s(A))` deveria ser trivialmente falso.
Podemos nos aproximar desse ideal ao _indexar_ as cláusulas baseado nos seus argumentos
atômicos ou estruturados.

## Nível 0: por functor

O primeiro nível de indexação é quase trivial: quando buscarmos por cláusulas que possam
unificar-se com um termo, precisamos apenas considerar as cláusulas que formam um predicado,
isto é, que possuem o mesmo functor do termo.
Portanto, se queremos invocar o termo `f(a, X)`, nós vamos buscar apenas por cláusulas que
tenham o mesmo functor `f/2`. Qualquer outra nunca iria unificar.

## Nível 1: constantes vs variáveis

Para esta implementação simplificada, nós vamos utilizar apenas o _primeiro_ argumento como
chave de indexação.
É possível usar outros argumentos, ou até mesmo constantes aninhadas em structs, o que
levaria a estruturas de indexação mais complexas e eficientes, mas também fora das minhas
habilidades.
A WAM original também utilizava apenas indexação do primeiro argumento.

Se o primeiro argumento em uma chamada de predicado é uma ref livre, então não existe
indexação possível -- ela pode unificar com qualquer outro valor presente no primeiro argumento
das cláusulas do predicado.
Neste caso precisamos apenas caminhar por todas as cláusulas do predicado, na ordem em que
estão presentes no banco de dados.

Contudo, se o primeiro argumento é um átomo ou uma struct (mesmo que não fechada), podemos
ignorar muitas outras cláusulas cujo primeiro argumento não iria bater estruturalmente.
Nós ainda precisamos unificar com cláusulas cujo primeiro argumento seja uma variável, uma
vez que ela unifica com qualquer termo.
Como precisamos testar as cláusulas na ordem do banco de dados, a primeira indexação é
dividir a lista de cláusulas em sequências de constantes vs variáveis:

                      Olhamos apenas para o primeiro argumento
      ↓        ↓        ↓           ↓         ↓           ↓        ↓
    f(X, 0). f(a, 1). f(g(_), 2). f(a, 10). f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------
    variável           constantes               variáveis        constante

Para a consulta `f(A, B)`, é necessário testar todas as 7 cláusulas, em ordem:

    f(X, 0). f(a, 1). f(g(_), 2). f(a, 10). f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------

Para a consulta `f(a, B)`, é necessário testar todas que possuem uma variável como primeiro
argumento, e apenas aquelas que possuem `a` como primeira constante:

    f(X, 0). f(a, 1).             f(a, 10). f(Y, s(Y)). f(Z, a).             
    -------  -----------------------------  -------------------  ----------

Para a consulta `f(g(A), B)`, também é necessário testar todas as cláusulas que possuem
variáveis no primeiro argumento, mas dentre as constantes precisamos testar apenas aquelas
com `g/1` como functor no primeiro argumento:

    f(X, 0).          f(g(_), 2).           f(Y, s(Y)). f(Z, a). f(g(b), 5).
    -------  -----------------------------  -------------------  ----------

Finalmente, para a consulta `f(x, B)`, precisamos apenas testar as cláusulas com variáveis
no primeiro argumento, já que não existe alguma cláusula com `x` de primeiro argumento:

    f(X, 0).                                f(Y, s(Y)). f(Z, a).            
    -------  -----------------------------  -------------------  ----------

## Nível 2: Estrutura da constante

Como dito na seção anterior, precisamos apenas considerar as cláusulas que podem bater
estruturalmente com um dado termo.
Podemos acelerar as checagens por átomos e functores de struct utilizando tabelas hash,
que mapeiam da constante para uma lista de termos dentro de uma sequência de constantes,
em ordem de banco de dados.

                f(a, 1). f(g(_), 2). f(a, 10). f(b, 10).
                -------  ----------  --------  --------

O índice de cláusulas para cada átomo e functor:

    (atom) a:   f(a, 1).             f(a, 10).
           -    -------  ----------  --------  --------
    (atom) b:                                  f(b, 10).
           -    -------  ----------  --------  --------
    (func) g/1:          f(g(_), 2).
           ---  -------  ----------  --------  --------
  
Se o primeiro argumento do termo é um átomo ou functor, retorne todas as cláusulas na lista
correspondente.
Se for um var, retorne todas as cláusulas do predicado.
