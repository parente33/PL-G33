from lexer import tokenize_file
from parser import parse_file
from semantic import run_semantic as _run_semantic, SemanticAnalyzer
from codegen import run_codegen as _run_codegen, CodeGenerator

def run_lexer(path):
    return tokenize_file(path)

def run_parser(path):
    return parse_file(path)

def run_semantic(path):
    tree = parse_file(path)
    if tree is None:
        return None
    return _run_semantic(tree)

def run_codegen(path) -> tuple:
    """
    Executa todas as fases (lex -> parse -> sem -> codegen).
    Devolve (CodeGenerator, SemanticAnalyzer) ou (None, None) em caso de erro.
    """
    tree = parse_file(path)
    if tree is None:
        return None, None

    analyzer = _run_semantic(tree)
    if analyzer is None:
        return None, None

    gen = _run_codegen(tree, analyzer)
    return gen, analyzer
