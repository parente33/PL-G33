# Cada tipo de nó tem a sua própria classe -- melhor para debugging
# Cada nó tem accept(visitor) que chama visitor.visit_NomeDoNo(self). As fases seguintes podem implementar um Visitor sem tocar nas classes da ast
# Todos os nós têm um campo lineno
# Hierarquia:
'''
Node                                (base abstrata)
|-- Program                         (programa principal)
|-- Subprogram                      (FUNCTION ou SUBROUTINE)
|-- declarations                    (INTEGER X, Y / REAL A(10))
|   |-- VarDecl
|   |-- ArrayDecl
|-- statements                      (corpo executável)
|   |-- Assignment                  (X = expr)
|   |-- IfThen                      (IF ... THEN / ELSEIF / ELSE / ENDIF)
|   |-- ArithmeticIf                (IF (expr) l1, l2, l3)
|   |-- DoLoop                      (DO label var = start, end [, step])
|   |-- Continue                    (CONTINUE)
|   |-- Goto                        (GOTO label)
|   |-- Call                        (CALL sub(args))
|   |-- Return                      (RETURN)
|   |-- Stop                        (STOP)
|   |-- Print                       (PRINT *, ...)
|   |-- Read                        (READ *, ...)
|   |-- LabeledStmt                 (wrapper: label + statement)
    |-- expressions
        |-- BinOp                   (a + b, a .AND. b, a .EQ. b)
        |-- UnaryOp                 (- a, .NOT. a)
        |-- FuncCall                (F(args)) -- também cobre array indexing
        |-- Var                     (nome da variável)
        |-- IntLiteral
        |-- RealLiteral
        |-- StrLiteral
        |-- LogicalLiteral
'''

from __future__ import annotations
from typing import Optional

# ------------------------------------------ Base ------------------------------------------ #

class Node:
    """ Nó base da AST. Todos os outros nós herdam daqui """
    def __init__(self, lineno: int = 0):
        self.lineno = lineno

    def accept(self, visitor):
        """
        Visitor: despacha para visitor.visit_<ClassName>(self)
        Se o visitor não tiver o método especificado, tenta visit_generic
        """
        method_name = f'visit_{type(self).__name__}'
        method = getattr(visitor, method_name, None)
        if method is None:
            method = getattr(visitor, 'visit_generic', self._default_visit)
        return method(self)

    def _default_visit(self, node=None):
        raise NotImplementedError(
            f"Visitor não implementa visit_{type(self).__name__}"
        )

    def __repr__(self):
        # Representação genérica: Nome(campo=valor, ...)
        attrs = {k: v for k, v in self.__dict__.items() if k != 'lineno'}
        inner = ', '.join(f'{k}={v!r}' for k, v in attrs.items())
        return f'{type(self).__name__}({inner})[L{self.lineno}]'


# ------------------------------------------ Estrutura do ficheiro ------------------------------------------ #

class ProgramFile(Node):
    """
    Raiz da AST. Representa um ficheiro fonte completo
    No nosso caso, pode conter um programa principal e zero ou mais subprogramas

    Campos:
        units: list[Program | Subprogram]
    """
    def __init__(self, units: list, lineno: int = 0):
        super().__init__(lineno)
        self.units = units


class Program(Node):
    """
    PROGRAM nome
        [declarations]
        [statemens]
    END

    Campos:
        name:           str                                 (nome após PROGRAM, ou None se for omitido)
        declarations:   list[VarDecl | ArrayDecl | ...]
        body:           list[stmt]
    """
    def __init__(self, name: Optional[str], declarations: list, body: list, lineno: int = 0):
        super().__init__(lineno)
        self.name = name
        self.declarations = declarations
        self.body = body


class Subprogram(Node):
    """
    INTEGER FUNCTION nome(params)   ou  SUBROUTINE nome(params)
        [declarations]
        [statements]
    END

    Campos:
        kind:           str         ('FUNCTION' ou 'SUBROUTINE')
        return_type:    str | None  (só para FUNCTION)
        name:           str
        params:         list[str]   (nome dos parâmtros formais)
        declarations:   list
        body:           list[stmt]
    """
    def __init__(self, kind: str, return_type: Optional[str], name: str, params: list, declarations: list, body: list, lineno: int = 0):
        super().__init__(lineno)
        self.kind = kind
        self.return_type = return_type
        self.name = name
        self.params = params
        self.declarations = declarations
        self.body = body


# ------------------------------------------ Declarações ------------------------------------------ #

class VarDecl(Node):
    """
    INTEGER X, Y, Z
    REAL A, B

    Campos:
        type_name:      str         ('INTEGER', 'REAL', 'LOGICAL', etc.)
        names:          list[str]   (lista de nomes declarados)
    """
    def __init__(self, type_name: str, names: list, lineno: int = 0):
        super().__init__(lineno)
        self.type_name = type_name
        self.names = names


class ArrayDecl(Node):
    """
    INTEGER NUMS(5)
    REAL MAT(3, 3)

    Campos:
        type_name:      str
        name:           str
        dimensions:     list[expr]      (expressões que definem cada dimensão)
    """
    def __init__(self, type_name: str, name: str, dimensions: list, lineno: int = 0):
        super().__init__(lineno)
        self.type_name = type_name
        self.name = name
        self.dimensions = dimensions


class ImplicitNone(Node):
    """ IMPLICIT None - desativa o typing implícito da linguagem """
    pass


class ParameterDecl(Node):
    """
    PARAMETER (PI = 3.14159, E = 2.71828)

    Campos:
        assignments: list[(str, expr)]
    """
    def __init__(self, assignments: list, lineno: int = 0):
        super().__init__(lineno)
        self.assignments = assignments  # [(nome, expr), ...]


# ------------------------------------------ Statements ------------------------------------------ #

class LabeledStmt(Node):
    """
    Wrapper para uma instrução que tem um label numérico.

    10 CONTINUE
    20 IF (...)

    Campos:
      label:    int
      stmt:     Node (qualquer statement)
    """
    def __init__(self, label: int, stmt: Node, lineno: int = 0):
        super().__init__(lineno)
        self.label = label
        self.stmt = stmt


class Assignment(Node):
    """
    X = expr
    NUMS(I) = expr   (indexação de array no lado esquerdo)

    Campos:
      target : Var | FuncCall   (FuncCall representa A(I) no lado esquerdo)
      value  : expr
    """
    def __init__(self, target: Node, value: Node, lineno: int = 0):
        super().__init__(lineno)
        self.target = target
        self.value = value


class IfThen(Node):
    """
    IF (cond) THEN
      ...
    ELSEIF (cond) THEN
      ...
    ELSE
      ...
    ENDIF

    Campos:
      condition   : expr
      then_body   : list[stmt]
      elseif_list : list[(expr, list[stmt])]   (pares condição/corpo)
      else_body   : list[stmt] | None
    """
    def __init__(self, condition: Node,
                 then_body: list,
                 elseif_list: list,
                 else_body: Optional[list],
                 lineno: int = 0):
        super().__init__(lineno)
        self.condition = condition
        self.then_body = then_body
        self.elseif_list = elseif_list   # [(cond, body), ...]
        self.else_body = else_body


class ArithmeticIf(Node):
    """
    IF (expr) label1, label2, label3
    Salta para label1 se expr<0, label2 se expr=0, label3 se expr>0.
    """
    def __init__(self, expr: Node,
                 label_neg: int, label_zero: int, label_pos: int,
                 lineno: int = 0):
        super().__init__(lineno)
        self.expr = expr
        self.label_neg = label_neg
        self.label_zero = label_zero
        self.label_pos = label_pos


class LogicalIf(Node):
    """
    IF (cond) stmt    — forma de uma linha (sem THEN)
    Executa stmt apenas se cond for verdadeiro.

    Campos:
      condition : expr
      stmt      : Node (qualquer statement simples)
    """
    def __init__(self, condition: Node, stmt: Node, lineno: int = 0):
        super().__init__(lineno)
        self.condition = condition
        self.stmt = stmt


class DoLoop(Node):
    """
    DO label var = start, end [, step]
      body
    label CONTINUE

    Campos:
      label    : int
      var      : str          (variável de controlo)
      start    : expr
      end      : expr
      step     : expr | None  (default = 1)
      body     : list[stmt]   (preenchido pelo parser após recolha)
    """
    def __init__(self, label: int, var: str,
                 start: Node, end: Node, step: Optional[Node],
                 body: list,
                 lineno: int = 0):
        super().__init__(lineno)
        self.label = label
        self.var = var
        self.start = start
        self.end = end
        self.step = step
        self.body = body


class Continue(Node):
    """ CONTINUE — instrução nula, usada como alvo de DO loops. """
    pass


class Goto(Node):
    """
    GOTO label

    Campos:
      label : int
    """
    def __init__(self, label: int, lineno: int = 0):
        super().__init__(lineno)
        self.label = label


class Call(Node):
    """
    CALL sub(args)

    Campos:
      name : str
      args : list[expr]
    """
    def __init__(self, name: str, args: list, lineno: int = 0):
        super().__init__(lineno)
        self.name = name
        self.args = args


class Return(Node):
    """ RETURN [expr]  (expr só em FUNCTION) """
    def __init__(self, value: Optional[Node] = None, lineno: int = 0):
        super().__init__(lineno)
        self.value = value


class Stop(Node):
    """ STOP [código] """
    def __init__(self, code: Optional[Node] = None, lineno: int = 0):
        super().__init__(lineno)
        self.code = code


class Print(Node):
    """
    PRINT *, expr, expr, ...
    PRINT fmt, expr, ...

    Campos:
      fmt  : str | expr   ('*' para format livre, ou expressão de formato)
      args : list[expr]
    """
    def __init__(self, fmt, args: list, lineno: int = 0):
        super().__init__(lineno)
        self.fmt = fmt
        self.args = args


class Read(Node):
    """
    READ *, var, var, ...
    READ (unit, fmt) var, ...

    Campos:
      fmt  : str | expr
      args : list[expr]   (variáveis a ler — lvalues)
    """
    def __init__(self, fmt, args: list, lineno: int = 0):
        super().__init__(lineno)
        self.fmt = fmt
        self.args = args


# ------------------------------------------ Expressões ------------------------------------------ #

class BinOp(Node):
    """
    Operação binária: left op right

    op pode ser: '+', '-', '*', '/', '**', '//',
                 '.EQ.', '.NE.', '.LT.', '.LE.', '.GT.', '.GE.',
                 '.AND.', '.OR.', '.EQV.', '.NEQV.'

    Campos:
      left  : expr
      op    : str
      right : expr
    """
    def __init__(self, left: Node, op: str, right: Node, lineno: int = 0):
        super().__init__(lineno)
        self.left = left
        self.op = op
        self.right = right


class UnaryOp(Node):
    """
    Operação unária: op operand

    op: '-' (negação aritmética) ou '.NOT.' (negação lógica)
    """
    def __init__(self, op: str, operand: Node, lineno: int = 0):
        super().__init__(lineno)
        self.op = op
        self.operand = operand


class FuncCall(Node):
    """
    Chamada de função ou indexação de array: nome(args)

    A sintaxe é igual para ambos os casos; a distinção é feita na análise semântica (olhando para a tabela de símbolos).

    Campos:
      name : str
      args : list[expr]
    """
    def __init__(self, name: str, args: list, lineno: int = 0):
        super().__init__(lineno)
        self.name = name
        self.args = args


class Var(Node):
    """
    Referência a uma variável simples.

    Campos:
      name : str
    """
    def __init__(self, name: str, lineno: int = 0):
        super().__init__(lineno)
        self.name = name


class IntLiteral(Node):
    """
    Literal inteiro.

    Campos:
      value : int
    """
    def __init__(self, value: int, lineno: int = 0):
        super().__init__(lineno)
        self.value = value


class RealLiteral(Node):
    """
    Literal real (ponto flutuante).

    Campos:
      value : float
    """
    def __init__(self, value: float, lineno: int = 0):
        super().__init__(lineno)
        self.value = value


class StrLiteral(Node):
    """
    Literal de string.

    Campos:
      value : str
    """
    def __init__(self, value: str, lineno: int = 0):
        super().__init__(lineno)
        self.value = value


class LogicalLiteral(Node):
    """
    Literal lógico: .TRUE. ou .FALSE.

    Campos:
      value : bool
    """
    def __init__(self, value: bool, lineno: int = 0):
        super().__init__(lineno)
        self.value = value


# ------------------------------------------ Utils (pretty printer para debugging) ------------------------------------------ #

def pretty_print(node: Node, indent: int = 0, file=None) -> None:
    """
    Imprime a AST de forma indentada e legível.

    Exemplo de output:
      ProgramFile
        Program 'HELLO' [L1]
          Print fmt='*' [L2]
            StrLiteral 'Ola, Mundo!'
    """
    import sys
    if file is None:
        file = sys.stdout

    prefix = '  ' * indent

    if node is None:
        print(f"{prefix}None", file=file)
        return

    if isinstance(node, list):
        for item in node:
            pretty_print(item, indent, file)
        return

    # Linha de cabeçalho do nó
    name = type(node).__name__
    line_info = f" [L{node.lineno}]" if node.lineno else ""

    # Campos simples (não-Node) resumidos na mesma linha
    simple = {}
    complex_fields = {}
    for k, v in node.__dict__.items():
        if k == 'lineno':
            continue
        if isinstance(v, Node):
            complex_fields[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], Node):
            complex_fields[k] = v
        elif isinstance(v, list) and v and isinstance(v[0], tuple):
            complex_fields[k] = v   # elseif_list, etc.
        else:
            simple[k] = v

    simple_str = '  '.join(f'{k}={v!r}' for k, v in simple.items())
    print(f"{prefix}{name}{line_info}  {simple_str}", file=file)

    # Campos complexos (sub-árvores) indentados
    for k, v in complex_fields.items():
        print(f"{prefix}  [{k}]", file=file)
        if isinstance(v, list):
            for item in v:
                if isinstance(item, tuple):
                    # elseif_list: (cond, body)
                    cond, body = item
                    print(f"{prefix}    (elseif)", file=file)
                    pretty_print(cond, indent + 3, file)
                    for s in body:
                        pretty_print(s, indent + 3, file)
                else:
                    pretty_print(item, indent + 2, file)
        else:
            pretty_print(v, indent + 2, file)