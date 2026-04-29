import sys, os, argparse
from compiler import run_lexer, run_parser # , run_semantic, run_codegen

# --------------------------------------------- Utils --------------------------------------------- #

def fail(message: str, code: int = 1):
    print(f"Erro: {message}", file=sys.stderr)
    sys.exit(code)


def ensure_file_exists(path: str):
    if not os.path.isfile(path):
        fail(f"ficheiro não encontrado: {path}")


def print_header(title: str):
    print("=" * 60)
    print(title)
    print("=" * 60)

# --------------------------------------------- Execução das Fases --------------------------------------------- #

def execute_lexer(path: str, summary: bool):
    result = run_lexer(path)

    if not result:
        print("Nenhum token produzido.")
        return

    if summary:
        print(f"Total de tokens: {len(result)}")
        return

    for tok in result:
        print(tok)


def execute_parser(path: str):
    result = run_parser(path)

    if result is None:
        print("Parsing concluído sem output.")
        return

    print(result)

'''
def execute_semantic(path: str):
    result = run_semantic(path)

    if result is None:
        print("Análise semântica concluída sem output.")
        return

    print(result)


def execute_codegen(path: str):
    result = run_codegen(path)

    if result is None:
        print("Geração de código concluída sem output.")
        return

    print(result)
'''
# --------------------------------------------- Argparse --------------------------------------------- #

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Compilador Fortran 77 — PL2026",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "phase",
        choices=["lex", "parse", "sem", "codegen"],
        help=(
            "fase a executar:\n"
            "  lex      Executa (apenas) o lexer (análise léxica)\n"
            "  parse    Executa o lexer e depois o parser (análise sintática)\n"
            "  sem      Executa o lexer, o parser e depois a análise semântica\n"
            "  codegen  Executa todos os passos da compilação, terminando com a tradução/geração de código"
        )
    )

    parser.add_argument(
        "file",
        help="ficheiro fonte Fortran (.f)"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="modo resumido"
    )

    return parser

# --------------------------------------------- Main --------------------------------------------- #

def main():
    parser = build_parser()
    args = parser.parse_args()

    ensure_file_exists(args.file)

    print_header("Compilador Fortran 77 — PL2026")

    try:
        if args.phase == "lex":
            execute_lexer(args.file, args.summary)


        elif args.phase == "parse":
            execute_parser(args.file)

        '''
        elif args.phase == "sem":
            execute_semantic(args.file)

        elif args.phase == "codegen":
            execute_codegen(args.file)
        '''

    except KeyboardInterrupt:
        fail("execução interrompida", 130)

    except Exception as e:
        fail(str(e), 1)


if __name__ == "__main__":
    main()