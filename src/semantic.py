# Fase 3 - Análise semântica

from __future__ import annotations
import sys
from typing import Optional

from ast_nodes import (
    Node, ProgramFile, Program, Subprogram, VarDecl, ArrayDecl, ImplicitNone, ParameterDecl, LabeledStmt,
    Assignment, IfThen, ArithmeticIf, LogicalIf, DoLoop, Continue, Goto, Call, Return, Stop,
    Print, Read, BinOp, UnaryOp, FuncCall, Var, IntLiteral, RealLiteral, StrLiteral, LogicalLiteral
)
from symbol_table import SymbolTable, Symbol, wider_type, implicit_type, NUMERIC_TYPES, infer_type, eval_const


# Funções intrínsecas; mapeamento: nome -> (tipo_retorno, [tipos_argumentos]) ('*' significa "qualquer tipo númerico", polimórfico)
INTRINSICS: dict[str, tuple] = {
    # Matemáticas
    'ABS':      ('*', ['*']),
    'SQRT':     ('REAL', ['*']),
    'EXP':      ('REAL', ['*']),
    'LOG':      ('REAL', ['*']),
    'LOG10':    ('REAL', ['*']),
    'SIN':      ('REAL', ['*']),
    'COS':      ('REAL', ['*']),
    'TAN':      ('REAL', ['*']),
    'ASIN':     ('REAL', ['*']),
    'ACOS':     ('REAL', ['*']),
    'ATAN':     ('REAL', ['*']),
    'ATAN2':    ('REAL', ['*', '*']),

    # Conversão
    'INT':      ('INTEGER', ['*']),
    'REAL':     ('REAL', ['*']),
    'DBLE':     ('DOUBLE PRECISION', ['*']),
    'IFIX':     ('INTEGER', ['REAL']),
    'FLOAT':    ('REAL', ['INTEGER']),

    # Inteiras
    'MOD':      ('INTEGER', ['INTEGER', 'INTEGER']),
    'MAX':      ('*', ['*', '*']),
    'MIN':      ('*', ['*', '*']),
    'MAX0':     ('INTEGER', ['INTEGER', 'INTEGER']),
    'MIN0':     ('INTEGER', ['INTEGER', 'INTEGER']),
    'AMAX1':    ('REAL', ['REAL', 'REAL']),
    'AMIN1':    ('REAL', ['REAL', 'REAL']),

    # String
    'LEN':      ('INTEGER', ['CHARACTER']),
    'INDEX':    ('INTEGER', ['CHARACTER', 'CHARACTER']),

    # Lógicas
    'LGE':      ('LOGICAL', ['CHARACTER', 'CHARACTER']),
    'LGT':      ('LOGICAL', ['CHARACTER', 'CHARACTER']),
    'LLE':      ('LOGICAL', ['CHARACTER', 'CHARACTER']),
    'LLT':      ('LOGICAL', ['CHARACTER', 'CHARACTER']),
}


class Diagnostic:
    """ Representa um erro ou aviso semântico """
    def __init__(self, level: str, message: str, lineno: int):
        self.level = level # 'ERROR' ou 'WARNING'
        self.message = message
        self.lineno = lineno

    def __str__(self):
        return f"[SEMANTIC] {self.level} (linha {self.lineno}): {self.message}"


class SemanticAnalyzer:
    """
    Percorre a AST e verifica a coerência semântica do programa.
    Após chamar analyze(), consulta self.errors e self.warnings
    """
    def __init__(self):
        self.diagnostics: list[Diagnostic] = []

        # Tabela global: nomes de subrpogramas (visíveis em todo o ficheiro)
        self.global_table = SymbolTable(scope_name='__global__')

        # Tabela local do âmbito atual (muda a cada unidade de programa)
        self.current_table: Optional[SymbolTable] = None

        # Nome da unidade atual (para mensagens)
        self.current_unit: str = ''

        # Labels definidos no àmbito atual: {label: nó}
        self.defined_labels: dict[int, Node] = {}

        # Labels referenciados por GOTO no âmbito atual
        self.goto_labels: list[tuple[int, int]] = [] # [(label, lineno)]

        # Labels de DO ativos (para verificar que têm CONTINUE)
        self.do_labels: set[int] = set()

        # Estamos dentro de um subprograma? (para validar RETURN)
        self.in_subprogram: bool = False

        # Tabelas locais de cada unidade, guardadas para consulta posterior (codegen precisa para alocar frames)
        # chave: nome da unidade de programa
        self.local_tables: dict[str, SymbolTable] = {}

        # Chamadas a subprogramas definidos no mesmo ficheiro, registadas durante a Passagem 1
        # para re-verificação na Passagem 2 (quando param_types já está preenchido).
        # Cada entrada: (name, args, lineno)
        self._pending_calls: list[tuple[str, list, int]] = []

    # --------------------------------------------------------------------------------------- #

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == 'ERROR']

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == 'WARNING']

    def error(self, msg: str, lineno: int):
        self.diagnostics.append(Diagnostic('ERROR', msg, lineno))

    def warning(self, msg: str, lineno: int):
        self.diagnostics.append(Diagnostic('WARNING', msg, lineno))

    # --------------------------------------------------------------------------------------- #

    def analyze(self, tree: ProgramFile):
        """ Analisa a AST completa. Modifica self.diagnostics """
        # Passagem 0: registar todos os subprogramas na tabela global antes de analisar qualquer unidade (permite chamadas forward)
        for unit in tree.units:
            if isinstance(unit, Subprogram):
                self._register_subprogram_global(unit)

        # Passagem principal (1): analisar cada unidade
        # Durante esta passagem, chamadas a subprogramas do mesmo ficheiro são acumuladas em _pending_calls porque param_types ainda pode estar vazio
        # (o subprograma chamado pode ainda não ter sido analisado).
        for unit in tree.units:
            self._analyze_unit(unit)

        # Passagem 2: re-verificar o nº de argumentos de todas as chamadas pendentes.
        # Neste ponto todos os subprogramas já foram analisados e param_types está completo.
        self._check_pending_calls()


    def _register_subprogram_global(self, unit: Subprogram):
        """ Regista um subprograma na tabela global """
        kind = 'function' if unit.kind == 'FUNCTION' else 'subroutine'
        sym = Symbol(
            name = unit.name,
            kind = kind,
            type = unit.return_type,
            param_types = [], # só é preenchido na passagem 1
            lineno = unit.lineno,
        )
        prev = self.global_table.declare(sym)
        if prev is not None:
            self.error(f"subprograma '{unit.name}' definido mais do que uma vez", unit.lineno)

    # --------------------------------------------------------------------------------------- #

    def _analyze_unit(self, unit: Node):
        if isinstance(unit, Program):
            self._analyze_program(unit)
        elif isinstance(unit, Subprogram):
            self._analyze_subprogram(unit)


    def _analyze_program(self, node: Program):
        self.current_unit = node.name or '<programa>'
        self.in_subprogram = False
        self.current_table = SymbolTable(self.current_unit)
        self.defined_labels = {}
        self.goto_labels = []
        self.do_labels = set()

        # Passagem 1: declarações
        for decl in node.declarations:
            self._visit_decl(decl)

        # Passagem 2: body
        self._collect_labels(node.body)
        for stmt in node.body:
            self._visit_stmt(stmt)

        # Verificações pós-body
        self._check_goto_labels()

        # Guardar tabela local para uso posterior
        self.local_tables[self.current_unit] = self.current_table


    def _analyze_subprogram(self, node: Subprogram):
        self.current_unit = node.name
        self.in_subprogram = True
        self.current_table = SymbolTable(node.name)
        self.defined_labels = {}
        self.goto_labels = []
        self.do_labels = set()

        # Registar parâmetros formais como variáveis na tabela local
        for idx, param_name in enumerate(node.params):
            sym = Symbol(
                name = param_name,
                kind = 'variable',
                type = None, # Determinado pelas declarações
                param_index = idx,
                is_param = True,
                lineno = node.lineno,
            )
            self.current_table.declare(sym)

        # Registar o nome da função como variável local (FUNCTION retorna atribuindo ao próprio nome: CONVRT = VAL)
        if node.kind == 'FUNCTION':
            ret_sym = Symbol(
                name = node.name,
                kind = 'variable',
                type = node.return_type,
                lineno = node.lineno,
            )
            self.current_table.declare(ret_sym)

        # Passagem 1: declarações
        for decl in node.declarations:
            self._visit_decl(decl)

        # Atualizar tipos dos parâmetros na tabela global
        global_sym = self.global_table.lookup(node.name)
        if global_sym is not None:
            global_sym.param_types = [
                self.current_table.lookup(p).type
                for p in node.params
                if self.current_table.lookup(p) is not None
            ]

        # Passagem 2: body
        self._collect_labels(node.body)
        for stmt in node.body:
            self._visit_stmt(stmt)
        self._check_goto_labels()

        # Guardar tabela local para uso posterior
        self.local_tables[node.name] = self.current_table


    # Recolha de labels - Percorre a lista de statements e regista todos os labels definidos
    # Necessário para que GOTO possa referenciar labels definidos mais à frente
    def _collect_labels(self, stmts: list):
        for stmt in stmts:
            self._collect_labels_stmt(stmt)


    def _collect_labels_stmt(self, stmt: Node):
        if isinstance(stmt, LabeledStmt):
            if stmt.label in self.defined_labels:
                self.error(f"label {stmt.label} definido mais do que uma vez", stmt.lineno)
            else:
                self.defined_labels[stmt.label] = stmt
            self._collect_labels_stmt(stmt.stmt)
        elif isinstance(stmt, DoLoop):
            self.do_labels.add(stmt.label)
            self._collect_labels(stmt.body)
        elif isinstance(stmt, IfThen):
            self._collect_labels(stmt.then_body)
            for _, body in stmt.elseif_list:
                self._collect_labels(body)
            if stmt.else_body:
                self._collect_labels(stmt.else_body)

    # -------------------------------------- Declarações --------------------------------------- #

    def _visit_decl(self, decl: Node):
        if isinstance(decl, VarDecl):
            self._visit_var_decl(decl)
        elif isinstance(decl, ArrayDecl):
            self._visit_array_decl(decl)
        elif isinstance(decl, ImplicitNone):
            self.current_table.implicit_none = True
        elif isinstance(decl, ParameterDecl):
            self._visit_parameter_decl(decl)


    def _visit_var_decl(self, decl: VarDecl):
        for name in decl.names:
            existing = self.current_table.lookup(name)
            if existing is not None and existing.type is not None:
                # Já tem definido e não é apenas um parâmetro sem tipo
                if not existing.is_param:
                    self.error(f"variável '{name}' declarada mais do que uma vez", decl.lineno)
                    continue
            if existing is not None and existing.is_param:
                existing.type = decl.type_name
            else:
                sym = Symbol(
                    name = name,
                    kind = 'variable',
                    type = decl.type_name,
                    lineno = decl.lineno,
                )
                self.current_table.declare(sym)


    def _visit_array_decl(self, decl: ArrayDecl):
        if self.current_table.lookup(decl.name) is not None:
            self.error(f"'{decl.name}' declarado mais do que uma vez", decl.lineno)
            return
        # Avaliar dimensões (devem ser constantes inteiras)
        shape = []
        for dim_expr in decl.dimensions:
            val = self._eval_const(dim_expr)
            if val is not None:
                if val != int(val):
                    self.error(f"dimensão de '{decl.name}' deve ser inteira, encontrado {val}", decl.lineno)
                    shape.append(0)
                elif int(val) <= 0:
                    self.error(f"dimensão de '{decl.name}' deve ser positiva, encontrado {int(val)}", decl.lineno)
                    shape.append(0)
                else:
                    shape.append(int(val))

        sym = Symbol(
            name = decl.name,
            kind = 'array',
            type = decl.type_name,
            shape = shape,
            lineno = decl.lineno,
        )
        self.current_table.declare(sym)


    def _visit_parameter_decl(self, decl: ParameterDecl):
        for name, expr in decl.assignments:
            val = self._eval_const(expr)
            expr_type = self._type_of(expr)
            sym = Symbol(
                name = name,
                kind = 'parameter',
                value  = val,
                type = expr_type,
                lineno = decl.lineno,
            )
            prev = self.current_table.declare(sym)
            if prev is not None:
                self.error(f"constante '{name}' declarada mais do que uma vez", decl.lineno)

    # -------------------------------------- Statements --------------------------------------- #

    def _visit_stmt(self, stmt: Node):
        if isinstance(stmt, LabeledStmt):
            self._visit_stmt(stmt.stmt)
        elif isinstance(stmt, Assignment):
            self._visit_assignment(stmt)
        elif isinstance(stmt, IfThen):
            self._visit_if_then(stmt)
        elif isinstance(stmt, LogicalIf):
            self._visit_logical_if(stmt)
        elif isinstance(stmt, ArithmeticIf):
            self._visit_arithmetic_if(stmt)
        elif isinstance(stmt, DoLoop):
            self._visit_do_loop(stmt)
        elif isinstance(stmt, Goto):
            self._visit_goto(stmt)
        elif isinstance(stmt, Call):
            self._visit_call(stmt)
        elif isinstance(stmt, Return):
            self._visit_return(stmt)
        elif isinstance(stmt, Print):
            self._visit_print(stmt.args, stmt.lineno)
        elif isinstance(stmt, Read):
            self._visit_read(stmt.args, stmt.lineno)
        elif isinstance(stmt, (Continue, Stop)):
            pass # Não é preciso verificar


    def _visit_assignment(self, stmt: Assignment):
        # Verificar que o alvo existe e não é uma constante PARAMETER
        target_type = self._check_lvalue(stmt.target)
        value_type = self._type_of(stmt.value)

        if target_type is None or value_type is None:
            return

        # Atribuição de LOGICAL a numéricos ou vice-versa
        t_is_logical = target_type == 'LOGICAL'
        v_is_logical = value_type == 'LOGICAL'
        if t_is_logical != v_is_logical:
            self.error(f"atribuição incompatível: tipo '{value_type}' não pode ser atribuído a '{target_type}'", stmt.lineno)
            return

        # Atribuição de REAL a INTEGER (aviso apenas, por perda de precisão)
        if target_type == 'INTEGER' and value_type in ('REAL', 'DOUBLE PRECISION'):
            self.warning(f"atribuição com perda de precisão: '{value_type}' truncado para 'INTEGER'", stmt.lineno)


    def _check_lvalue(self, target: Node) -> Optional[str]:
        """ Verifica um lvalue (alvo de atribuição). Devolve o tipo. """
        if isinstance(target, Var):
            try:
                sym = self.current_table.lookup_or_implicit(target.name, target.lineno)
            except KeyError:
                self.error(f"variável '{target.name}' usada sem ser declarada", target.lineno)
                return None
            if sym.kind == 'parameter':
                self.error(f"'{target.name}' é uma constante PARAMETER e não pode ser modificada", target.lineno)
                return None
            return sym.type

        elif isinstance(target, FuncCall):
            # A(1) = ... - indexação do array no lado esquerdo
            try:
                sym = self.current_table.lookup_or_implicit(target.name, target.lineno)
            except KeyError:
                self.error(f"'{target.name}' usada sem ser declarada", target.lineno)
                return None
            if sym.kind not in ('array', 'variable'):
                # Pode ser atribuição de retorno de função (CONVRT = VAL), melhor passar
                pass
            for arg in target.args:
                self._type_of(arg) # Verificar tipos dos índices
            return sym.type
        return None


    def _visit_if_then(self, stmt: IfThen):
        cond_type = self._type_of(stmt.condition)
        if cond_type is not None and cond_type != 'LOGICAL':
            self.error(f"condição do IF deve ser LOGICAL, encontrado '{cond_type}'", stmt.lineno)
        for s in stmt.then_body:
            self._visit_stmt(s)
        for cond, body in stmt.elseif_list:
            ct = self._type_of(cond)
            if ct is not None and ct != 'LOGICAL':
                self.error(f"condição do ELSEIF deve ser LOGICAL, encontrado '{ct}'", stmt.lineno)
            for s in body:
                self._visit_stmt(s)
        if stmt.else_body:
            for s in stmt.else_body:
                self._visit_stmt(s)


    def _visit_logical_if(self, stmt: LogicalIf):
        cond_type = self._type_of(stmt.condition)
        if cond_type is not None and cond_type != 'LOGICAL':
            self.error(f"condição do IF deve ser LOGICAL, encontrado '{cond_type}'", stmt.lineno)
        self._visit_stmt(stmt.stmt)


    def _visit_arithmetic_if(self, stmt: ArithmeticIf):
        expr_type = self._type_of(stmt.expr)
        if expr_type is not None and expr_type not in NUMERIC_TYPES:
            self.error(f"IF aritmético requer expressão numérica, encontrado '{expr_type}'", stmt.lineno)
        for label in (stmt.label_neg, stmt.label_zero, stmt.label_pos):
            self.goto_labels.append((label, stmt.lineno))


    def _visit_do_loop(self, stmt: DoLoop):
        # Variável de controlo deve ser INTEGER
        try:
            sym = self.current_table.lookup_or_implicit(stmt.var, stmt.lineno)
        except KeyError:
            self.error(f"variável de controlo '{stmt.var}' do DO não declarada", stmt.lineno)
            sym = None

        if sym is not None and sym.type not in (None, 'INTEGER'):
            self.warning(f"variável de controlo '{stmt.var}' do DO é '{sym.type}', recomendado INTEGER", stmt.lineno)

        # Verificar expressões de limite
        for expr in (stmt.start, stmt.end) + ((stmt.step,) if stmt.step else ()):
            t = self._type_of(expr)
            if t is not None and t not in NUMERIC_TYPES:
                self.error(f"limite do DO deve ser numérico, encontrado '{t}'", stmt.lineno)

        # Verificar body
        for s in stmt.body:
            self._visit_stmt(s)


    def _visit_goto(self, stmt: Goto):
        # Registar para verificação no fim do âmbito
        self.goto_labels.append((stmt.label, stmt.lineno))


    def _visit_call(self, stmt: Call):
        # Procurar na tabela global (subprogramas) e depois na local
        sym = self.global_table.lookup(stmt.name)
        if sym is None:
            sym = self.current_table.lookup(stmt.name)
        if sym is None:
            self.warning(f"subrotina '{stmt.name}' não definida no ficheiro (pode ser externa)", stmt.lineno)
            return
        if sym.kind == 'function':
            self.error(f"'{stmt.name}' é uma FUNCTION, não uma SUBROUTINE; use numa expressão em vez de CALL", stmt.lineno)
            return
        # Adiar a verificação do nº de argumentos para a Passagem 2, porque param_types só fica completo depois de _analyze_subprogram correr.
        self._pending_calls.append((stmt.name, stmt.args, stmt.lineno))


    def _visit_return(self, stmt: Return):
        if not self.in_subprogram:
            self.error("RETURN fora de FUNCTION ou SUBROUTINE", stmt.lineno)


    def _visit_print(self, args: list, lineno: int):
        for arg in args:
            self._type_of(arg) # Verificar que as expressões são válidas


    def _visit_read(self, args: list, lineno: int):
        for arg in args:
            if not isinstance(arg, (Var, FuncCall)):
                self.error("READ requer variáveis ou elementos de array, não expressões arbitrárias", lineno)
            else:
                self._check_lvalue(arg)


    def _check_pending_calls(self):
        """
        Passagem 2: verifica o nº de argumentos de todas as chamadas a subprogramas registadas em _pending_calls durante a Passagem 1.
        Neste ponto param_types já está preenchido para todos os subprogramas do ficheiro.
        """
        for name, args, lineno in self._pending_calls:
            sym = self.global_table.lookup(name)
            if sym is not None:
                self._check_arg_count(name, sym, args, lineno)


    def _check_goto_labels(self):
        """ Verifica que todos os labels referenciados por GOTO existem """
        for label, lineno in self.goto_labels:
            if label not in self.defined_labels:
                self.error(f"GOTO referencia label {label} que não existe neste âmbito", lineno)

    # -------------------------------------- Inferência de Tipos --------------------------------------- #

    def _type_of(self, node: Node) -> Optional[str]:
        """
        Devolve o tipo de uma expressão e regista erros/avisos semânticos.

        A inferência de tipo pura é delegada para infer_type() em symbol_table.py. Esta função acrescenta por cima:
          - chamada a lookup_or_implicit (pode criar símbolos com implicit typing)
          - registo de erros para variáveis não declaradas com IMPLICIT NONE
          - validação cruzada de tipos nos operadores (UnaryOp, BinOp)
          - validação de chamadas (subroutine usada como função, arg count, etc.)
        """
        if isinstance(node, Var):
            return self._type_of_var(node)
        if isinstance(node, FuncCall):
            return self._type_of_call(node)
        if isinstance(node, UnaryOp):
            return self._type_of_unary(node)
        if isinstance(node, BinOp):
            return self._type_of_binop(node)
        # Literais: podemos delegar diretamente
        return infer_type(node, self.current_table, self.global_table, INTRINSICS)


    def _type_of_var(self, node: Var) -> Optional[str]:
        try:
            sym = self.current_table.lookup_or_implicit(node.name, node.lineno)
            return sym.type
        except KeyError:
            self.error(f"variável '{node.name}' usada sem ser declarada", node.lineno)
            return None


    def _type_of_call(self, node: FuncCall) -> Optional[str]:
        """
        Resolve FuncCall: pode ser chamada de função ou indexação de array. A distinção faz-se aqui, com base na tabela de símbolos.
        Acrescenta validação (erros e avisos) por cima de infer_type.
        """
        name = node.name

        # Hipótese 1: Ver nas intrínsecas
        if name in INTRINSICS:
            ret_type, param_types = INTRINSICS[name]
            if param_types and param_types[0] != '*':
                if len(node.args) != len(param_types):
                    self.error(f"função intrínseca '{name}' espera {len(param_types)} argumento(s), recebeu {len(node.args)}", node.lineno)
            arg_types = [self._type_of(a) for a in node.args]
            if ret_type == '*':
                return arg_types[0] if arg_types else 'INTEGER'
            return ret_type

        # Hipótese 2: Subprograma definido no ficheiro (tabela global)
        global_sym = self.global_table.lookup(name)
        if global_sym is not None:
            if global_sym.kind == 'subroutine':
                self.error(f"'{name}' é uma SUBROUTINE; use CALL em vez de expressão", node.lineno)
                return None
            # Adiar a verificação do nº de argumentos para a Passagem 2.
            self._pending_calls.append((name, node.args, node.lineno))
            return global_sym.type

        # Hipótese 3: Array indexing - variável declarada como array
        local_sym = self.current_table.lookup(name)
        if local_sym is not None:
            if local_sym.kind == 'array':
                if local_sym.shape and len(node.args) != len(local_sym.shape):
                    self.error(f"array '{name}' tem {len(local_sym.shape)} dimensão(ões), mas foi indexado com {len(node.args)}", node.lineno)
                for arg in node.args:
                    idx_type = self._type_of(arg)
                    if idx_type is not None and idx_type != 'INTEGER':
                        self.warning(f"índice de array '{name}' deveria ser INTEGER, encontrado '{idx_type}'", node.lineno)
                return local_sym.type
            elif local_sym.kind == 'variable':
                self.warning(f"'{name}' está declarado como variável mas é chamado como função; se for uma função externa, declare com EXTERNAL", node.lineno)
                return local_sym.type

        # Hipótese 4: Não encontrado - implicit typing para funções
        if not self.current_table.implicit_none:
            itype = implicit_type(name)
            self.warning(f"função '{name}' não declarada; tipo inferido por implicit typing: '{itype}'", node.lineno)
            return itype

        self.error(f"'{name}' não declarado", node.lineno)
        return None


    def _type_of_unary(self, node: UnaryOp) -> Optional[str]:
        """ A validação semântica de UnaryOp é feita nesta função. """
        operand_type = self._type_of(node.operand)
        if node.op == '.NOT.':
            if operand_type is not None and operand_type != 'LOGICAL':
                self.error(f".NOT. requer operando LOGICAL, encontrado '{operand_type}'", node.lineno)
            return 'LOGICAL'
        if node.op == '-':
            if operand_type is not None and operand_type not in NUMERIC_TYPES:
                self.error(f"negação unária requer tipo numérico, encontrado '{operand_type}'", node.lineno)
            return operand_type
        return operand_type


    def _type_of_binop(self, node: BinOp) -> Optional[str]:
        """ A validação cruzada de tipos entre operandos é responsabilidade do semantic e não pode ser movida para infer_type. """
        lt = self._type_of(node.left)
        rt = self._type_of(node.right)
        op = node.op

        if op in ('.AND.', '.OR.', '.EQV.', '.NEQV.'):
            for t, side in ((lt, 'esquerdo'), (rt, 'direito')):
                if t is not None and t != 'LOGICAL':
                    self.error(f"operador '{op}' requer operandos LOGICAL; operando {side} é '{t}'", node.lineno)
            return 'LOGICAL'

        if op in ('.EQ.', '.NE.', '.LT.', '.LE.', '.GT.', '.GE.'):
            if lt is not None and rt is not None and lt != rt:
                if not (lt in NUMERIC_TYPES and rt in NUMERIC_TYPES):
                    self.error(f"comparação '{op}' entre tipos incompatíveis '{lt}' e '{rt}'", node.lineno)
            return 'LOGICAL'

        if op == '//':
            for t, side in ((lt, 'esquerdo'), (rt, 'direito')):
                if t is not None and t != 'CHARACTER':
                    self.error(f"operador '//' requer CHARACTER; operando {side} é '{t}'", node.lineno)
            return 'CHARACTER'

        if op in ('+', '-', '*', '/', '**'):
            for t, side in ((lt, 'esquerdo'), (rt, 'direito')):
                if t is not None and t not in NUMERIC_TYPES:
                    self.error(f"operador '{op}' requer operandos numéricos; operando {side} é '{t}'", node.lineno)
            if lt is not None and rt is not None:
                return wider_type(lt, rt)
            return lt or rt

        return None

    # -------------------------------------- Utils --------------------------------------- #

    def _check_arg_count(self, name: str, sym: Symbol, args: list, lineno: int):
        """ Verifica o nº de argumentos numa chamada """
        expected = len(sym.param_types)
        got = len(args)
        if expected > 0 and got != expected:
            self.error(f"'{name}' espera {expected} argumento(s), recebeu {got}", lineno)


    def _eval_const(self, node: Node) -> Optional[float]:
        """
        Wrapper sobre eval_const() de symbol_table.py.
        O semantic continua a usar float em todo o lado (para as dimensões de arrays), por isso converte para float se necessário.
        """
        v = eval_const(node, self.current_table)
        return float(v) if v is not None else None

    # -------------------------------------- Relatório/Debug --------------------------------------- #

    def print_report(self, file=None):
        if file is None:
            file = sys.stderr
        if not self.diagnostics:
            print("[SEMANTIC] OK -- nenhum erro encontrado.", file=file)
            return
        for d in self.diagnostics:
            print(str(d), file=file)
        nerr = len(self.errors)
        nwarn = len(self.warnings)
        print(f"[SEMANTIC] {nerr} erro(s), {nwarn} aviso(s).", file=file)


    def print_symbol_table(self, file=None):
        """ Imprime todas as tabelas de símbolos de forma tabular, para debugging """
        if file is None:
            file = sys.stdout

        def print_table(table: SymbolTable):
            syms = table.all_symbols()
            if not syms:
                print("  (vazia)", file=file)
                return
            # cabeçalho
            print(f"  {'NOME':<12} {'KIND':<12} {'TIPO':<18} {'SHAPE':<12} {'PARAM?':<8} {'OFFSET'}", file=file)
            print(f"  {'-'*12} {'-'*12} {'-'*18} {'-'*12} {'-'*8} {'-'*6}", file=file)
            for s in syms:
                shape_str = str(s.shape) if s.shape else '—'
                param_str = f"#{s.param_index}" if s.is_param else '—'
                print(f"  {s.name:<12} {s.kind:<12} {str(s.type):<18} {shape_str:<12} {param_str:<8} {s.offset}", file=file)

        # Tabela global
        print("", file=file)
        print(f"=== Âmbito Global ===", file=file)
        print_table(self.global_table)

        # Tabelas locais, por ordem de aparição
        for scope_name, table in self.local_tables.items():
            implicit_str = " [IMPLICIT NONE]" if table.implicit_none else ""
            print("", file=file)
            print(f"=== Âmbito: {scope_name}{implicit_str} ===", file=file)
            print_table(table)


def run_semantic(tree: ProgramFile) -> Optional[SemanticAnalyzer]:
    """
    Corre a análise semântica sobre a AST.
    Devolve o SemanticAnalyzer (com tabelas de símbolos preenchidas) se não houver erros,
    ou None se houver erros que impeçam a compilação
    """
    analyzer = SemanticAnalyzer()
    analyzer.analyze(tree)
    analyzer.print_report()
    if analyzer.errors:
        return None
    return analyzer