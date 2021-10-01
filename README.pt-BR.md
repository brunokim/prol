# Prol: WAM demo

Esta é uma implementação simplificada da Máquina Abstrata de Warren (WAM) para Prolog,
que demonstra as principais instruções, compilação, alocação de registros e funções
da máquina.

## Organização do código

- model.py: Objetos de dados, representando termos, programas e entidades da máquina.
- compiler.py: Compilação de uma lista de regras em uma lista de instruções.
- interpreter.py: Interpretador que executa a listagem de instruções para uma dada consulta.
- grammar.py: Uma aplicação de exemplo do interpretador, com uma gramática que parseia a si mesma.

## Documentação

1. [Sobre Prolog](docs/about-prolog.md): uma introdução apressada se você não sabe do que isso se trata.
1. [Estratégia de resolução](docs/resolution.md): como uma consulta é realmente resolvida em Prolog.
1. [Warren Abstract Machine](docs/wam.md): tentativa de explicar a implementação.
1. [Indexando](docs/indices.md): implementação de indexação para acelerar alguns padrões de chamada.
1. [Parsing](docs/parsing.md): explicação das estruturas básicas de parsing.
1. [Gramática](docs/grammar.md): documentação para a aplicação de exemplo de parsing de gramática.
1. [Coisas extras](docs/references.md): o que esta implementação simplificou da WAM, e referências.

