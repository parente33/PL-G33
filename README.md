# Compilador para Fortran 77 - Projeto

Este projeto consiste no desenvolvimento de um compilador para a linguagem Fortran 77, implementado em Python com recurso à biblioteca PLY (lex e yacc). O compilador é responsável por analisar programas escritos em Fortran, validar a sua estrutura sintática e semântica, e gerar código para a máquina virtual fornecida no âmbito da unidade curricular.

## 1. Estrutura do Repositório

O projeto está dividido em duas componentes principais localizados na pasta principal:

- **src/**: Contém a implementação do compilador:

    - analisador léxico: [lexer.py](src/lexer.py)

    - analisador sintático: [parser.py](src/parser.py)

    - analisador semântico: [semantic.py](src/semantic.py)

    - geração de código para a VM: [codegen.py](src/codegen.py)

- **tests/**: Contém programas de teste em Fortran 77 utilizados para validar o funcionamento do compilador, bem como os respetivos ficheiros de saída esperados.

## 2. Tecnologias Utilizadas

- **Python 3**: Linguagem utilizada no desenvolvimento do compilador.

- **PLY**: Biblioteca utilizada para construção do analisador léxico e sintático.

- **EWVM**: Ambiente alvo para geração e execução do código produzido pelo compilador. [link](https://ewvm.epl.di.uminho.pt/)

## 3. Como Executar

Criar ambiente virtual:

```console
python3 -m venv venv
source venv/bin/activate
```

Instalar dependências:

```console
pip install -r requirements.txt
```

e depois executar o compilador:

```console
python3 src/main.py [fase] tests/[ficheiro] [opções]
```

## 4. Documentação Detalhada

Para uma análise mais profunda do projeto, por favor consultar o relatório técnico:

[RELATORIO.md](RELATORIO.md)