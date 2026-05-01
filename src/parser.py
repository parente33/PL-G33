# Fase 2 - Análise sintática

import ply.yacc as yacc
import sys
from lexer import tokens

from ast_nodes import *

# ------------------------------------------ Precedência de Operadores ------------------------------------------ #

# Ordem: do MENOS prioritário (topo) ao MAIS prioritário (fundo)
precedence = (
    # Operadores lógicos
    ('left',  'OP_EQV', 'OP_NEQV'),
    ('left',  'OP_OR'),
    ('left',  'OP_AND'),
    ('right', 'OP_NOT'),

    # Operadores relacionais
    ('nonassoc', 'OP_EQ', 'OP_NE', 'OP_LT', 'OP_LE', 'OP_GT', 'OP_GE'),

    # Concatenação de strings
    ('left',  'DSLASH'),

    # Aritméticos
    ('left',  'PLUS', 'MINUS'),
    ('left',  'STAR', 'SLASH'),

    # Potência (associatividade à direita: 2**3**2 = 2**(3**2))
    ('right', 'DSTAR'),

    # Unário (maior precedência)
    ('right', 'UMINUS', 'UPLUS'),
)

# ------------------------------------------------------------------------------------ #

def p_program_file(p):
    """ program_file : program_units """
    # Pós-processamento: resolver os DO loops depois de ter a lista plana
    units = [resolve_do_loops(unit) for unit in p[1]]
    p[0] = ProgramFile(units=units, lineno=1)


def p_program_units_multi(p):
    """ program_units : program_units program_unit """
    p[0] = p[1] + [p[2]]

def p_program_units_single(p):
    """ program_units : program_unit """
    p[0] = [p[1]]


# ------------------------------------------ Programa ------------------------------------------ #

def p_program_unit_main(p):
    """ program_unit : PROGRAM ID newlines declarations body END newlines_opt """
    p[0] = Program(name=p[2], declarations=p[4], body=p[5], lineno=p.lineno(1))

def p_program_unit_main_noname(p):
    """ program_unit : declarations body END newlines_opt """
    # Linguagem permite omitir PROGRAM nome
    p[0] = Program(name=None, declarations=p[1], body=p[2], lineno=1)

# --- FUNCTION ---

def p_program_unit_function(p):
    """ program_unit : type_spec FUNCTION ID LPAREN param_list RPAREN newlines \
                      declarations body END newlines_opt """
    p[0] = Subprogram(kind='FUNCTION', return_type=p[1], name=p[3], params=p[5], declarations=p[8], body=p[9], lineno=p.lineno(2))

def p_program_unit_function_notype(p):
    """ program_unit : FUNCTION ID LPAREN param_list RPAREN newlines \
                      declarations body END newlines_opt """
    p[0] = Subprogram(kind='FUNCTION', return_type=None, name=p[2], params=p[4], declarations=p[7], body=p[8], lineno=p.lineno(1))

# --- SUBROUTINE ---

def p_program_unit_subroutine(p):
    """ program_unit : SUBROUTINE ID LPAREN param_list RPAREN newlines \
                      declarations body END newlines_opt """
    p[0] = Subprogram(kind='SUBROUTINE', return_type=None, name=p[2], params=p[4], declarations=p[7], body=p[8], lineno=p.lineno(1))

def p_program_unit_subroutine_noparams(p):
    """ program_unit : SUBROUTINE ID newlines declarations body END newlines_opt """
    p[0] = Subprogram(kind='SUBROUTINE', return_type=None, name=p[2], params=[], declarations=p[4], body=p[5], lineno=p.lineno(1))

# --- Lista de parâmetros formais ---

def p_param_list_multi(p):
    """ param_list : param_list COMMA ID """
    p[0] = p[1] + [p[3]]

def p_param_list_single(p):
    """ param_list : ID """
    p[0] = [p[1]]

def p_param_list_empty(p):
    """ param_list : """
    p[0] = []

# ------------------------------------------ Declarações ------------------------------------------ #

def p_declarations_multi(p):
    """ declarations : declarations declaration """
    p[0] = p[1] + p[2]

def p_declarations_empty(p):
    """ declarations : """
    p[0] = []


def p_declaration(p):
    """ declaration : type_spec declarator_list newlines """
    type_name = p[1]
    decls = []
    for name, dims in p[2]:
        if dims is None:
            decls.append(VarDecl(type_name=type_name, names=[name], lineno=p.lineno(1)))
        else:
            decls.append(ArrayDecl(type_name=type_name, name=name, dimensions=dims, lineno=p.lineno(1)))
    p[0] = decls

def p_declaration_implicit_none(p):
    """ declaration : IMPLICIT NONE newlines """
    p[0] = [ImplicitNone(lineno=p.lineno(1))]

def p_declaration_parameter(p):
    """ declaration : PARAMETER LPAREN param_assign_list RPAREN newlines """
    p[0] = [ParameterDecl(assignments=p[3], lineno=p.lineno(1))]


def p_param_assign_list_multi(p):
    """ param_assign_list : param_assign_list COMMA ID EQUALS expr """
    p[0] = p[1] + [(p[3], p[5])]

def p_param_assign_list_single(p):
    """ param_assign_list : ID EQUALS expr """
    p[0] = [(p[1], p[3])]

# --- Especificadores de tipo ---

def p_type_spec_integer(p):
    """ type_spec : INTEGER """
    p[0] = 'INTEGER'

def p_type_spec_real(p):
    """ type_spec : REAL """
    p[0] = 'REAL'

def p_type_spec_logical(p):
    """ type_spec : LOGICAL """
    p[0] = 'LOGICAL'

def p_type_spec_character(p):
    """ type_spec : CHARACTER """
    p[0] = 'CHARACTER'

def p_type_spec_complex(p):
    """ type_spec : COMPLEX """
    p[0] = 'COMPLEX'

def p_type_spec_double(p):
    """ type_spec : DOUBLE PRECISION """
    p[0] = 'DOUBLE PRECISION'

# --- Lista de declaradores: X, Y(10), Z ---

def p_declarator_list_multi(p):
    """ declarator_list : declarator_list COMMA declarator """
    p[0] = p[1] + [p[3]]

def p_declarator_list_single(p):
    """ declarator_list : declarator """
    p[0] = [p[1]]

def p_declarator_scalar(p):
    """ declarator : ID """
    p[0] = (p[1], None)  # (nome, dimensões=None) → variável simples

def p_declarator_array(p):
    """ declarator : ID LPAREN dim_list RPAREN """
    p[0] = (p[1], p[3])  # (nome, [dim1, dim2, ...]) → array

# --- Lista de dimensões ---

def p_dim_list_multi(p):
    """ dim_list : dim_list COMMA expr """
    p[0] = p[1] + [p[3]]

def p_dim_list_single(p):
    """ dim_list : expr """
    p[0] = [p[1]]


# ------------------------------------------ Corpo (statements executáveis) ------------------------------------------ #

# Lista plana de statements (incluindo LabeledStmt); DO loops são resolvidos depois
def p_body_multi(p):
    """ body : body statement """
    stmts = p[2]
    p[0] = p[1] + (stmts if isinstance(stmts, list) else [stmts])

def p_body_empty(p):
    """ body : """
    p[0] = []


# ------------------------------------------ Statements ------------------------------------------ #

def p_statement_labeled(p):
    """ statement : INT_LITERAL stmt newlines """
    # Um label (inteiro nas colunas 2-5) precede o statement
    # O label chega como INT_LITERAL porque o pré-processador coloca o número no início da linha lógica
    label = p[1]
    stmt = p[2]
    p[0] = [LabeledStmt(label=label, stmt=stmt, lineno=p.lineno(1))]

def p_statement_unlabeled(p):
    """ statement : stmt newlines """
    p[0] = [p[1]]

def p_statement_newline_only(p):
    """ statement : newlines """
    # Linha em branco entre statements — ignorar
    p[0] = []


# --- Todos os tipos de statement ---

def p_stmt_assignment(p):
    """ stmt : lvalue EQUALS expr """
    p[0] = Assignment(target=p[1], value=p[3], lineno=p.lineno(2))

def p_stmt_if_then(p):
    """ stmt : IF LPAREN expr RPAREN THEN newlines body elseif_clauses else_clause ENDIF """
    p[0] = IfThen(condition=p[3], then_body=p[7], elseif_list=p[8], else_body=p[9], lineno=p.lineno(1))

def p_stmt_logical_if(p):
    """ stmt : IF LPAREN expr RPAREN stmt """
    # IF (cond) stmt  — uma linha, sem THEN
    p[0] = LogicalIf(condition=p[3], stmt=p[5], lineno=p.lineno(1))

def p_stmt_arithmetic_if(p):
    """ stmt : IF LPAREN expr RPAREN INT_LITERAL COMMA INT_LITERAL COMMA INT_LITERAL """
    # IF (expr) l1, l2, l3
    p[0] = ArithmeticIf(expr=p[3], label_neg=p[5], label_zero=p[7], label_pos=p[9], lineno=p.lineno(1))

def p_stmt_do(p):
    """ stmt : DO INT_LITERAL ID EQUALS expr COMMA expr """
    # DO label var = start, end
    p[0] = DoLoop(label=p[2], var=p[3], start=p[5], end=p[7], step=None, body=[], lineno=p.lineno(1))

def p_stmt_do_step(p):
    """ stmt : DO INT_LITERAL ID EQUALS expr COMMA expr COMMA expr """
    # DO label var = start, end, step
    p[0] = DoLoop(label=p[2], var=p[3], start=p[5], end=p[7], step=p[9], body=[], lineno=p.lineno(1))

def p_stmt_continue(p):
    """ stmt : CONTINUE """
    p[0] = Continue(lineno=p.lineno(1))

def p_stmt_goto(p):
    """ stmt : GOTO INT_LITERAL """
    p[0] = Goto(label=p[2], lineno=p.lineno(1))

def p_stmt_call(p):
    """ stmt : CALL ID LPAREN arg_list RPAREN """
    p[0] = Call(name=p[2], args=p[4], lineno=p.lineno(1))

def p_stmt_call_noargs(p):
    """ stmt : CALL ID """
    p[0] = Call(name=p[2], args=[], lineno=p.lineno(1))

def p_stmt_return(p):
    """ stmt : RETURN """
    p[0] = Return(lineno=p.lineno(1))

def p_stmt_return_val(p):
    """ stmt : RETURN expr """
    p[0] = Return(value=p[2], lineno=p.lineno(1))

def p_stmt_stop(p):
    """ stmt : STOP """
    p[0] = Stop(lineno=p.lineno(1))

def p_stmt_stop_code(p):
    """ stmt : STOP INT_LITERAL """
    p[0] = Stop(code=IntLiteral(p[2], p.lineno(2)), lineno=p.lineno(1))

def p_stmt_print_star(p):
    """ stmt : PRINT STAR COMMA io_list """
    p[0] = Print(fmt='*', args=p[4], lineno=p.lineno(1))

def p_stmt_print_star_noargs(p):
    """ stmt : PRINT STAR """
    p[0] = Print(fmt='*', args=[], lineno=p.lineno(1))

def p_stmt_print_fmt(p):
    """ stmt : PRINT INT_LITERAL COMMA io_list """
    p[0] = Print(fmt=p[2], args=p[4], lineno=p.lineno(1))

def p_stmt_read_star(p):
    """ stmt : READ STAR COMMA io_list """
    p[0] = Read(fmt='*', args=p[4], lineno=p.lineno(1))

def p_stmt_read_fmt(p):
    """ stmt : READ INT_LITERAL COMMA io_list """
    p[0] = Read(fmt=p[2], args=p[4], lineno=p.lineno(1))


# --- ELSEIF / ELSE ---

def p_elseif_clauses_multi(p):
    """ elseif_clauses : elseif_clauses ELSEIF LPAREN expr RPAREN THEN newlines body """
    p[0] = p[1] + [(p[4], p[8])]

def p_elseif_clauses_empty(p):
    """ elseif_clauses : """
    p[0] = []

def p_else_clause_present(p):
    """ else_clause : ELSE newlines body """
    p[0] = p[3]

def p_else_clause_absent(p):
    """ else_clause : """
    p[0] = None


# --- lvalue (lado esquerdo da atribuição) ---

def p_lvalue_var(p):
    """ lvalue : ID """
    p[0] = Var(name=p[1], lineno=p.lineno(1))

def p_lvalue_array(p):
    """ lvalue : ID LPAREN arg_list RPAREN """
    p[0] = FuncCall(name=p[1], args=p[3], lineno=p.lineno(1))


# --- Lista de I/O ---

def p_io_list_multi(p):
    """ io_list : io_list COMMA expr """
    p[0] = p[1] + [p[3]]

def p_io_list_single(p):
    """ io_list : expr """
    p[0] = [p[1]]


# --- Lista de argumentos ---

def p_arg_list_multi(p):
    """ arg_list : arg_list COMMA expr """
    p[0] = p[1] + [p[3]]

def p_arg_list_single(p):
    """ arg_list : expr """
    p[0] = [p[1]]

def p_arg_list_empty(p):
    """ arg_list : """
    p[0] = []


# ------------------------------------------ Expressões ------------------------------------------ #

def p_expr_binop_arith(p):
    """ expr : expr PLUS  expr
             | expr MINUS expr
             | expr STAR  expr
             | expr SLASH expr
             | expr DSTAR expr
             | expr DSLASH expr """
    p[0] = BinOp(left=p[1], op=p[2], right=p[3], lineno=p.lineno(2))

def p_expr_binop_relational(p):
    """ expr : expr OP_EQ expr
             | expr OP_NE expr
             | expr OP_LT expr
             | expr OP_LE expr
             | expr OP_GT expr
             | expr OP_GE expr """
    p[0] = BinOp(left=p[1], op=p[2], right=p[3], lineno=p.lineno(2))

def p_expr_binop_logical(p):
    """ expr : expr OP_AND  expr
             | expr OP_OR   expr
             | expr OP_EQV  expr
             | expr OP_NEQV expr """
    p[0] = BinOp(left=p[1], op=p[2], right=p[3], lineno=p.lineno(2))

def p_expr_unary_minus(p):
    """ expr : MINUS expr %prec UMINUS """
    p[0] = UnaryOp(op='-', operand=p[2], lineno=p.lineno(1))

def p_expr_unary_plus(p):
    """ expr : PLUS expr %prec UPLUS """
    # +expr é válido — produz o mesmo valor
    p[0] = p[2]

def p_expr_not(p):
    """ expr : OP_NOT expr """
    p[0] = UnaryOp(op='.NOT.', operand=p[2], lineno=p.lineno(1))

def p_expr_paren(p):
    """ expr : LPAREN expr RPAREN """
    p[0] = p[2]

def p_expr_func_call(p):
    """ expr : ID LPAREN arg_list RPAREN """
    # Pode ser chamada de função OU indexação de array
    p[0] = FuncCall(name=p[1], args=p[3], lineno=p.lineno(1))

def p_expr_var(p):
    """ expr : ID """
    p[0] = Var(name=p[1], lineno=p.lineno(1))

def p_expr_int(p):
    """ expr : INT_LITERAL """
    p[0] = IntLiteral(value=p[1], lineno=p.lineno(1))

def p_expr_real(p):
    """ expr : REAL_LITERAL """
    p[0] = RealLiteral(value=p[1], lineno=p.lineno(1))

def p_expr_str(p):
    """ expr : STR_LITERAL """
    p[0] = StrLiteral(value=p[1], lineno=p.lineno(1))

def p_expr_logical_true(p):
    """ expr : LOGICAL_TRUE """
    p[0] = LogicalLiteral(value=True, lineno=p.lineno(1))

def p_expr_logical_false(p):
    """ expr : LOGICAL_FALSE """
    p[0] = LogicalLiteral(value=False, lineno=p.lineno(1))


# ------------------------------------------ Newlines ------------------------------------------ #

def p_newlines(p):
    """ newlines : NEWLINE
                 | newlines NEWLINE """
    pass   # apenas consumir; sem valor semântico

def p_newlines_opt(p):
    """ newlines_opt : newlines
                     | """
    pass


# ------------------------------------------ Erros Sintáticos ------------------------------------------ #

def p_error(p):
    if p is None:
        print("[PARSER] Erro: fim de ficheiro inesperado", file=sys.stderr)
    else:
        print(
            f"[PARSER] Erro sintático: token inesperado '{p.value}' "
            f"(tipo {p.type}) na linha {p.lineno}",
            file=sys.stderr
        )
        # Recuperação de erro: descartar tokens até ao próximo NEWLINE
        # Isto permite continuar a parsear o resto do ficheiro
        while True:
            tok = parser.token()
            if tok is None or tok.type == 'NEWLINE':
                break
        parser.restart()


# ------------------------------------------ DO Loops ------------------------------------------ #

# Estrutura é (por exemplo):
#   DO 10 I = 1, N
#     stmt1
#     stmt2
#   10 CONTINUE
#
# O parser produz uma lista:
#   [DoLoop(label=10, body=[]), stmt1, stmt2, LabeledStmt(10, Continue)]
#
# resolve_do_loops() transforma isso em:
#   [DoLoop(label=10, body=[stmt1, stmt2])]
#
# Suporta DO loops aninhados corretamente
def resolve_do_loops(unit: Node) -> Node:
    """
    Pós-processamento de uma unidade de programa (Program ou Subprogram):
    agrupa os statements do corpo de cada DO loop.
    """
    if isinstance(unit, Program):
        unit.body = _resolve(unit.body)
    elif isinstance(unit, Subprogram):
        unit.body = _resolve(unit.body)
    return unit


def _resolve(stmts: list) -> list:
    """
    Percorre uma lista plana de statements e agrupa os DO loops.
    Usa uma pilha para gerir DO loops aninhados.

    Algoritmo:
      - Para cada statement:
          - Se for DoLoop: empurrar para a pilha
          - Se for LabeledStmt cujo label coincide com o topo da pilha:
              - Incluir este statement no body do DoLoop
              - Fechar o DoLoop (pop da pilha)
              - Adicionar o DoLoop fechado ao contexto pai
          - Caso contrário: adicionar ao contexto atual
            (topo da pilha, ou lista de resultado se pilha vazia)
    """
    result = []
    stack = []   # lista de (DoLoop, lista_de_statements_acumulados)

    for stmt in stmts:
        # Resolver recursivamente IF-THEN bodies
        stmt = _resolve_if(stmt)

        if isinstance(stmt, DoLoop):
            stack.append((stmt, []))

        elif isinstance(stmt, LabeledStmt) and stack:
            # Verificar se este label fecha algum DO loop da pilha
            # (pode fechar vários se houver DO loops com o mesmo label)
            target_label = stmt.label

            # Adicionar este statement ao contexto atual
            if stack:
                stack[-1][1].append(stmt)

            # Fechar todos os loops cuja label coincide (de dentro para fora)
            while stack and stack[-1][0].label == target_label:
                do_loop, body = stack.pop()
                do_loop.body = body
                # Entregar o DoLoop fechado ao contexto pai (ou resultado)
                if stack:
                    stack[-1][1].append(do_loop)
                else:
                    result.append(do_loop)

        else:
            # Statement normal: adicionar ao contexto atual
            if stack:
                stack[-1][1].append(stmt)
            else:
                result.append(stmt)

    # DO loops não fechados (label nunca encontrado) — erro semântico futuro
    for do_loop, body in stack:
        print(
            f"[PARSER] Aviso: DO loop com label {do_loop.label} nunca fechado "
            f"(linha {do_loop.lineno})",
            file=sys.stderr
        )
        do_loop.body = body
        result.append(do_loop)

    return result


def _resolve_if(stmt: Node) -> Node:
    """ Resolve recursivamente DO loops dentro de blocos IF. """
    if isinstance(stmt, LabeledStmt):
        stmt.stmt = _resolve_if(stmt.stmt)
    elif isinstance(stmt, IfThen):
        stmt.then_body = _resolve(stmt.then_body)
        stmt.elseif_list = [(c, _resolve(b)) for c, b in stmt.elseif_list]
        if stmt.else_body is not None:
            stmt.else_body = _resolve(stmt.else_body)
    elif isinstance(stmt, LogicalIf):
        stmt.stmt = _resolve_if(stmt.stmt)
    return stmt


# ------------------------------------------ Parser ------------------------------------------ #

parser = yacc.yacc(debug=False, write_tables=False)

def parse(source: str, filename: str = '<stdin>') -> ProgramFile:
    """
    Recebe código Fortran e devolve a AST (ProgramFile).

    Pipeline:
      1. Pré-processamento
      2. Tokenização (lexer)
      3. Parsing → AST
      4. Resolução de DO loops (pós-processamento)
    """
    from lexer import lexer as base_lexer, preprocess_fixed_form, join_logical_lines

    logical_lines = preprocess_fixed_form(source)
    if not logical_lines:
        return ProgramFile(units=[], lineno=0)

    combined = join_logical_lines(logical_lines)
    lx = base_lexer.clone()
    lx.lineno = 1

    result = parser.parse(combined, lexer=lx, tracking=True)
    return result if result is not None else ProgramFile(units=[], lineno=0)


def parse_file(path: str) -> ProgramFile:
    """ Lê um ficheiro Fortran 77 e devolve a AST """
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        source = f.read()
    return parse(source, filename=path)