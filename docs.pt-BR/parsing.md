# Parsing

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

_Parsing_ é uma área onde linguagens lógicas se destacam, graças à sua
habilidade de assumir uma estrutura para uma sequência de caracteres ou
palavras, e então recuar arbitrariamente se ela se revelar não sendo
válida de acordo com uma gramática.
Por isso, eu decidi usar um _parser_ para a própria linguagem para
demonstrar suas capacidades.

## Listas, listas incompletas

Esta implementação não faz das listas objetos integrados à linguagem,
mas elas podem ser facilmente representadas com _células cons_, ou
listas ligadas.
Uma célula cons é simplesmente uma struct com functor `./2` que pode
ser usada para definir uma lista recursivamente:

- `[]` (um átomo) é a lista vazia;
- `.(X, Y)` é uma lista contendo o elemento `X` (cabeça) seguido da
  lista `Y` (cauda).

Uma lista é então construída por uma cadeia de células cons, como a
representação a seguir da lista `[a, b, c, d]`:

```prolog
.(a, .(b, .(c, .(d, []))))
```

Células cons têm esse nome de *construct*.
Elas são a estrutura de dados mais simples e talvez a mais versátil,
tendo sido usada para definir a linguagem Lisp nos anos 1950.

A caudad de uma lista não necessariamente precisa ser uma lista vazia.
Se ela for uma variável livre, nós a chamamos de uma *lista incompleta*,
como

```prolog
.(a, .(b, .(c, .(d, X))))
```

Isto representa a lista `[a, b, c, d|X]`, que pode ser lida como "a sequência
de átomos `a`, `b`, `c`, `d`, seguido de uma lista desconhecida `X`".

Uma célula cons pode ter um valor na cauda que não seja uma lista, como
`.(a, b)`. Neste caso, nós a chamamos de uma *lista imprópria*.

Usar listas incompletas pode ser útil para definir uma linguagem recursivamente.
Por exemplo, a linguagem `(ab|c)+` aceita as strings
`ab`, `c`, `abab`, `abc`, `cab`, `cc`,
e daí por diante.
Podemos escrever um predicado que avalia se uma lista de átomos é aceita por tal linguagem:

```prolog
% Caso base: [a, b] ou [c]
lang_abc(.(a, .(b, []))).
lang_abc(.(c, [])).

% Caso recursivo
lang_abc(.(a, .(b, X))) :-
  lang_abc(X).
lang_abc(.(c, X)) :-
  lang_abc(X).
```

Qual é o resultado para a consulta `lang_abc(.(c, .(c, .(a, .(b, .(a, [])))))).`?
Você consegue traçar a execução?

## Exemplo: implementando `append/3`

Uma operação básica de listas é concatenar duas delas para gerar uma terceira.
Por exemplo, a concatenação de `L0 = .(a, .(b, []))` e `L1 = .(c, .(d, .(e, [])))`
deve ser `L2 = .(a, .(b, .(c, .(d, .(e, [])))))`.
Isto está implementado no predicado `append(L0, L1, L2)` abaixo:

```prolog
% Caso base: concatenação de [] e B é B
append([], B, B).

% Caso recursivo: L2 (= [Y|C]) é a concatenação de L0 (= [X|A]) e L1 (= B) se
% Y = X, e C é a concatenação de A e B.
append(.(X, A), B, .(X, C)) :-
    append(A, B, C).
```

`append` é o nome histórico desse predicado, que se traduz para "juntar". Embora
o nome pareça indicar uma ação, ele ainda apenas descreve uma relação entre três listas.
Podemos utilizá-lo para resolver problemas lógicos onde qualquer um dos argumentos é desconhecido,
não apenas para obter a concatenação direta quando `L0` e `L1` estão ligadas:

```prolog
% Qual é a concatenação de [a] e [b]?
?- A = .(a, []), B = .(b, []), append(A, B, X).
X = .(a, .(b, [])).

% Qual X, que quando concatenado em [a, b], produz [a, b, z]?
?- A = .(a, .(b, [])), C = .(a, .(b, .(z, []))), append(A, X, C).
X = .(z, []).

% Qual X que, quando concatenado com [z], produz [z]?
?- B = .(z, []), C = .(z, []), append(X, B, C).
X = [].

% Quais concatenações de X e Y produzem [a, b]?
?- append(X, Y, .(a, .(b, []))).
X = [], Y = .(a, .(b, [])) ;
X = .(a, []), Y = .(b, []) ;
X = .(a, .(b, [])), Y = [].
```

## Diferença de listas

Uma diferença de lista é, conceitualmente, o par de uma lista incompleta e sua cauda.
Isto é, o par `[a, b, c|T] - T` define a lista `[a, b, c]` como a "diferença" entre
`[a, b, c|T]` e `T`.
Isto é uma abstração útil para se escrever predicados lidando com uma pequena seção
de uma lista maior, sem saber o que pode estar no restante da lista maior `T`.

Por exemplo, a linguagem de parênteses angulares balanceados, como "<>", "<<>>", "<><<>>"
pode ser descrita com a seguinte definição:

- `L = "<>"`; ou
- `L = L0 L1`, se L0 e L1 forem parte da linguagem; ou
- `L = "<" L0 ">"`, se L0 é parte da linguagem.

Podemos simplificar a gramática um pouco se também aceitarmos a string vazia; neste
caso, a gramática se torna

```ebnf
L ::= "" ;
L ::= "<" L ">" L ;
```

Podemos escrever um predicado sem utilizar diferenças de lista, mas isso requer utilizar
`append/3` e tem um desempenho ruim:

```prolog
parens([]).
parens(.(<, L)) :-
    append(L0, L1, L),        % #1
    parens(L1),
    append(L2, .(>, []), L0), % #2
    parens(L2).
```

Na nota #1, nós invocamos `append(L0, L1, L)` para quebrar a lista `L` em duas componentes.
Esta implementação tenta todas as possíveis divisões em sequência, recuando se mais adiante
descobrir que a divisão produziu uma subsequência inválida.

Na nota #2, `append/3` vai percorrer toda a lista `L0` apenas para se certificar que ela
termina com um `>`, armazenando os elementos anteriores em `L2`.
Isto é, para consumir um único caractere ela precisa caminhar sobre N outros, o que leva a
uma complexidade de tempo quadrática.

Agora, compare com uma implementação alternativa utilizando diferença de listas, onde cada
cláusula recebe dois argumentos, correspondentes às partes da diferença:

```prolog
parens(T, T).
parens(.(<, L), T) :-
    parens(L, .(>, T0)), % #1
    parens(T0, T).
```

Isto é não apenas mais simples, mas também muito mais eficiente.
Pode ser necessário algum tempo para entender, então vamos nos aprofundar:

A primeira cláusula representa a diferença de listas `T-T`, isto é, uma lista vazia.
A segunda cláusula conceitualmente "divide" a diferença de listas `L-T` em `L-T0` e
`T0-T`.
De certo modo, `L - T = (L - T0) + (T0 - T)`.

Na nota #1, a diferença de listas `L-[>|T0]` se certifica de que `L` termine com `>`.
Para ver isso, considere que `A-B = (A-Z)-(Z+B)`, com `Z = [>]`, `A-Z = L` e `Z+B = [>|T0]`.

Esta abordagem é mais eficiente porque ela lida com um caractere por vez, e não a lista inteira.
A restrição de que um parêntese aberto deve ser pareado com um fechado é construída gradualmente
como uma lista incompleta no segundo argumento.
Quando essa lista unifica com uma subsequência da lista, os parênteses fechados são consumidos
e a resolução continua no restante da lista.
A complexidade de tempo é linear.

Você consegue detalhar a execução de `parens(.(<, .(<, .(>, .(>, .(<, .(>, [])))))), [])`?
Você consegue também para a versão usando `append/3`?
