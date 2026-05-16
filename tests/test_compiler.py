"""
Testes automáticos do compilador Fortran77
"""

import sys
import io
from pathlib import Path
import pytest

# --------------------------------------- paths --------------------------------------- #

TESTS_DIR = Path(__file__).parent
ROOT_DIR  = TESTS_DIR.parent
SRC_DIR   = ROOT_DIR / "src"
ERROR_DIR = TESTS_DIR / "error"

# Garantir importação direta do src/
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compiler import run_codegen
from parser import parse_file
from semantic import run_semantic
from semantic import SemanticAnalyzer

# --------------------------------------- helpers --------------------------------------- #

def get_vm_code(src: Path) -> str:
    """
    Compila um ficheiro .f e devolve o código VM como string pura, sem nenhum header ou decoração do main.py.
    Levanta AssertionError se a compilação falhar.
    """
    gen, _ = run_codegen(str(src))
    assert gen is not None, f"Compilação falhou para {src.name}"
    return gen.get_code().strip()


def get_sem_output(src: Path) -> str:
    """
    Corre o parse + análise semântica e devolve todos os diagnósticos como string.
    Faz patch direto de sys.stderr/stdout para capturar também os prints do PLY (lexer/parser), que escapam ao contextlib.redirect_stderr.
    """
    buf = io.StringIO()
    old_err, old_out = sys.stderr, sys.stdout
    sys.stderr = sys.stdout = buf
    try:
        tree = parse_file(str(src))
        analyzer = SemanticAnalyzer()
        analyzer.analyze(tree)
        analyzer.print_report()
    finally:
        sys.stderr, sys.stdout = old_err, old_out
    return buf.getvalue()


def inline_codegen(fortran_src: str, tmp_path: Path) -> str:
    """ Compila uma string Fortran e devolve o código VM puro. """
    src = tmp_path / "prog.f"
    src.write_text(fortran_src)
    return get_vm_code(src)


def inline_sem_errors(fortran_src: str, tmp_path: Path) -> str:
    """ Corre a semântica sobre uma string Fortran e devolve os diagnósticos. """
    src = tmp_path / "prog.f"
    src.write_text(fortran_src)
    return get_sem_output(src)


def has_error_msg(output: str, keyword: str) -> bool:
    return keyword.lower() in output.lower()

# ========================================================================
# 1. TESTES DE ERRO — programas inválidos devem produzir mensagens de erro
# ========================================================================

class TestLexErrors:
    def test_unclosed_string(self):
        """ String não fechada deve gerar erro léxico. """
        src = ERROR_DIR / "19_lex_unclosed_string.f"
        out = get_sem_output(src)
        assert has_error_msg(out, "string") or has_error_msg(out, "LEXER"), \
            "Esperava mensagem de erro léxico para string não fechada"


class TestSyntaxErrors:
    def test_incomplete_assignment(self):
        """ Atribuição incompleta 'X =' deve produzir erro sintático. """
        src = ERROR_DIR / "16_syntax_incomplete_assign.f"
        out = get_sem_output(src)
        assert has_error_msg(out, "PARSER") or has_error_msg(out, "sintático"), \
            "Esperava erro sintático para atribuição incompleta"


    def test_missing_endif(self):
        """ IF THEN sem ENDIF deve produzir erro sintático. """
        src = ERROR_DIR / "17_syntax_missing_endif.f"
        out = get_sem_output(src)
        assert has_error_msg(out, "PARSER") or has_error_msg(out, "sintático")


    def test_unclosed_do(self):
        """ DO loop sem label CONTINUE correspondente deve produzir aviso. """
        src = ERROR_DIR / "18_syntax_unclosed_do.f"
        out = get_sem_output(src)
        assert has_error_msg(out, "nunca fechado") or has_error_msg(out, "label"), \
            "Esperava aviso de DO loop não fechado"


# ========================================================================
# 2. TESTES UNITÁRIOS SEMÂNTICOS (programas inline curtos)
# ========================================================================

class TestSemanticVariables:
    def test_undeclared_variable(self, tmp_path):
        src = """\
      PROGRAM T
      IMPLICIT NONE
      INTEGER X
      X = Y + 1
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "Y") or has_error_msg(out, "declarad"), \
            "Esperava erro de variável não declarada"


    def test_duplicate_declaration(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER N
      INTEGER N
      N = 1
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "N") and has_error_msg(out, "declarad"), \
            "Esperava erro de variável redeclarada"


    def test_declared_variable_ok(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER N
      N = 5
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert not has_error_msg(out, "ERROR"), \
            f"Não devia haver erros, mas obteve:\n{out}"


    def test_parameter_is_read_only(self, tmp_path):
        src = """\
      PROGRAM T
      PARAMETER (N = 5)
      N = 3
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "N") or has_error_msg(out, "PARAMETER") or has_error_msg(out, "constante"), \
            "Esperava erro ao modificar constante PARAMETER"


class TestSemanticTypes:
    def test_if_condition_must_be_logical(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER N
      N = 5
      IF (N) THEN
        N = 1
      ENDIF
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "LOGICAL"), \
            "Esperava erro: condição do IF deve ser LOGICAL"


    def test_if_condition_relational_ok(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER N
      N = 5
      IF (N .GT. 3) THEN
        N = 1
      ENDIF
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert not has_error_msg(out, "ERROR"), \
            "Expressão relacional em IF deve ser aceite como LOGICAL"


    def test_logical_assigned_to_integer_error(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A
      LOGICAL B
      B = .TRUE.
      A = B
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "incompatível") or has_error_msg(out, "LOGICAL"), \
            "Esperava erro de atribuição LOGICAL -> INTEGER"


    def test_real_to_integer_warning(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A
      A = 3.14
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "precisão") or has_error_msg(out, "WARNING"), \
            "Esperava aviso de truncagem REAL -> INTEGER"

# ========================================================================
# 3. SEMÂNTICA (subprogramas, arrays, etc.)
# ========================================================================

class TestSemanticSubprograms:
    def test_return_outside_subprogram(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER X
      X = 1
      RETURN
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "RETURN") or has_error_msg(out, "fora"), \
            "Esperava erro: RETURN fora de subprograma"


    def test_call_function_as_subroutine(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER R
      CALL DOBRO(7)
      END

      INTEGER FUNCTION DOBRO(X)
      INTEGER X
      DOBRO = X * 2
      RETURN
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "FUNCTION") or has_error_msg(out, "CALL"), \
            "Esperava erro: chamar FUNCTION com CALL"


    def test_wrong_arg_count(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER R
      R = DOBRO(7, 8)
      END

      INTEGER FUNCTION DOBRO(X)
      INTEGER X
      DOBRO = X * 2
      RETURN
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "argumento") or has_error_msg(out, "espera"), \
            "Esperava erro de número errado de argumentos"


    def test_goto_undefined_label(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER X
      X = 1
      GOTO 999
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "999") or has_error_msg(out, "label"), \
            "Esperava erro: GOTO para label inexistente"


class TestSemanticArrays:
    def test_array_wrong_dimensions(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A(3)
      A(1, 2) = 5
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert has_error_msg(out, "dimensão") or has_error_msg(out, "A"), \
            "Esperava erro: indexação de array com número errado de dimensões"


    def test_array_access_ok(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A(5), I
      I = 3
      A(I) = 10
      END
"""
        out = inline_sem_errors(src, tmp_path)
        assert not has_error_msg(out, "ERROR"), \
            "Acesso válido a array não devia gerar erros"


# ========================================================================
# 4. TESTES UNITÁRIOS DE CODEGEN (verificar instruções específicas)
# ========================================================================

class TestCodegenInstructions:
    def test_real_arithmetic_uses_float_ops(self, tmp_path):
        src = """\
      PROGRAM T
      REAL X, Y
      X = 1.5
      Y = 2.5
      PRINT *, X + Y
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "FADD" in code, "Adição de REAL deve usar FADD"
        assert "PUSHF" in code, "Literais REAL devem usar PUSHF"


    def test_integer_arithmetic_uses_int_ops(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A, B
      A = 3
      B = 4
      PRINT *, A + B
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "ADD" in code and "FADD" not in code, \
            "Adição de INTEGER deve usar ADD, não FADD"


    def test_logical_true_is_pushi_1(self, tmp_path):
        src = """\
      PROGRAM T
      LOGICAL F
      F = .TRUE.
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "PUSHI 1" in code, ".TRUE. deve ser representado como PUSHI 1"


    def test_logical_false_is_pushi_0(self, tmp_path):
        src = """\
      PROGRAM T
      LOGICAL F
      F = .FALSE.
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "PUSHI 0" in code, ".FALSE. deve ser representado como PUSHI 0"


    def test_string_concat_uses_concat(self, tmp_path):
        src = """\
      PROGRAM T
      PRINT *, 'A' // 'B'
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "CONCAT" in code, "Concatenação // deve usar instrução CONCAT"


    def test_not_operator(self, tmp_path):
        src = """\
      PROGRAM T
      LOGICAL B
      B = .NOT. .TRUE.
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "NOT" in code, ".NOT. deve emitir instrução NOT"


    def test_array_alloc(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A(10)
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "ALLOC 10" in code, "Array de tamanho 10 deve gerar ALLOC 10"


    def test_array_2d_alloc(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER M(3, 4)
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "ALLOC 12" in code, "Array 3x4 deve gerar ALLOC 12"


    def test_function_call_uses_pusha_call(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER R, DOBRO
      R = DOBRO(5)
      END

      INTEGER FUNCTION DOBRO(X)
      INTEGER X
      DOBRO = X * 2
      RETURN
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "PUSHA DOBRO" in code, "Chamada de função deve usar PUSHA + CALL"
        assert "CALL" in code


    def test_do_loop_has_jump(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER I
      DO 10 I = 1, 5
          PRINT *, I
  10  CONTINUE
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "JUMP" in code, "DO loop deve conter instrução JUMP"
        assert "INFEQ" in code or "SUPEQ" in code, \
            "DO loop deve conter comparação de limite"


    def test_itof_on_mixed_arithmetic(self, tmp_path):
        src = """\
      PROGRAM T
      REAL X
      INTEGER N
      N = 3
      X = N + 1.5
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "ITOF" in code, \
            "Expressão INTEGER+REAL deve promover INTEGER com ITOF"


    def test_power_constant_exp(self, tmp_path):
        # Expoente constante: codegen usa DUP+MUL inline (sem loop em runtime)
        src = """\
      PROGRAM T
      INTEGER R, A
      A = 3
      R = A ** 4
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "DUP 1" in code, \
            "Potência com expoente constante deve usar DUP+MUL inline"
        assert "ERR" not in code, \
            "Expoente constante não deve cair no caminho de expoente variável"


    def test_ne_operator(self, tmp_path):
        src = """\
      PROGRAM T
      INTEGER A
      LOGICAL R
      A = 5
      R = A .NE. 3
      END
"""
        code = inline_codegen(src, tmp_path)
        assert "EQUAL" in code and "NOT" in code, \
            ".NE. deve ser implementado como EQUAL + NOT"