# Fase 4 - Tradução de Código

from __future__ import annotations
from typing import Optional

from ast_nodes import (
    Node, ProgramFile, Program, Subprogram, VarDecl, ArrayDecl, ImplicitNone,
    ParameterDecl, LabeledStmt, Assignment, IfThen, ArithmeticIf, LogicalIf,
    DoLoop, Continue, Goto, Call, Return, Stop, Print, Read,
    BinOp, UnaryOp, FuncCall, Var, IntLiteral, RealLiteral, StrLiteral, LogicalLiteral
)
from symbol_table import SymbolTable, Symbol, infer_type, eval_const
from semantic import SemanticAnalyzer, INTRINSICS


class CodegenError(Exception):
    pass


class CodeGenerator:
    """
    Percorre a AST e emite instruções para a VM stack-based.
    Após generate(), consulta self.output (list[str]).
    """
    def __init__(self, analyzer: SemanticAnalyzer):
        self.analyzer =            analyzer
        self.output:               list[str] = []
        self._label_counter =      0
        self._current_scope:       str = ''
        self._current_table:       Optional[SymbolTable] = None
        self._current_kind:        str = 'program'   # 'program' | 'function' | 'subroutine'
        self._current_func_name:   str = ''
        self._fort_labels:         dict[int, str] = {}  # label Fortran → label VM
        self._next_temp_offset:    int = 0         # próximo offset de temporário disponível

    # ------------------------------------- Labels ------------------------------------- #

    def _new_label(self, prefix: str = 'L') -> str:
        self._label_counter += 1
        return f'{prefix}{self._label_counter}'

    def _fort_label(self, n: int) -> str:
        """ Devolve (criando se necessário) o label VM correspondente ao label Fortran n. """
        if n not in self._fort_labels:
            self._fort_labels[n] = self._new_label(f'F{n}')
        return self._fort_labels[n]

    # ------------------------------------- Emissão ------------------------------------- #

    def _emit(self, instr: str):
        self.output.append(instr)

    def _emit_label(self, label: str):
        """
        Emite um label e aplica peephole:
          JUMP <label>   seguido imediatamente de   <label>:
          é um salto para a instrução seguinte — completamente inútil.
          Ao emitir o label, se a última instrução emitida for exatamente
          'JUMP <label>', ela é removida.

        Exemplo antes:       Exemplo depois:
          ...body...           ...body...
          JUMP ENDIF           ENDIF:
          ENDIF:
        """
        jump_instr = f'JUMP {label}'
        if self.output and self.output[-1] == jump_instr:
            # Otimização peephole: eliminar JUMP redundante para o label imediato
            self.output.pop()
        self.output.append(f'{label}:')

    # ------------------------------------- Ponto de entrada ------------------------------------- #

    def generate(self, tree: ProgramFile):
        """ Gera código para toda a ProgramFile. Programa principal primeiro, depois subprogramas. """
        main_unit = None
        subprograms = []
        for unit in tree.units:
            if isinstance(unit, Program):
                main_unit = unit
            elif isinstance(unit, Subprogram):
                subprograms.append(unit)

        self._emit('START')
        if main_unit is not None:
            self._gen_program(main_unit)
        self._emit('STOP')

        for sub in subprograms:
            self._gen_subprogram(sub)

    # ------------------------------------- Atribuição de offsets ------------------------------------- #

    def _assign_offsets(self, table: SymbolTable, params: list[str]):
        """
        Atribui offsets de frame a todos os símbolos do âmbito.

        Parâmetros: offsets negativos relativamente ao fp.
          params[0] → fp[-n], params[1] → fp[-(n-1)], ..., params[-1] → fp[-1]

        Variáveis locais (e variável de retorno de função): offsets 0, 1, 2, ...
        Arrays contam como 1 slot (o slot guarda o endereço heap).

        Devolve (n_params, n_locals).
        """
        n_params = len(params)
        for idx, pname in enumerate(params):
            sym = table.lookup(pname)
            if sym is not None:
                sym.offset = idx - n_params   # negativo

        local_offset = 0
        for sym in table.all_symbols():
            if sym.is_param:
                continue
            if sym.kind in ('parameter', 'function', 'subroutine'):
                continue
            sym.offset = local_offset
            local_offset += 1

        return n_params, local_offset

    # ------------------------------------- Programa principal ------------------------------------- #

    def _gen_program(self, node: Program):
        scope = node.name or '<programa>'
        self._current_scope = scope
        self._current_table = self.analyzer.local_tables.get(scope)
        self._current_kind = 'program'
        self._current_func_name = ''
        self._fort_labels = {}

        if self._current_table is None:
            return

        _, n_locals = self._assign_offsets(self._current_table, [])
        self._next_temp_offset = n_locals   # temporários começam depois das variáveis

        if n_locals > 0:
            self._emit(f'PUSHN {n_locals}')

        self._alloc_arrays(self._current_table, is_global=True)
        self._gen_body(node.body)

    # ------------------------------------- Subprogramas ------------------------------------- #

    def _gen_subprogram(self, node: Subprogram):
        self._current_scope = node.name
        self._current_table = self.analyzer.local_tables.get(node.name)
        self._current_kind = node.kind.lower()   # 'function' | 'subroutine'
        self._current_func_name = node.name if node.kind == 'FUNCTION' else ''
        self._fort_labels = {}

        if self._current_table is None:
            return

        self._emit_label(node.name)

        _, n_locals = self._assign_offsets(self._current_table, node.params)
        self._next_temp_offset = n_locals   # temporários começam depois das variáveis

        if n_locals > 0:
            self._emit(f'PUSHN {n_locals}')

        self._alloc_arrays(self._current_table, is_global=False)
        self._gen_body(node.body)

        # RETURN implícito no fim (se o corpo não terminar já com RETURN ou STOP)
        if not self._last_instr_is('RETURN', 'STOP'):
            if node.kind == 'FUNCTION':
                ret_sym = self._current_table.lookup(node.name)
                if ret_sym is not None:
                    self._emit_load(ret_sym.offset)
            self._emit('RETURN')

    def _last_instr_is(self, *instrs: str) -> bool:
        """ Verifica se a última instrução emitida (ignorando labels) é uma das dadas. """
        for line in reversed(self.output):
            if line.endswith(':'):
                continue      # label — ignorar
            return line.strip() in instrs
        return False

    # ------------------------------------- Alocação de arrays na heap ------------------------------------- #

    def _alloc_arrays(self, table: SymbolTable, is_global: bool):
        """ Aloca na heap cada array declarado no âmbito e guarda o endereço no slot correspondente. """
        for sym in table.all_symbols():
            if sym.kind != 'array' or sym.is_param:
                continue
            size = 1
            for d in sym.shape:
                size *= d
            self._emit(f'ALLOC {size}')
            if is_global:
                self._emit(f'STOREG {sym.offset}')
            else:
                self._emit(f'STOREL {sym.offset}')

    # ------------------------------------- Corpo (lista de statements) ------------------------------------- #

    def _gen_body(self, stmts: list):
        for stmt in stmts:
            self._gen_stmt(stmt)

    # ------------------------------------- Statements ------------------------------------- #

    def _gen_stmt(self, stmt: Node):
        if isinstance(stmt, LabeledStmt):
            self._gen_labeled(stmt)
        elif isinstance(stmt, Assignment):
            self._gen_assignment(stmt)
        elif isinstance(stmt, IfThen):
            self._gen_if_then(stmt)
        elif isinstance(stmt, LogicalIf):
            self._gen_logical_if(stmt)
        elif isinstance(stmt, ArithmeticIf):
            self._gen_arithmetic_if(stmt)
        elif isinstance(stmt, DoLoop):
            self._gen_do_loop(stmt)
        elif isinstance(stmt, Goto):
            self._gen_goto(stmt)
        elif isinstance(stmt, Call):
            self._gen_call_stmt(stmt)
        elif isinstance(stmt, Return):
            self._gen_return(stmt)
        elif isinstance(stmt, Stop):
            self._gen_stop(stmt)
        elif isinstance(stmt, Print):
            self._gen_print(stmt)
        elif isinstance(stmt, Read):
            self._gen_read(stmt)
        elif isinstance(stmt, Continue):
            pass  # label emitido pelo LabeledStmt pai; CONTINUE em si não gera código

    def _gen_labeled(self, stmt: LabeledStmt):
        lbl = self._fort_label(stmt.label)
        self._emit_label(lbl)
        self._gen_stmt(stmt.stmt)

    # ------------------------------------- Atribuição ------------------------------------- #

    def _gen_assignment(self, stmt: Assignment):
        target = stmt.target

        if isinstance(target, Var):
            self._gen_expr(stmt.value)
            self._store_var(target.name)

        elif isinstance(target, FuncCall):
            # Pode ser A(I) = expr  (array) ou FUNCNAME = expr (retorno de função)
            sym = self._current_table.lookup(target.name)
            if sym is not None and sym.kind == 'array':
                # Ordem para STOREN: addr idx val
                self._load_addr(sym)
                self._gen_array_index(sym, target.args)
                self._gen_expr(stmt.value)
                self._emit('STOREN')
            else:
                # Variável escalar ou variável de retorno de função
                self._gen_expr(stmt.value)
                self._store_var(target.name)

    # ------------------------------------- Helpers de acesso a variáveis ------------------------------------- #

    # _emit_load e _emit_store recebem um offset directamente (positivo para locais/globais, negativo para parâmetros de subprogramas).
    def _emit_load(self, offset: int):
        """ Empilha o valor no offset dado da frame actual (global ou local). """
        if self._current_kind == 'program':
            self._emit(f'PUSHG {offset}')
        else:
            self._emit(f'PUSHL {offset}')

    def _emit_store(self, offset: int):
        """ Desempilha o topo e guarda no offset dado da frame actual. """
        if self._current_kind == 'program':
            self._emit(f'STOREG {offset}')
        else:
            self._emit(f'STOREL {offset}')


    def _store_var(self, name: str):
        self._emit_store(self._lookup(name).offset)

    def _load_var(self, name: str):
        self._emit_load(self._lookup(name).offset)

    def _load_addr(self, sym: Symbol):
        """ Empilha o endereço base do array (guardado no slot escalar do símbolo). """
        self._emit_load(sym.offset)

    def _lookup(self, name: str) -> Symbol:
        sym = self._current_table.lookup(name)
        if sym is None:
            raise CodegenError(f"Símbolo '{name}' não encontrado na tabela de símbolos")
        return sym

    # -----------------------------------------------------------------------------
    # Índice flat de array (row-major, 1-based → 0-based)
    #
    # Para array A(d1, d2, ...):
    #   flat = (i1-1) + d1*(i2-1) + d1*d2*(i3-1) + ...
    #
    # Após esta função, o topo da stack contém o índice flat.
    # Antes de chamar, o endereço base já deve estar na stack (para STOREN/LOADN).
    # -----------------------------------------------------------------------------
    def _gen_array_index(self, sym: Symbol, args: list):
        """
        Calcula o índice flat 0-based para LOADN/STOREN.

        Fórmula (column-major, 1-based → 0-based):
          flat = (i1-1) + d1*(i2-1) + d1*d2*(i3-1) + ...

        Otimização — constant folding no índice:
          Se todos os argumentos de indexação forem constantes em compile-time,
          o índice flat é calculado aqui e emitido como um único PUSHI, evitando
          a sequência SUB/MUL/ADD em runtime.

          Exemplo:  A(3)      → PUSHI 2          (em vez de PUSHI 3 / PUSHI 1 / SUB)
                    MAT(2,3)  → PUSHI <flat>      (em vez de 7 instruções)
        """
        ndim = len(sym.shape)

        # Tentar calcular o índice flat completamente em compile-time
        const_args = [self._eval_const_int(a) for a in args]
        if all(v is not None for v in const_args):
            # Todos os índices são constantes: calcular flat aqui
            flat = const_args[0] - 1
            stride = 1
            for k in range(1, ndim):
                stride *= sym.shape[k - 1]
                flat += stride * (const_args[k] - 1)
            self._emit(f'PUSHI {flat}')
            return

        # Caso geral: pelo menos um índice é variável
        if ndim == 1:
            # flat = i1 - 1
            self._gen_expr(args[0])
            self._emit('PUSHI 1')
            self._emit('SUB')
        else:
            # flat = (i1-1) + d1*(i2-1) + d1*d2*(i3-1) + ...
            self._gen_expr(args[0])
            self._emit('PUSHI 1')
            self._emit('SUB')
            stride = 1
            for k in range(1, ndim):
                stride *= sym.shape[k - 1]
                self._gen_expr(args[k])
                self._emit('PUSHI 1')
                self._emit('SUB')
                self._emit(f'PUSHI {stride}')
                self._emit('MUL')
                self._emit('ADD')

    # ------------------------------------- IF THEN / ELSEIF / ELSE ------------------------------------- #

    def _gen_if_then(self, stmt: IfThen):
        """
        Estrutura gerada:

            <cond_0>
            JZ ELSE_1
            <then_body>
            JUMP ENDIF
          ELSE_1:
            <cond_1>          ← ELSEIF
            JZ ELSE_2
            <elseif_body_1>
            JUMP ENDIF
          ELSE_2:
            <else_body>       ← ELSE (ou vazio)
          ENDIF:
        """
        end_label = self._new_label('ENDIF')
        branches = [(stmt.condition, stmt.then_body)] + list(stmt.elseif_list)

        for i, (cond, body) in enumerate(branches):
            # Label para o próximo branch (ou ELSE/ENDIF se for o último)
            next_label = self._new_label('ELSE')

            self._gen_expr(cond)
            self._emit(f'JZ {next_label}')
            self._gen_body(body)
            self._emit(f'JUMP {end_label}')
            self._emit_label(next_label)

        # Depois do último branch, o next_label já está emitido e aponta aqui
        if stmt.else_body:
            self._gen_body(stmt.else_body)

        self._emit_label(end_label)

    # ------------------------------------- IF lógico de uma linha ------------------------------------- #

    def _gen_logical_if(self, stmt: LogicalIf):
        """ IF (cond) stmt — salta stmt se cond for falsa. """
        skip = self._new_label('IFL')
        self._gen_expr(stmt.condition)
        self._emit(f'JZ {skip}')
        self._gen_stmt(stmt.stmt)
        self._emit_label(skip)

    # ------------------------------------- IF aritmético: IF (expr) l1, l2, l3 ------------------------------------- #

    def _gen_arithmetic_if(self, stmt: ArithmeticIf):
        """
        Avalia expr uma vez, salta para:
          label_neg  se expr < 0
          label_zero se expr == 0
          label_pos  se expr > 0

        Stack:
          após eval:          [v]
          após DUP 1:         [v, v]
          teste < 0:          consome um v, deixa [v] + resultado do teste
          se negativo:        POP o v restante, JUMP neg_lbl
          senão:              [v] continua para teste == 0
        """
        neg_lbl  = self._fort_label(stmt.label_neg)
        zero_lbl = self._fort_label(stmt.label_zero)
        pos_lbl  = self._fort_label(stmt.label_pos)

        not_neg  = self._new_label('AIFNN')
        not_zero = self._new_label('AIFNZ')

        self._gen_expr(stmt.expr)   # stack: [v]
        self._emit('DUP 1')         # stack: [v, v]

        # Testar v < 0
        self._emit('PUSHI 0')       # stack: [v, v, 0]
        self._emit('INF')           # stack: [v, (v<0)]
        self._emit(f'JZ {not_neg}') # se não negativo, salta
        # É negativo: descartar v original e saltar
        self._emit('POP 1')         # stack: []
        self._emit(f'JUMP {neg_lbl}')

        # Testar v == 0
        self._emit_label(not_neg)   # stack: [v]
        self._emit('PUSHI 0')       # stack: [v, 0]
        self._emit('EQUAL')         # stack: [(v==0)]
        self._emit(f'JZ {not_zero}')
        self._emit(f'JUMP {zero_lbl}')

        # Caso contrário: v > 0
        self._emit_label(not_zero)
        self._emit(f'JUMP {pos_lbl}')

    # ------------------------------------------------------------------
    # DO loop
    #
    # Estrutura:
    #   var = start
    # DO_start:
    #   IF var <= end (ou >= se step<0) → continuar, senão saltar para end_lbl
    #   <body sem o LabeledStmt(CONTINUE) terminal>
    #   var = var + step
    #   JUMP DO_start
    # end_lbl:   ← label do DO
    # ------------------------------------------------------------------
    def _gen_do_loop(self, stmt: DoLoop):
        loop_start = self._new_label('DO')
        end_lbl    = self._fort_label(stmt.label)
        step_node  = stmt.step

        # Determinar sentido do loop em compile-time (para escolher INFEQ vs SUPEQ)
        step_is_negative = False
        if step_node is not None:
            cv = self._eval_const_int(step_node)
            if cv is not None and cv < 0:
                step_is_negative = True

        # Inicializar variável de controlo
        self._gen_expr(stmt.start)
        self._store_var(stmt.var)

        self._emit_label(loop_start)

        # Condição de continuação: var <= end  (ou var >= end se step < 0)
        self._load_var(stmt.var)
        self._gen_expr(stmt.end)
        if step_is_negative:
            self._emit('SUPEQ')
        else:
            self._emit('INFEQ')
        self._emit(f'JZ {end_lbl}')

        # Corpo: excluir o LabeledStmt(CONTINUE) com o label terminal do DO
        # (esse label será emitido logo a seguir como end_lbl)
        body_to_gen = [
            s for s in stmt.body
            if not (isinstance(s, LabeledStmt)
                    and s.label == stmt.label
                    and isinstance(s.stmt, Continue))
        ]
        self._gen_body(body_to_gen)

        # Incremento
        self._load_var(stmt.var)
        if step_node is not None:
            self._gen_expr(step_node)
        else:
            self._emit('PUSHI 1')
        self._emit('ADD')
        self._store_var(stmt.var)

        self._emit(f'JUMP {loop_start}')
        self._emit_label(end_lbl)

    # ------------------------------------- Inferência de tipo e avaliação de constantes ------------------------------------- #

    def _type_of(self, node: Node) -> Optional[str]:
        """ Wrapper: infere o tipo de node no âmbito actual. """
        return infer_type(node, self._current_table, self.analyzer.global_table, INTRINSICS)

    def _eval_const(self, node: Node) -> Optional[int | float]:
        """ Wrapper: tenta avaliar node como constante aritmética. Devolve int ou float. """
        return eval_const(node, self._current_table)

    def _eval_const_int(self, node: Node) -> Optional[int]:
        """
        Wrapper: como _eval_const mas só devolve um resultado se for inteiro exacto.
        Usado onde só interessa a parte inteira (step de DO, expoente de **).
        """
        v = eval_const(node, self._current_table)
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v.is_integer():
            return int(v)
        return None

    # ------------------------------------- GOTO ------------------------------------- #

    def _gen_goto(self, stmt: Goto):
        self._emit(f'JUMP {self._fort_label(stmt.label)}')

    # ------------------------------------- CALL (subroutine) ------------------------------------- #

    def _gen_call_stmt(self, stmt: Call):
        for arg in stmt.args:
            self._gen_expr(arg)
        self._emit(f'PUSHA {stmt.name}')
        self._emit('CALL')
        # Subroutines não deixam valor na stack; RETURN da VM restaura sp para antes dos args.

    # ------------------------------------- RETURN ------------------------------------- #

    def _gen_return(self, stmt: Return):
        if self._current_kind == 'function':
            # Empilhar o valor de retorno (guardado na variável com o nome da função)
            ret_sym = self._current_table.lookup(self._current_func_name)
            if ret_sym is not None:
                self._emit(f'PUSHL {ret_sym.offset}')
        self._emit('RETURN')

    # ------------------------------------- STOP ------------------------------------- #

    def _gen_stop(self, stmt: Stop):
        self._emit('STOP')

    # ------------------------------------- PRINT ------------------------------------- #

    def _gen_print(self, stmt: Print):
        for i, arg in enumerate(stmt.args):
            # Separador entre argumentos (PRINT * separa com espaços)
            if i > 0:
                self._emit('PUSHS " "')
                self._emit('WRITES')

            self._gen_expr(arg)
            t = self._type_of(arg)
            if t in ('REAL', 'DOUBLE PRECISION'):
                self._emit('WRITEF')
            elif t == 'CHARACTER':
                self._emit('WRITES')
            elif t == 'LOGICAL':
                # 0 = .FALSE., != 0 = .TRUE.
                # JZ salta se o topo for 0 (falso) → imprime ".FALSE."
                # se não salta → imprime ".TRUE."
                false_lbl = self._new_label('PFALSE')
                end_lbl   = self._new_label('PEND')
                self._emit(f'JZ {false_lbl}')
                self._emit('PUSHS ".TRUE."')
                self._emit(f'JUMP {end_lbl}')
                self._emit_label(false_lbl)
                self._emit('PUSHS ".FALSE."')
                self._emit_label(end_lbl)
                self._emit('WRITES')
            else:
                self._emit('WRITEI')
        self._emit('WRITELN')

    # ------------------------------------- READ ------------------------------------- #

    def _gen_read(self, stmt: Read):
        for arg in stmt.args:
            t = self._type_of(arg)

            if isinstance(arg, Var):
                self._emit('READ')
                self._convert_read_value(t)
                self._store_var(arg.name)

            elif isinstance(arg, FuncCall):
                sym = self._current_table.lookup(arg.name)
                if sym is not None and sym.kind == 'array':
                    # STOREN espera: addr idx val
                    # Calcular addr e idx primeiro, depois ler e converter
                    self._load_addr(sym)
                    self._gen_array_index(sym, arg.args)
                    self._emit('READ')
                    self._convert_read_value(t)
                    self._emit('STOREN')
                else:
                    self._emit('READ')
                    self._convert_read_value(t)
                    self._store_var(arg.name)

    def _convert_read_value(self, t: Optional[str]):
        """ Converte o endereço de string da READ para o tipo apropriado. """
        if t in ('REAL', 'DOUBLE PRECISION'):
            self._emit('ATOF')
        elif t == 'CHARACTER':
            pass  # já é string
        else:
            self._emit('ATOI')

    # ------------------------------------- Expressões ------------------------------------- #

    def _gen_expr(self, node: Node):
        """
        Gera código para uma expressão.

        Otimização — constant folding:
          Antes de gerar qualquer instrução, tenta avaliar a expressão inteira
          em compile-time (_eval_const). Se for possível, emite um único
          PUSHI/PUSHF em vez da sequência de instruções que calcularia o valor
          em runtime.

          Exemplos:
            2 + 3        → PUSHI 5         (em vez de PUSHI 2 / PUSHI 3 / ADD)
            10 * 10 - 1  → PUSHI 99
            A(3)         → índice 3-1=2 calculado → PUSHI 2 (em _gen_array_index)
            PARAMETER PI = 3.14159
            PI * 2.0     → PUSHF 6.28318...
        """
        # Tentar constant folding para nós que não são literais simples
        # (literais já são O(1), o folding não acrescenta nada para eles)
        if isinstance(node, (BinOp, UnaryOp)):
            val = self._eval_const(node)
            if val is not None:
                if isinstance(val, float):
                    self._emit(f'PUSHF {val}')
                else:
                    self._emit(f'PUSHI {int(val)}')
                return

        if isinstance(node, IntLiteral):
            self._emit(f'PUSHI {node.value}')
        elif isinstance(node, RealLiteral):
            self._emit(f'PUSHF {node.value}')
        elif isinstance(node, StrLiteral):
            escaped = node.value.replace('"', '\\"')
            self._emit(f'PUSHS "{escaped}"')
        elif isinstance(node, LogicalLiteral):
            self._emit(f'PUSHI {1 if node.value else 0}')
        elif isinstance(node, Var):
            self._gen_var(node)
        elif isinstance(node, FuncCall):
            self._gen_funccall(node)
        elif isinstance(node, UnaryOp):
            self._gen_unary(node)
        elif isinstance(node, BinOp):
            self._gen_binop(node)
        else:
            raise CodegenError(f"Expressão não suportada: {type(node).__name__}")


    def _gen_var(self, node: Var):
        sym = self._current_table.lookup(node.name)
        if sym is None:
            raise CodegenError(f"Símbolo '{node.name}' não encontrado")
        if sym.kind == 'parameter':
            # Constante PARAMETER: emitir o valor diretamente
            val = sym.value
            if sym.type in ('REAL', 'DOUBLE PRECISION'):
                self._emit(f'PUSHF {float(val)}')
            else:
                self._emit(f'PUSHI {int(val)}')
        else:
            self._load_var(node.name)


    def _gen_funccall(self, node: FuncCall):
        name = node.name

        # 1. Funções intrínsecas
        if name in INTRINSICS:
            self._gen_intrinsic(name, node.args)
            return

        # 2. Array indexing (símbolo local declarado como array)
        sym = self._current_table.lookup(name) if self._current_table else None
        if sym is not None and sym.kind == 'array':
            self._load_addr(sym)
            self._gen_array_index(sym, node.args)
            self._emit('LOADN')
            return

        # 3. Função definida no ficheiro (tabela global)
        gsym = self.analyzer.global_table.lookup(name)
        if gsym is not None and gsym.kind == 'function':
            for arg in node.args:
                self._gen_expr(arg)
            self._emit(f'PUSHA {name}')
            self._emit('CALL')
            return

        # 4. Variável escalar (fallback — possível com implicit typing)
        if sym is not None:
            self._load_var(name)
            return

        raise CodegenError(f"Símbolo '{name}' não encontrado para FuncCall")

    # ------------------------------------- Funções intrínsecas ------------------------------------- #

    def _gen_intrinsic(self, name: str, args: list):
        """
        Gera código para uma função intrínseca.
        Os argumentos já são empilhados antes de chamar os helpers específicos,
        exceto quando a ordem ou a coerção de tipos exige tratamento especial.
        """
        # Empilhar todos os argumentos
        for arg in args:
            self._gen_expr(arg)

        arg_types = [self._type_of(a) for a in args]
        is_real = any(t in ('REAL', 'DOUBLE PRECISION') for t in arg_types if t)

        if name == 'ABS':
            self._gen_intrinsic_abs(arg_types)

        elif name == 'SIN':
            if not is_real: self._emit('ITOF')
            self._emit('FSIN')

        elif name == 'COS':
            if not is_real: self._emit('ITOF')
            self._emit('FCOS')

        elif name in ('INT', 'IFIX'):
            t = arg_types[0] if arg_types else 'REAL'
            if t in ('REAL', 'DOUBLE PRECISION'):
                self._emit('FTOI')

        elif name in ('REAL', 'FLOAT', 'DBLE'):
            t = arg_types[0] if arg_types else 'INTEGER'
            if t not in ('REAL', 'DOUBLE PRECISION'):
                self._emit('ITOF')

        elif name == 'MOD':
            self._emit('MOD')

        elif name in ('MAX', 'MAX0', 'AMAX1'):
            self._gen_intrinsic_minmax(len(args), is_real, is_max=True)

        elif name in ('MIN', 'MIN0', 'AMIN1'):
            self._gen_intrinsic_minmax(len(args), is_real, is_max=False)

        elif name == 'LEN':
            self._emit('STRLEN')

        else:
            # Intrínsecas não suportadas pela VM (SQRT, EXP, LOG, TAN, ...)
            self._emit(f'ERR "{name}: instrinseca nao suportada pela VM"')


    def _gen_intrinsic_abs(self, arg_types: list):
        """
        ABS(x): se x >= 0, manter; se x < 0, negar.

        Stack antes: [x]
        Stack depois: [|x|]
        """
        t = arg_types[0] if arg_types else 'INTEGER'
        lbl_neg = self._new_label('ABSNEG')
        lbl_end = self._new_label('ABSEND')

        self._emit('DUP 1')          # [x, x]
        if t in ('REAL', 'DOUBLE PRECISION'):
            self._emit('PUSHF 0.0')  # [x, x, 0.0]
            self._emit('FINF')       # [x, (x < 0.0)]
        else:
            self._emit('PUSHI 0')    # [x, x, 0]
            self._emit('INF')        # [x, (x < 0)]
        self._emit(f'JZ {lbl_neg}')  # se não negativo, salta para lbl_neg
        # x >= 0: apenas descartar o DUP e manter x original
        self._emit('POP 1')          # [x]   ← descarta o DUP
        self._emit(f'JUMP {lbl_end}')
        self._emit_label(lbl_neg)    # x < 0: negar
        if t in ('REAL', 'DOUBLE PRECISION'):
            self._emit('PUSHF -1.0')
            self._emit('FMUL')
        else:
            self._emit('PUSHI -1')
            self._emit('MUL')
        self._emit_label(lbl_end)


    def _gen_intrinsic_minmax(self, n_args: int, is_real: bool, is_max: bool):
        """
        MAX/MIN com n_args argumentos já na stack: [a0, a1, ..., a_{n-1}]

        Algoritmo iterativo: para cada par consecutivo, comparar e manter o maior/menor.
        Após cada passo, a stack tem um argumento a menos.

        A instrução de comparação (SUP/INF) devolve 1 se (topo_anterior > topo_atual),
        i.e., SUP: m > n  (m é o segundo, n é o primeiro a sair).
        Na documentação: "SUP: takes n and m from the pile and stacks the result m > n"
        → empilha m depois de n, portanto o segundo empilhado é 'm'.

        Para MAX: queremos manter o maior. Após COPY 2, temos [... a b a b].
          SUP devolve 1 se b > a (b é m, a é n).
          Se b > a (SUP=1, JZ não salta): manter b → SWAP + POP descarta a.
          Se a >= b (SUP=0, JZ salta para lbl_keep_a): manter a → POP descarta b.
        """
        if n_args < 2:
            return  # nada a fazer com 0 ou 1 argumentos

        for _ in range(n_args - 1):
            lbl_keep_a = self._new_label('MMKA')
            lbl_end    = self._new_label('MME')
            # stack: [..., a, b]
            self._emit('COPY 2')            # [..., a, b, a, b]
            if is_max:
                # SUP: m > n → b > a → manter b
                if is_real:
                    self._emit('FSUP')
                else:
                    self._emit('SUP')
                self._emit(f'JZ {lbl_keep_a}')
                # b > a: manter b, descartar a
                # stack: [..., a, b]
                self._emit('SWAP')          # [..., b, a]
                self._emit('POP 1')         # [..., b]
                self._emit(f'JUMP {lbl_end}')
                self._emit_label(lbl_keep_a)
                # a >= b: manter a, descartar b
                self._emit('POP 1')         # [..., a]
            else:
                # INF: m < n → b < a → manter b (b é o menor)
                if is_real:
                    self._emit('FINF')
                else:
                    self._emit('INF')
                self._emit(f'JZ {lbl_keep_a}')
                # b < a: manter b, descartar a
                self._emit('SWAP')          # [..., b, a]
                self._emit('POP 1')         # [..., b]
                self._emit(f'JUMP {lbl_end}')
                self._emit_label(lbl_keep_a)
                # a <= b: manter a, descartar b
                self._emit('POP 1')         # [..., a]
            self._emit_label(lbl_end)

    # ------------------------------------- Operadores unários ------------------------------------- #

    def _gen_unary(self, node: UnaryOp):
        self._gen_expr(node.operand)
        t = self._type_of(node.operand)
        if node.op == '-':
            if t in ('REAL', 'DOUBLE PRECISION'):
                self._emit('PUSHF -1.0')
                self._emit('FMUL')
            else:
                self._emit('PUSHI -1')
                self._emit('MUL')
        elif node.op == '.NOT.':
            self._emit('NOT')
        # '+' unário: não faz nada (identidade)

    # ------------------------------------- Operadores binários ------------------------------------- #

    def _gen_binop(self, node: BinOp):
        op = node.op
        lt = self._type_of(node.left)
        rt = self._type_of(node.right)
        is_real = (lt in ('REAL', 'DOUBLE PRECISION')
                   or rt in ('REAL', 'DOUBLE PRECISION'))

        # Concatenação de strings
        if op == '//':
            # Tem de ser assim (direita primeiro e depois esquerda, por causa da ordem que a VM pega nas strings da stack
            # -- como é a mais recente a ter sido empilhada a ser posta em primeiro lugar, temos de pôr a string que queremos estar em segundo lugar em primeiro)
            # O código resultante vai parecer que está ao contrário, mas está correto
            self._gen_expr(node.right)
            self._gen_expr(node.left)
            self._emit('CONCAT')
            return

        # Operadores lógicos (curto-circuito não é necessário em Fortran 77)
        if op in ('.AND.', '.OR.', '.EQV.', '.NEQV.'):
            self._gen_expr(node.left)
            self._gen_expr(node.right)
            vm_op = {'.AND.': 'AND', '.OR.': 'OR', '.EQV.': 'EQUAL', '.NEQV.': None}[op]
            if vm_op:
                self._emit(vm_op)
            else:
                self._emit('EQUAL')
                self._emit('NOT')
            return

        # Potenciação
        if op == '**':
            self._gen_power(node.left, node.right, is_real)
            return

        # Operadores aritméticos e relacionais: coerção INTEGER → REAL se necessário
        if is_real:
            self._gen_expr_coerced(node.left, lt)
            self._gen_expr_coerced(node.right, rt)
        else:
            self._gen_expr(node.left)
            self._gen_expr(node.right)

        # Mapa de operadores para inteiros e reais
        if is_real:
            op_map = {
                '+': 'FADD', '-': 'FSUB', '*': 'FMUL', '/': 'FDIV',
                '.EQ.': 'EQUAL', '.NE.': None,
                '.LT.': 'FINF',  '.LE.': 'FINFEQ',
                '.GT.': 'FSUP',  '.GE.': 'FSUPEQ',
            }
        else:
            op_map = {
                '+': 'ADD', '-': 'SUB', '*': 'MUL', '/': 'DIV',
                '.EQ.': 'EQUAL', '.NE.': None,
                '.LT.': 'INF',  '.LE.': 'INFEQ',
                '.GT.': 'SUP',  '.GE.': 'SUPEQ',
            }

        instr = op_map.get(op)
        if instr is None:
            # .NE. → EQUAL + NOT
            self._emit('EQUAL')
            self._emit('NOT')
        elif instr:
            self._emit(instr)
        else:
            raise CodegenError(f"Operador binário não suportado: {op}")

    def _gen_expr_coerced(self, node: Node, t: Optional[str]):
        """ Gera node e emite ITOF se t for INTEGER. """
        self._gen_expr(node)
        if t == 'INTEGER':
            self._emit('ITOF')

    # ------------------------------------------------------------------
    # Potência: base ** exp
    #
    # Estratégia:
    #   - Expoente constante positivo n:    DUP n-1 vezes + MUL n-1 vezes
    #   - Expoente constante 0:             empilhar 1
    #   - Expoente constante negativo:      1.0 / (base ** |n|)
    #   - Expoente variável:                loop runtime com variável auxiliar
    # ------------------------------------------------------------------

    def _gen_power(self, base_node: Node, exp_node: Node, is_real: bool):
        exp_val = self._eval_const_int(exp_node)

        if exp_val is not None:
            # --- Expoente constante ---
            n = exp_val
            if n == 0:
                if is_real:
                    self._emit('PUSHF 1.0')
                else:
                    self._emit('PUSHI 1')

            elif n == 1:
                self._gen_expr(base_node)
                if is_real and self._type_of(base_node) == 'INTEGER':
                    self._emit('ITOF')

            elif n > 1:
                # base ** n via DUP + MUL repetido
                # Exemplo n=3: [b] → DUP 1 → [b,b] → DUP 1 → [b,b,b] → MUL → [b,b²] → MUL → [b³]
                self._gen_expr(base_node)
                if is_real and self._type_of(base_node) == 'INTEGER':
                    self._emit('ITOF')
                for _ in range(n - 1):
                    self._emit('DUP 1')
                for _ in range(n - 1):
                    self._emit('FMUL' if is_real else 'MUL')

            else:  # n < 0
                # base ** -|n| = 1 / (base ** |n|)
                self._gen_power(base_node, IntLiteral(-n), is_real=True)
                self._emit('PUSHF 1.0')
                self._emit('SWAP')
                self._emit('FDIV')

        else:
            # --- Expoente variável: loop runtime ---
            #
            # A VM não tem instrução para aceder a posições arbitrárias da stack,
            # por isso guardamos base e exp em slots temporários do frame actual
            # (alocados dinamicamente com PUSHN 1) e usamos PUSHL/STOREL/PUSHG/STOREG
            # para os ler e escrever durante o loop.
            #
            # Algoritmo: resultado = 1; enquanto exp > 0 { resultado *= base; exp-- }
            tmp_base   = self._alloc_temp()
            tmp_exp    = self._alloc_temp()
            loop_lbl   = self._new_label('PWLP')
            end_lbl    = self._new_label('PWEND')

            # Guardar base e exp em temporários
            self._gen_expr(base_node)
            if is_real and self._type_of(base_node) == 'INTEGER':
                self._emit('ITOF')
            self._store_temp(tmp_base)

            self._gen_expr(exp_node)
            self._store_temp(tmp_exp)

            # resultado = 1
            if is_real:
                self._emit('PUSHF 1.0')
            else:
                self._emit('PUSHI 1')

            # Loop: enquanto exp > 0 { res *= base; exp-- }
            self._emit_label(loop_lbl)
            self._load_temp(tmp_exp)
            self._emit('PUSHI 0')
            self._emit('SUP')              # exp > 0?
            self._emit(f'JZ {end_lbl}')

            # res *= base
            self._load_temp(tmp_base)
            if is_real:
                self._emit('FMUL')
            else:
                self._emit('MUL')

            # exp--
            self._load_temp(tmp_exp)
            self._emit('PUSHI 1')
            self._emit('SUB')
            self._store_temp(tmp_exp)

            self._emit(f'JUMP {loop_lbl}')
            self._emit_label(end_lbl)
            # Stack: [resultado]

    # ------------------------------------- Gestão de temporários ------------------------------------- #

    def _alloc_temp(self) -> int:
        """
        Aloca um slot temporário no frame atual e devolve o seu offset.
        Emite PUSHN 1 para reservar espaço na stack.
        Usa _next_temp_offset para garantir que cada chamada devolve um offset diferente.
        """
        tmp_offset = self._next_temp_offset
        self._next_temp_offset += 1
        self._emit('PUSHN 1')   # reservar o slot na stack
        return tmp_offset

    def _store_temp(self, offset: int):
        self._emit_store(offset)

    def _load_temp(self, offset: int):
        self._emit_load(offset)

    # ------------------------------------- Output ------------------------------------- #

    def get_code(self) -> str:
        return '\n'.join(self.output)

    def print_code(self, file=None):
        import sys
        if file is None:
            file = sys.stdout
        print(self.get_code(), file=file)

# ------------------------------------- Função pública ------------------------------------- #

def run_codegen(tree: ProgramFile, analyzer: SemanticAnalyzer) -> Optional[CodeGenerator]:
    gen = CodeGenerator(analyzer)
    try:
        gen.generate(tree)
        return gen
    except CodegenError as e:
        import sys
        print(f'[CODEGEN] ERRO: {e}', file=sys.stderr)
        return None
