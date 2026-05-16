from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# Tipos suportados
NUMERIC_TYPES = { 'INTEGER', 'REAL', 'DOUBLE PRECISION', 'COMPLEX' }
LOGICAL_TYPES = { 'LOGICAL' }
STRING_TYPES = { 'CHARACTER' }
ALL_TYPES = NUMERIC_TYPES | LOGICAL_TYPES | STRING_TYPES

# Tipos que podem ser coercidos entre si (widening implícito)
NUMERIC_RANK = { 'INTEGER': 1, 'REAL': 2, 'DOUBLE PRECISION': 3, 'COMPLEX': 4 }

def wider_type(t1: str, t2: str) -> str:
    """ Devolve o tipo mais 'largo' de dois tipos numéricos """
    r1 = NUMERIC_RANK.get(t1, 0)
    r2 = NUMERIC_RANK.get(t2, 0)
    return t1 if r1 >= r2 else t2

def implicit_type(name: str) -> str:
    """ Implicit typing: nomes que começam por I, J, K, L, M, N -> INTEGER; todos os outros -> REAL """
    return 'INTEGER' if name[0].upper() in 'IJKLMN' else 'REAL'


# ------------------------------------- Funções livres partilhadas ------------------------------------- #
# Estas funções são usadas tanto pelo SemanticAnalyzer como pelo CodeGenerator.

def infer_type(node, local_table: Optional['SymbolTable'], global_table: Optional['SymbolTable'], intrinsics: dict) -> Optional[str]:
    """
    Inferência de tipo pura.

    Devolve o tipo Fortran de uma expressão AST, consultando as tabelas de símbolos fornecidas. Não regista erros, nem cria símbolos implícitos.
    Devolve None se o tipo não for determinável.

    Usada pelo SemanticAnalyzer (que depois acrescenta validação por cima) e pelo CodeGenerator (que só precisa do tipo, sem diagnósticos).
    """
    # Importação local para evitar dependência circular ao nível do módulo.
    # ast_nodes não importa symbol_table, portanto é seguro.
    from ast_nodes import ( IntLiteral, RealLiteral, StrLiteral, LogicalLiteral, Var, FuncCall, UnaryOp, BinOp, )

    if isinstance(node, IntLiteral):      return 'INTEGER'
    if isinstance(node, RealLiteral):     return 'REAL'
    if isinstance(node, StrLiteral):      return 'CHARACTER'
    if isinstance(node, LogicalLiteral):  return 'LOGICAL'

    if isinstance(node, Var):
        if local_table is None:
            return None
        sym = local_table.lookup(node.name)
        return sym.type if sym else None

    if isinstance(node, FuncCall):
        name = node.name
        # Intrínsecas
        if name in intrinsics:
            ret, _ = intrinsics[name]
            if ret == '*':
                # Polimórfico: tipo == tipo do primeiro argumento
                arg_types = [infer_type(a, local_table, global_table, intrinsics)
                             for a in node.args]
                return arg_types[0] if arg_types else 'INTEGER'
            return ret
        # Símbolo local (array indexing ou variável de retorno de função)
        if local_table:
            sym = local_table.lookup(name)
            if sym is not None:
                return sym.type
        # Subprograma global
        if global_table:
            gsym = global_table.lookup(name)
            if gsym is not None:
                return gsym.type
        return None

    if isinstance(node, UnaryOp):
        if node.op == '.NOT.': return 'LOGICAL'
        return infer_type(node.operand, local_table, global_table, intrinsics)

    if isinstance(node, BinOp):
        op = node.op
        if op in ('.AND.', '.OR.', '.EQV.', '.NEQV.', '.EQ.', '.NE.', '.LT.', '.LE.', '.GT.', '.GE.'):
            return 'LOGICAL'
        if op == '//':
            return 'CHARACTER'
        lt = infer_type(node.left,  local_table, global_table, intrinsics)
        rt = infer_type(node.right, local_table, global_table, intrinsics)
        if lt in ('REAL', 'DOUBLE PRECISION') or rt in ('REAL', 'DOUBLE PRECISION'):
            return 'REAL'
        return lt or rt

    return None


def eval_const(node, local_table: Optional['SymbolTable']) -> Optional[int | float]:
    """
    Avaliação de uma expressão constante em compile-time.

    Tenta calcular o valor de uma expressão aritmética pura (literais e constantes PARAMETER) em tempo de compilação. Devolve:
      - int     se o resultado for inteiro (preserva a distinção int/float)
      - float   se o resultado for real
      - None    se a expressão contiver variáveis não-PARAMETER ou não for aritmética

    Usada pelo SemanticAnalyzer (verificação de dimensões de arrays, PARAMETERs) e pelo CodeGenerator (constant folding, índices de arrays, step de DO).
    """
    from ast_nodes import IntLiteral, RealLiteral, LogicalLiteral, Var, UnaryOp, BinOp

    if isinstance(node, IntLiteral):
        return node.value                       # int
    if isinstance(node, RealLiteral):
        return node.value                       # float
    if isinstance(node, LogicalLiteral):
        return int(node.value)                  # .TRUE.=1, .FALSE.=0

    if isinstance(node, UnaryOp) and node.op == '-':
        v = eval_const(node.operand, local_table)
        return -v if v is not None else None

    if isinstance(node, Var) and local_table is not None:
        sym = local_table.lookup(node.name)
        if sym is not None and sym.kind == 'parameter' and sym.value is not None:
            # Preservar o tipo do PARAMETER: INTEGER → int, REAL → float
            return int(sym.value) if sym.type == 'INTEGER' else sym.value

    if isinstance(node, BinOp):
        op = node.op
        if op not in ('+', '-', '*', '/', '**'):
            return None   # operadores relacionais/lógicos não são constantes aritméticas
        lv = eval_const(node.left,  local_table)
        rv = eval_const(node.right, local_table)
        if lv is None or rv is None:
            return None
        if op == '+':  return lv + rv
        if op == '-':  return lv - rv
        if op == '*':  return lv * rv
        if op == '/':
            if rv == 0: return None
            # Divisão inteira se ambos os operandos forem int
            return lv // rv if (isinstance(lv, int) and isinstance(rv, int)) else lv / rv
        if op == '**':
            return lv ** rv

    return None


@dataclass
class Symbol:
    """
    Entrada na tabela de símbolos.

    Campos:
        name:            nome do símbolo (sempre em maiúsculas)
        kind:           'variable' | 'array' | 'function' | 'subroutine' | 'parameter'
        type:           'INTEGER' | 'REAL' | 'LOGICAL' | 'CHARACTER' | 'DOUBLE PRECISION' | 'COMPLEX' | None (subroutines)
        shape:          lista de inteiros com o tamanho de cada dimensão, ou []
        param_types:    lista de tipos dos parâmetros (só para function/subroutine)
        param_index:    índice na lista de parâmetros formais, ou -1
        offset:         posição na frame de memória da VM (preenchido só pelo codegen)
        lineno:         linha onde foi declarado
        is_param:       True se for parâmetro formal do subprograma
    """
    name:           str
    kind:           str
    type:           Optional[str]
    value:          Optional[object] = None
    shape:          list = field(default_factory=list)
    param_types:    list = field(default_factory=list)
    param_index:    int = -1
    offset:         int = 0
    lineno:         int = 0
    is_param:       bool = False

    def is_array(self) -> bool:
        return self.kind == 'array' or len(self.shape) > 0

    def is_callable(self) -> bool:
        return self.kind in ('function', 'subroutine')

    def __repr__(self):
        shape_str = f"[{','.join(str(d) for d in self.shape)}]" if self.shape else ""
        return (f"Symbol({self.name}{shape_str} : {self.kind} type={self.type} offset={self.offset})")


class SymbolTable:
    """
    Tabela de símbolos para um único âmbito (programa ou subprograma)

    Cada PROGRAM / SUBROUTINE / FUNCTION tem a sua própria SymbolTable.
    A tabela global é mantida pelo SemanticAnalyzer
    """
    def __init__(self, scope_name: str, implicit_none: bool = False):
        self.scope_name = scope_name
        self.implicit_none = implicit_none
        self._symbols: dict[str, Symbol] = {}

    # Inserção
    def declare(self, symbol: Symbol) -> Optional[Symbol]:
        """ Regista um novo símbolo. Devolve o símbolo anterior se já existia (para erro de redeclaração), ou None se foi bem sucedida """
        existing = self._symbols.get(symbol.name)
        if existing is not None:
            return existing # quem chama é que decide o que se faz
        self._symbols[symbol.name] = symbol
        return None

    # Consulta
    def lookup(self, name: str) -> Optional[Symbol]:
        """ Procura um símbolo pelo nome. Devolve None se não existir """
        return self._symbols.get(name.upper())

    def lookup_or_implicit(self, name: str, lineno: int = 0) -> Symbol:
        """
        Procura um símbolo. Se não existir e implicit_none=False, cria automaticamente um símbolo com o tipo implícito (I-N -> INTEGER, resto -> REAL)
        Se implicit_none=True e o símbolo não existe, lança KeyError (o SemanticAnalyzer transforma em erro)
        """
        sym = self.lookup(name)
        if sym is not None:
            return sym
        if self.implicit_none:
            raise KeyError(name)
        # Criar entrada implícita
        itype = implicit_type(name)
        sym = Symbol(name=name, kind='variable', type=itype, lineno=lineno)
        self._symbols[name.upper()] = sym
        return sym

    # Iteração e debug
    def all_symbols(self) -> list[Symbol]:
        return list(self._symbols.values())

    def variables(self) -> list[Symbol]:
        return [s for s in self._symbols.values()
                if s.kind in ('variable', 'array')]

    def __repr__(self):
        lines = [f"SymbolTable({self.scope_name!r}):"]
        for sym in self._symbols.values():
            lines.append(f"  {sym}")
        return '\n'.join(lines)