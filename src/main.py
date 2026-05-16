import sys, os, argparse, glob
from compiler import run_lexer, run_parser, run_semantic, run_codegen

# --------------------------------------------- Utils --------------------------------------------- #

def fail(message: str, code: int = 1):
    print(f"Erro: {message}", file=sys.stderr)
    sys.exit(code)


def print_header(title: str):
    print("=" * 60)
    print(title)
    print("=" * 60)

def print_separator(filename: str):
    print(f"\n" + "=" * 80)
    print(f"FILE: {filename}")
    print("=" * 80)

# --------------------------------------------- Execução das Fases --------------------------------------------- #

def execute_lexer(path: str, summary: bool):
    result = run_lexer(path)
    print_separator(path)

    if not result:
        print("Nenhum token produzido.")
        return

