# Compilador para Fortran 77 - Projeto

Este projeto consiste numa plataforma web para a gestão e visualização de inquirições históricas presentes no Arquivo Distrital de Braga. A solução foi desenhada seguindo uma arquitetura de serviços distribuídos para garantir a separação de responsabilidades entre autenticação, lógica de negócio e a interface do utilizador.

## 1. Estrutura do Repositório

O projeto está dividido em duas componentes principais localizados na pasta principal:

- **src/**: Diretoria onde se encontram os ficheiros .py, que implementam o compilador.

- **tests/**: Diretoria com os ficheiros de teste Fortran, e uma main dedicada a testar o compilador.

## 2. Tecnologias Utilizadas

- **ply**:

...

## 3. Como Executar

Criar ambiente virtual:

```console
python3 -m venv venv
source venv/bin/activate
```

e depois executar a main:

```console
python3 src/main.py [fase] tests/[ficheiro] [opções]
```

## 4. Documentação Detalhada

Para uma análise mais profunda do projeto, por favor consultar o relatório técnico:

[RELATORIO.md](RELATORIO.md)