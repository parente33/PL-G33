# Fase 1 - Análise Léxica

import ply.lex as lex
import re
import sys

# ------------------------------------------ PRÉ-PROCESSAMENTO ------------------------------------------ #

def preprocess_fixed_form(source: str) -> list[tuple[int, str]]:
    """
    Converte o código Fortran em formato fixo numa lista de (numero_linha_original, conteudo_logico), já com:
        - comentários removidos
        - linhas de continuação unidas
        - colunas 73+ removidas
        - conversão para maiúsculas (exceto strings)

    Retorna lista de tuplos (linha_original, texto) para preserver informação de linha para mensagens de erro.
    """

    lines = source.splitlines()
    logical_lines = []              # lista de (linha_inicio, texto_completo)

    i = 0
    while i < len(lines):
        raw = lines[i]
        lineon = i + 1

        raw = raw.rstrip('\r\n')
        raw = raw[:72]              # ignorar a partir da 73ª coluna

        # Coluna 1: 'C', 'c', '*', ou '!' indicam linha de comentário completa
        if raw and raw[0] in ('C', 'c', '*', '!'):
            i += 1
            continue

        # linha completamente em branco
        if not raw.strip():
            i += 1
            continue

        # Coluna 6: continuação de linha (esta linha continua a anterior)
        if len(raw) >= 6 and raw[5] not in (' ', '0', '\t'):
            # linha de continuação: anexa-se colunas 7-72 à linha lógica anterior
            continuation = raw[6:]
            if logical_lines:
                logical_lines[-1] = (logical_lines[-1][0], logical_lines[-1][1] + continuation)
            i += 1
            continue

        # Linha normal: extrai-se colunas 7-72 como código
        # Colunas 2-5: label, trata-se em separado
        label = raw[1:5].strip() if len(raw) >= 5 else ''
        code = raw[6:] if len(raw) > 6 else ''

        # Inline comentários com '!', remover tudo que não esteja dentro de uma string
        code = remove_inline_comment(code)

        # Reconstruir linha com label (se existir) para o lexer ver o label como token
        if label.isdigit():
            logical_lines.append((lineon, f"{label} {code}"))
        else:
            logical_lines.append((lineon, code))

        i += 1

    return logical_lines


def remove_inline_comment(code: str) -> str:
    """
    Remove comentários inline (marcados sempre após um '!') respeitando strings definidas
    """

    in_string = False
    for idx, ch in enumerate(code):
        if ch == "'":
            in_string = not in_string
        elif ch == '!' and not in_string:
            return code [:idx]

    return code


def join_logical_lines(logical_lines: list[tuple[int, str]]) -> str:
    """
    Une todas as linhas lógicas numa única string para o lexer, inserindo
    newlines para que o PLY possa rastrear números de linha.
    """

    return '\n'.join(code for _, code in logical_lines)


# ------------------------------------------ TOKENS ------------------------------------------ #

keywords = {
    # Estrutura do programa
    'PROGRAM'       : 'PROGRAM',
    'END'           : 'END',
    'STOP'          : 'STOP',
    'RETURN'        : 'RETURN',

    # Declarações de tipo
    'INTEGER'       : 'INTEGER',
    'REAL'          : 'REAL',
    'DOUBLE'        : 'DOUBLE',
    'PRECISION'     : 'PRECISION',
    'COMPLEX'       : 'COMPLEX',
    'CHARACTER'     : 'CHARACTER',
    'LOGICAL'       : 'LOGICAL',

    # Controlo de fluxo
    'IF'            : 'IF',
    'THEN'          : 'THEN',
    'ELSE'          : 'ELSE',
    'ELSEIF'        : 'ELSEIF',
    'DO'            : 'DO',
    'CONTINUE'      : 'CONTINUE',
    'GOTO'          : 'GOTO',
    'ENDIF'         : 'ENDIF',

    # I/0
    'READ'          : 'READ',
    'WRITE'         : 'WRITE',
    'PRINT'         : 'PRINT',
    'OPEN'          : 'OPEN',
    'CLOSE'         : 'CLOSE',
    'FORMAT'        : 'FORMAT',

    # Subprogramas
    'SUBROUTINE'    : 'SUBROUTINE',
    'FUNCTION'      : 'FUNCTION',
    'CALL'          : 'CALL',
    'COMMON'        : 'COMMON',
    'SAVE'          : 'SAVE',
    'EXTERNAL'      : 'EXTERNAL',
    'INTRINSIC'     : 'INTRINSIC',
    'IMPLICIT'      : 'IMPLICIT',
    'NONE'          : 'NONE',
    'PARAMETER'     : 'PARAMETER',
    'DIMENSION'     : 'DIMENSION',
    'EQUIVALENCE'   : 'EQUIVALENCE',
    'DATA'          : 'DATA',
}

relational_ops = {
    '.EQ.'  : 'OP_EQ',    # ==
    '.NE.'  : 'OP_NE',    # /=
    '.LT.'  : 'OP_LT',    # <
    '.LE.'  : 'OP_LE',    # <=
    '.GT.'  : 'OP_GT',    # >
    '.GE.'  : 'OP_GE',    # >=
}

logical_ops = {
    '.AND.'     : 'OP_AND',
    '.OR.'      : 'OP_OR',
    '.NOT.'     : 'OP_NOT',
    '.EQV.'     : 'OP_EQV',
    '.NEQV.'    : 'OP_NEQV',
}

logical_literals = {
    '.TRUE.'    : 'LOGICAL_TRUE',
    '.FALSE.'   : 'LOGICAL_FALSE',
}

tokens = (
    list(keywords.values()) +
    list(relational_ops.values()) +
    list(logical_ops.values()) +
    list(logical_literals.values()) +
    [
        # Identificadores e literais
        'ID',               # identificadores (nomes de variáveis, funções, ...)
        'INT_LITERAL',      # literais inteiros: 42, -3, ...
        'REAL_LITERAL',     # literais reais: 3.14, 1.5E-3, ...
        'STR_LITERAL',      # literais de string: 'Ola, Mundo!'
        'LABEL',            # labels numéricos: 10, 20, 30 (colunas 2-5)

        # Operadores aritméticos
        'PLUS',             # +
        'MINUS',            # -
        'STAR',             # * (multiplicação ou ponteiro de formato)
        'SLASH',            # /
        'DSTAR',            # ** (potência)
        'DSLASH',           # // (concatenação de strings)

        # Operadores de atribuição
        'EQUALS',           # =

        # Delimitadores
        'LPAREN',           # (
        'RPAREN',           # )
        'COMMA',            # ,
        'COLON',            # :
        'SEMICOLON',        # ;
        'DOT',              # . (para acesso a campos de estrutura)
        'DOLLAR',           # $ (usado em algumas extensões)

        # Especial
        'NEWLINE',          # \n (fim de instrução lógica)
        'AMPERSAND'         # & (continuação em formato livre)
    ]
)

tokens = tuple(dict.fromkeys(tokens))

# Usa-se um estado especial 'string' para tokenizar literais de string, que não devem ser convertidos para maiúsculas
states = (
    ('string', 'exclusive'),  # dentro de uma string Fortran (aspas simples)
)

# Buffer para construção de strings
_string_buffer = ''
_string_start_line = 0


# ------------------------------------------ ESTADO NORMAL ------------------------------------------ #

def t_COMMENT(t):
    r'![^\n]*'
    # Comentários inline com '!': ignorar (já tratados no pré-processador,
    # mas podem aparecer se o user não usar o formato fixo)
    pass


def t_LABEL(t):
    r'^\d+'
    t.value = int(t.value)
    return t


def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
    t.lexer.at_line_start = True
    return t


# Ignorar espaços e tabulações
t_ignore = ' \t\r'


def t_REAL_LITERAL(t):
    r'(\d+\.\d*|\.\d+)([EDed][+-]?\d+)?|\d+[EDed][+-]?\d+'
    t.value = float(t.value.upper().replace('D', 'E'))
    return t


def t_INT_LITERAL(t):
    r'\d+'
    t.value = int(t.value)
    return t


def t_STRING_START(t):
    r"'"
    # Início de literal de string — transição para estado 'string'
    global _string_buffer, _string_start_line
    _string_buffer = ''                 # Aspas únicas em vez de duplas, porque duplas são expansão
    _string_start_line = t.lexer.lineno
    t.lexer.begin('string')
    # Não retornamos token ainda


def t_DSTAR(t):
    r'\*\*'
    return t


def t_DSLASH(t):
    r'//'
    return t


def t_PLUS(t):
    r'\+'
    return t


def t_MINUS(t):
    r'-'
    return t


def t_STAR(t):
    r'\*'
    return t


def t_SLASH(t):
    r'/'
    return t


def t_EQUALS(t):
    r'='
    return t


def t_LPAREN(t):
    r'\('
    return t


def t_RPAREN(t):
    r'\)'
    return t


def t_COMMA(t):
    r','
    return t


def t_COLON(t):
    r':'
    return t


def t_SEMICOLON(t):
    r';'
    return t


def t_AMPERSAND(t):
    r'&'
    return t


def t_DOLLAR(t):
    r'\$'
    return t


def t_DOT_OPERATOR(t):
    r'\.[A-Za-z]+\.'
    # Operadores da forma .XYZ. — relacionais, lógicos e literais booleanos
    # Captura-se todos de uma vez e classifica-se por dicionário
    val = t.value.upper()

    if val in relational_ops:
        t.type = relational_ops[val]
    elif val in logical_ops:
        t.type = logical_ops[val]
    elif val in logical_literals:
        t.type = logical_literals[val]
        t.value = (val == '.TRUE.')  # converte para bool Python
    else:
        # Operador desconhecido da forma .XYZ.
        print(f"[LEXER] Erro: operador desconhecido '{t.value}' na linha {t.lexer.lineno}", file=sys.stderr)
    return t


def t_ID(t):
    r'[A-Za-z][A-Za-z0-9_]*'
    # Identificadores em Fortran 77 têm máx. 6 caracteres,
    val = t.value.upper()

    if val not in keywords and len(val) > 6:
        # Emite-se só aviso
        print(f"[LEXER] Aviso: identificador '{val}' excede 6 caracteres (linha {t.lexer.lineno})", file=sys.stderr)

    # Verificar se é palavra-chave
    t.type = keywords.get(val, 'ID')
    t.value = val
    return t


# ------------------------------------------ ESTADO 'STRING' ------------------------------------------ #

def t_string_ESCAPED_QUOTE(t):
    r"''"
    # Em Fortran 77, '' dentro de uma string representa um ' literal
    global _string_buffer
    _string_buffer += "'"


def t_string_END(t):
    r"'"
    # Fim da string
    global _string_buffer
    t.type = 'STR_LITERAL'
    t.value = _string_buffer
    t.lexer.begin('INITIAL')
    return t


def t_string_NEWLINE(t):
    r'\n'
    # String não fechada até ao fim da linha — erro
    print(f"[LEXER] Erro: string não terminada na linha {_string_start_line}", file=sys.stderr)
    t.lexer.lineno += 1
    t.lexer.begin('INITIAL')


def t_string_CONTENT(t):
    r"[^'\n]+"
    # Conteúdo normal da string (tudo excepto ' e \n)
    global _string_buffer
    _string_buffer += t.value


# Ignorar nada no estado string (cada carácter é significativo)
t_string_ignore = ''


# ------------------------------------------ ERROS ------------------------------------------ #

def t_error(t):
    print(f"[LEXER] Erro: carácter ilegal '{t.value[0]}' na linha {t.lexer.lineno}", file=sys.stderr)
    t.lexer.skip(1)


def t_string_error(t):
    print(f"[LEXER] Erro (string): carácter inesperado '{t.value[0]}' na linha {t.lexer.lineno}", file=sys.stderr)
    t.lexer.skip(1)


# Construção do lexer
lexer = lex.lex(debug=False, reflags=re.UNICODE)


def tokenize(source: str, filename: str = '<stdin>') -> list:
    """
    Recebe o código-fonte Fortran 77 (em formato fixo) como string e
    devolve uma lista de tokens PLY.

    Cada token tem os atributos:
      .type   — tipo do token (string)
      .value  — valor semântico (string, int, float, bool)
      .lineno — número de linha no fonte original
      .lexpos — posição em bytes no input do lexer

    Etapas:
      1. Pré-processamento
      2. Conversão para maiúsculas do código (não das strings)
      3. Tokenização
    """
    # 1.
    logical_lines = preprocess_fixed_form(source)

    if not logical_lines:
        return []

    # 2.
    combined = join_logical_lines(logical_lines)

    # 3.
    lx = lexer.clone()
    lx.input(combined)

    result = []
    for tok in lx:
        # Filtrar NEWLINEs redundantes consecutivos
        if tok.type == 'NEWLINE' and result and result[-1].type == 'NEWLINE':
            continue
        result.append(tok)

    return result


def tokenize_file(path: str) -> list:
    """Lê um ficheiro Fortran 77 e tokeniza-o."""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return tokenize(f.read())