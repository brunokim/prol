# Coisas extras (ou: leitura suplementar)

1. [Sobre Prolog](about-prolog.md)
1. [Estratégia de resolução](resolution.md)
1. [Warren Abstract Machine](wam.md)
1. [Indexando](indices.md)
1. [Parsing](parsing.md)
1. [Gramática](grammar.md)
1. [Coisas extras](references.md)

## Layout de memória

A Máquina Abstrata de Warren foi proposta como um alvo viável para se implementar um
interpretador ou compilador de baixo nível.
Como tal, ela assume um layout de memória linear e contíguo, onde o ambiente de execução
é responsável por administrar alocação de células e sua eventual limpeza.
Ela divide a memória nas seguintes regiões principais:

- *Registradores*, que idealmente devem corresponder ao banco de registradores da arquitetura
alvo;
- *Pilha*, uma região volátil que cresce ao armazenar ambientes e _choice points_, e diminui
ao retroceder ou desalocar um ambiente;
- *Heap*, região onde são postas as células de mais longa duração, que devem ser sempre
referenciadas, direta ou indiretamente, por outras células nos registradores ou na pilha;
- *Trilha*, onde referências ligadas são armazenadas, para serem desfeitas ao retroceder;

Uma vez que os registradores são fundamentalmente um recurso limitado, uma WAM de baixo nível
precisa ter alguma estratégia para *derramar* células para a pilha quando uma cláusula requer
mais registradores do que está disponível.

Nesta implementação, nós confiamos na GC do Python para manter um objeto em memória enquanto
ele é referenciado. Isto simplifica várias características da WAM:
- Um ambiente desalocado ainda pode ser referenciado por um _choice point_ enterrado fundo
na pilha. A WAM organiza a pilha de um jeito esperto de modo que o ambiente não é *de fato*
desalocado se ainda existe um _choice point_ que o referencia.
- Células na heap nunca devem referenciar uma célula nos registradores ou na pilha, que são
fundamentalmente voláteis.
Esta situação é checada durante a execução em potenciais valores "inseguros", e se acontecerem
a célula na região volátil é promovida para a heap.
- Apesar do artigo original não se preocupar com isso, a heap pode ficar poluída de células
que não são mais referenciadas.
Uma implementação efetiva iria considerar limpar e reutilizar esse espaço disponível.

Na nossa implementação, a trilha é quebrada em partes e associada a cada _choice point_.
Na WAM, a trilha é uma região contígua, que cresce quando uma variável condicional é ligada,
e diminui ao retroceder.

## Instruções removidas

A WAM utiliza instruções especializadas para inserir, atualizar e remover _choice points_
da pilha: `try_me_else`/`retry_me_else`/`trust_me`, respectivamente.
Estas instruções são colocadas no início das cláusulas em um predicado com múltiplas
cláusulas, formando uma lista ligada que a máquina percorre ao retroceder.
Aqui, nós realizamos a checagem de se o predicado tem múltiplas cláusulas durante a
execução.

Esta implementação realizada a indexação parcialmente durante a execução: o primeiro
argumento de um termo sendo chamado é utilizado para construir uma lista de cláusulas
cuja cabeça pode se unificar com o termo.
A WAM também realiza indexação, mas estas listas são construídas de forma inteligente
em tempo de compilação!
Basicamente, o ponto de entrada de um predicado não é sua primeira cláusula, mas um
cabeçalho de instruções especiais que direcionam o fluxo de execução para as cláusulas
subjacentes.
Instruções como `switch_on_term`/`switch_on_atom`/`switch_on_struct` escolhem a cláusula
baseado no tipo do primeiro argumento, preservando a mesma ordem de resolução.
Quando existem múltiplas cláusulas com o mesmo tipo, a máquina também caminha apenas
sobre elas usando uma lista ligada criada com as instruções `try`/`retry`/`trust`.

## Gramática

A gramática criada é intencionalmente mais pobre que um Prolog usual, para não tornar o
estudo mais complexo. Algumas coisas interessantes a serem adicionadas:

- Comentários, começando com '%' e seguindo até o fim da linha (ou do programa);
- Listas, tanto fechadas como `[a,b,c]` e incompletas como `[a,b,c|X]`;
- Strings de texto, utilizando aspas duplas para significar uma lista, isto é, `"abc" = [a,b,c]`;
- Caracteres de escape em átomos; a gramática atual utiliza duas aspas simples em sequência
para significar uma aspa simples dentro de um átomo.
Outros Prologs usam a barra invertida para escapar a aspa simples, o que exige também
escapar a própria barra invertida, e até outros caracteres como LF e tab.
- As construções que fizemos com diferenças de listas são tão especiais que merecem uma
sintaxe própria, de _definite clause grammar_ ou DCG. A conversão de um DCG para uma cláusula
usando diferença de listas é razoavelmente direta.

## Epílogo

Eu espero que este repositório seja um recurso legal de estudo para todos os 4 de vocês
que se interessam em aprender sobre um compilador de linguagem lógica.
Alguns problemas conhecidos:

- A alocação de registradores não sabe quando uma variável não é mais usada; algumas vezes
é seguro sobrescrevê-la, mas atualmente o compilador guarda a variável em um registrador
seguro antes de substitui-la, ocupando mais espaço e tempo que o necessário;
- A compilação de structs, tanto para as instruções "get" e "put", parece mais complexa do
que necessário;
- Não deve ser muito complexo compilar as cláusulas em uma ordem que nos permita saber quantos
registrador um predicado sendo chamado utiliza.
Isto nos permitiria manter variáveis permanentes em registradores "seguros", economizando em
alocação de slots de ambiente. Basta utilizar ordenação topológica!
- Não estamos tratando casos de variáveis solitárias ou nulas.
Isto é, em `f(_, _, a)` as duas primeiras variáveis são consideradas a mesma.
Somos forçados a escrever `f(_1, _2, a)` para ter o mesmo efeito que o esperado em outros Prologs.

## Referências (em inglês)

- Glossary, SWI-Prolog ([link](https://www.swi-prolog.org/pldoc/man?section=glossary)): um recurso muito útil sobre os termos
usados em programação lógica para fraudes autodidatas como eu. Veja os comentários também!
- "Warren Abstract Machine: a tutorial reconstruction", Hassan Aït-Kaci, 1999 ([link](http://wambook.sourceforge.net/)):
  o melhor recurso para se começar a entender a famosa WAM
- "Register Allocation in a Prolog Machine", Saumya K. Debray, 1986 ([link](https://www.semanticscholar.org/paper/Register-Allocation-in-a-Prolog-Machine-Debray/be79bf12014c53607e7933717b710ac8a7bd9261)): algoritmo de alocação de registros utilizado
  nessa implementação.
- "Prolog DCG Primer", [Markus Triska](https://github.com/triska) ([link](https://www.metalevel.at/prolog/dcg)): uma boa e completa introdução sobre DCGs

