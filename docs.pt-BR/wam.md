# Warren Abstract Machine

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Justificativa

Para a execução eficiente de programas em Prolog é necessário compilá-lo em uma
arquitetura de baixo nível.
David S. Warren propôs em 1983 um conjunto de instruções abstratas para serem
executadas em uma máquina abstrata, simples mas receptiva a uma implementação em 
linguagem de máquina.
A máquina abstrata proposta ficou conhecida com seu nome (_Warren Abstract Machine_, ou _WAM_),
e este repositório tem a intenção de demonstrar seus principais pontos.
Para entendê-la por completo, eu recomendo o tutorial de Hassan Aït-Kaci.

Esta implementação não se preocupa com todos os detalhes de baixo nível, em especial
ignorando gerenciamento de memória.
Isto simplifica muitas das instruções, que precisam considerar como mover e descartar
dados, além de se preocupar que ponteiros não apontem de memória permanente para
memória volátil.
Aqui, todos os dados são armazenados em objetos normais de Python, que são acessíveis
enquanto existir um ponteiro que aponte para eles.

A WAM é uma máquina de registradores, e predicados são tratados como funções.
Executar um predicado de dentro do corpo de outro é similar a uma chamada de função.
A convenção de chamada é passar os argumentos do predicado via registradores X0-Xn para
a função sendo invocada.
Dado que a execução de predicados normalmente move os registradores de lugar, qualquer
variável que precise ser preservada entre chamadas de função é armazenada em um _ambiente_
(_environment_, ou _stack frame_).
Tomamos aqui algum cuidado para minimizar o número de movimentações de registrador e
alocações de ambientes.

Em resumo, uma cláusula como

```prolog
pred(X, Y, Z) :-
  f(Y, X, a),
  Z \== q(X),
  g(Z, r(s(1, 2), s(3, 4))).
```

é traduzida nas seguintes instruções (`@X` significa "endereço de X", que por enquanto é
um lugar abstrato, mas será explicado junto com as instruções)

```text
% Pega os argumentos passados nos registradores X0-X2 
get X0, @X
get X1, @Y
get X2, @Z

% Coloca os argumentos da chamada f(Y, X, a)
put X0, @Y
put X1, @X
put X2, @a
call f/3

% Constroi a struct q(X) no registrador X0
put X0, q/1
set_arg @X

% \== é uma função builtin
builtin \==, @Z, X0

% Coloca o primeiro argumento da chamada a g/2 em X0
put X0, @Z

% Constroi s(1, 2) no registrador X2
put X2, s/2
set_arg 1
set_arg 2

% Constroi s(3, 4) no registrador X3
put X3, s/2
set_arg 3
set_arg 4

% Constroi r(s(...), s(...)) no registrador X1
put X1, r/2
set_arg X2
set_arg X3

% Chama g/2 com os registradores X0, X1 preenchidos
call g/2
```

Existe um pouco mais de nuance aqui porque existem variantes de cada uma dessas
instruções, que iremos apresentar melhor abaixo.
Primeiramente, precisamos apresentar os tipos de células de memória:

## Tipos de célula de memória

Existes três tipos de células, correspondentes a cada tipo de termo:

- AtomCell: contém um átomo
- StructCell: contém uma struct com nome a aridade fixos. Pode não ter todos os argumentos preenchidos.
- Ref: ponteiro para outra célula. Pode estar livre (`value = None`) ou ligado (`value` está setado).

Células podem ser armazenadas em registradores (voláteis) ou em slots do ambiente (permanentes).
Quando nos referimos a um registrador usamos `Xi`, e para slots usamos `Yi`.
Quando estamos nos referindo a qualquer um, usamos `Addr`.

## Instruções `get` e `unify`

Existem quatro instruções "get" para ler os argumentos passados para um predicado:

- `get_var <Xi>, <Addr>`: usada para variáveis ainda não referenciadas dentro da cláusula.
  Move a célula em Xi para Addr
- `get_val <Xi>, <Addr>`: usada para variáveis que já foram referenciadas e armazenadas em
  Addr. Unifica os conteúdos de Xi com Addr.
- `get_atom <Xi>, <Atom>`: usada para constantes em argumentos. Unifica o conteúdo de Xi com
  o átomo.
- `get_struct <Xi>, <f/n>`: usada para structs em argumentos. As instruções "unify" na sequência
  manipulam cada argumento.
  Se uma Ref livre for passada em Xi, começa a construir uma struct ligada a ela; se uma StructCell
  é passada, começa a ler seus argumentos.

Se esperamos structs na cabeça de uma cláusula, então durante a execução podem ou
ligar esta struct com uma var, ou unificar a struct argumento a argumento.
Digamos, o fato a seguir:

```prolog
pred(X, 1, f(X, g(a)), X).
```

pode ser chamado com qualquer das seguintes consultas:

```prolog
?- pred(b, 1, F, b).
?- pred(b, 1, f(b, G), b).
```

No primeiro caso, desejamos ligar `F = f(X, g(a))` para o 3º argumento.
No segundo caso, nós precisamos andar pela struct existente e unificar os argumentos
da struct correspondente na cabeça da cláusula, obtendo as ligações `X=b, g(a)=G`.
Para diferenciar estes casos, armazenamos um modo de leitura/escrita ao executar
`get_struct`: leitura se a célula é uma StructCell, escrita se ela for uma Ref.

As instruções para cada argumento são chamadas de "unify", acomodando ambos os modos,
uma vez que a decisão se dá em tempo de execução. Existem três tipos de instrução:

- `unify_var <Addr>`: usado para variáveis aninhadas em structs ainda não referenciadas
na cabeça da cláusula. No modo de leitura, move o argumento para Addr; no modo escrita,
cria uma Ref livre em Addr.
- `unify_val <Addr>`: usada para variáveis aninhadas em structs já referenciadas na
cabeça da cláusula. No modo leitura, unifica o argumento e Addr; no modo de escrita, 
sobrescreve o argumento com o conteúdo de Addr.
- `unify_atom <Atom>`: usada para átomos aninhados em structs. No modo leitura, unifica
o argumento e o átomo; em modo escrita, copia o átomo para o argumento.

Note que não existe nenhuma instrução `unify_struct`. Structs aninhadas em outras
structs são tratadas como novas variáveis ligadas à struct, recursivamente.

O exemplo acima deve ser compilado em:

```text
% pred/4
get_var    X0, X5   % X é armazenado in X5
get_atom   X1, 1
get_struct X2, f/2  % Começa a tratar f(.,.)
unify_val  X5       %   Arg #1: X já foi referenciado e armazenado em X5
unify_var  X6       %   Arg #2: struct aninhada g(a) será lida/escrita em X6
get_val    X5       % X já foi referenciada e armazanada em X5

get_struct X6, g/1  % Struct aninhada é unificada em X6
unify_atom a        %   Arg #1: unifica átomo com argumento
```

## Instruções `put`

Existem quatro instruções `put` para inserir argumentos nos registradores antes da
invocação de um predicado:

- `put_var <Xi>, <Addr>`: utilizada para variáveis ainda não referenciadas dentro do corpo
da cláusula.
Cria uma ref livre e a insere tanto em Xi quanto em Addr.
- `put_val <Xi>, <Addr>`: utilizada para variáveis já referenciada e armazenada em Addr.
Simplesmente insere a célula armazenada em Addr no registrador Xi.
- `put_atom <Xi>, <Atom>`: utilizada para argumentos constantes, copiando AtomCell para Xi.
- `put_struct <Xi>, <f/n>`: utilizada para construir structs como argumentos. Configura o modo da máquina para
escrita e utiliza as mesmas instruções "unify" para os argumentos da struct.

Por exemplo, a cláusula abaixo:

```prolog
p(X) :-
    q(X, 1, f(a, g(Y)), Y).
```

é compilada para

```none
% p/1
% Cabeça da cláusula
get_var X0, X4  % X é armazenado em X4

% Corpo
% Constroi struct aninhada g(Y)
put_struct X5, g/1  % Constroi struct em X5
unify_var  X6       %   Arg #1: Y é armazenado em X6

put_val    X0, X4  % Põe X de X4 em X0
put_atom   X1, 1   %
put_struct X2, f/2 % Escreve os args de f(.,.)
unify_atom a       %   Arg #1: escreve o átomo 'a'
unify_val  X5      %   Arg #2: escreve a struct construida em X5
put_val    X3, X6  % Y já foi referenciado, armazenado em X6

call q/4
```

No seu tutorial, Aït-Kaci argumenta que é melhor ter instruções separadas de "set" para
escrever os argumentos de uma struct criada com "put", ao invés de reutilizar as
instruções "unify".
Isto seria mais eficiente por evitar checar o modo de operação a cada passo, sendo que,
nesse caso, ele estaria sempre como de escrita.
Eu concordo, mas para este projeto estou focado em minimizar o conjunto de instruções ao
invés de eficiência.

## Instruções de controle

A instrução `call <f/n>` altera o ponteiro de instrução da máquina para a primeira
cláusula do predicado indicado por _f/n_. Se existem mais cláusulas no predicado, ela
empilha um _choice point_ armazenando o estado atual da máquina.

Uma vez que uma cláusula completa sua execução, é necessário retornar o controle para
logo após sua instrução `call` original (chamado _continuação_).
A sequência de chamadas pode ser arbitrariamente profunda, então a máquina também
mantém uma pilha de _ambientes_, onde cada um armazena a continuação naquela posição.

Um ambiente é criado e inserido da pilha com a instrução `allocate`, e removido com
a instrução `deallocate`. À primeira vista, toda cláusula deveria começar com `allocate`
e terminar com `deallocate`, mas nós podemos evitar criar ambientes em vários casos:

1. se a cláusula não realiza nenhuma `call`, como ocorre com fatos (cláusulas sem corpo);
2. se a única `call` for a última instrução da cláusula, nós simplesmente pulamos para
a próxima função, mantendo a mesma continuação de antes;

O segundo caso é uma otimização mais genérica da otimização de chamada de cauda (_tail-call
optimization_): qualquer chamada na última posição é invocada mantendo-se o mesmo
ambiente, então não existe impacto de memória em chamadas recursivas (de cauda)
arbitrariamente profundas. Nesta posição, a instrução `call` é substituída por uma
instrução `execute`, que altera o ponteiro de instrução sem alterar a continuação.

Para marcar o fim de uma cláusula que não emprega `allocate`/`deallocate`, nós temos
a instrução `proceed`, que apenas retorna a execução para a continuação atual.

## Variáveis temporárias e permanentes

Como já indicado, nós podemos armazenar células em registradores ou slots de ambiente.
Variáveis permanentes são estáveis e persistem ao longo de múltiplas chamadas, mas
requerem mais memória e movimento de dados. Por este motivo, nós buscamos utilizar
os registradores da maneira mais eficiente possível, dado que todos os valores precisam
estar presentes neles pela convenção de chamada, de qualquer modo.

Durante a compilação, nós anotamos quais variáveis podem ser deixadas nos registradores
(temporárias) e quais precisam ser permanentes e movidas para um slot.
A instrução `allocate <n>` na realidade precisa do número de slots necessários para o
ambiente a ser criado.

Por exemplo, na cláusula

```prolog
andar2(A, B) :-
    andar(A, C),
    andar(C, B).
```

Inicialmente, A estará no registrador X0, e B no registrador X1.
Um compilador ingênuo não checa se a chamada de `walk` utiliza 0, 1 ou 1000 registradores;
ela apenas assume que manter qualquer variável em um registrador é inseguro se precisarmos
utiliza-la após uma chamada.
Este não é o caso de A, que não precisa ser usada de novo após a primeira chamada a `andar`,
mas é o caso para B e C. Portanto, A é temporária e B, C são permanentes.
A cláusula é compilada em:

```none
% andar2/2

allocate 2      % Slots para B, C
                % A é mantida no registrador X0
get_var X1, Y0  % Move B para o slot Y0
put_var X1, Y1  % Cria C no slot Y1 e coloca em X1
call andar/2    % Chama andar(A, C)

put_val X0, Y1  % Põe C em X0
put_val X1, Y0  % Põe B em X1
deallocate      % Desempilha o ambiente, que não é mais necessário
execute andar/2 % Invoca (com a mesma continuação) andar(C, B)
```

Note que no exemplo acima pudemos manter A no mesmo registrador, porque ela seria
o argumento na mesma posição para a próxima chamada. Isto não é sempre o caso,
por exemplo,

```prolog
p(A, B, C) :- q(B, C, A).
```

requer que reservemos um registrador adicional para rotacionar todas as variáveis:

```none
% p/3
get_var X0, X4  % Move A temporariamente em X4 de X0
get_var X1, X0  % Move B de X1 para X0
get_var X2, X1  % Move C de X2 para X1
put_var X2, X4  % Põe A de X4 para X2
call q/3
```

Escolher o registrador para cada variável de modo que ela seja armazenada até ser
utilizada na posição adequada para uma chamada de função é um problema difícil,
conhecido como _alocação de registradores_.
Nós utilizamos um algoritmo de Saumya K. Debray, que é bom para minimizar
movimentação dos dados e reduzir o número de instruções.
