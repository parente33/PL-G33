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

    if summary:
        print(f"Total de tokens: {len(result)}")
    else:
        for tok in result:
            print(tok)


def execute_parser(path: str):
    result = run_parser(path)
    print_separator(path)

    if result is None:
        print(f"[{path}] Parsing concluído sem output.")
        return
    else:
        print(f"[{path}] AST gerada com suecesso.")
        print(result)


def execute_semantic(path: str, summary: bool):
    analyzer = run_semantic(path)
    print_separator(path)

    if analyzer is None:
        print(f"[{path}] Análise semântica falhou.")
        return

    print(f"[{path}] Análise semântica OK - {len(analyzer.warnings)} aviso(s).")

    if not summary:
        analyzer.print_symbol_table()


def execute_codegen(path: str, output_target: str | None):
    gen, analyzer = run_codegen(path)
    print_separator(path)

    if gen is None:
        print(f"[{path}] Geração de código falhou.", file=sys.stderr)
        return

    code = gen.get_code()

    if output_target:
        # Se o output for uma diretoria, cria um ficheiro lá dentro com o nome original + .txt
        if os.path.isdir(output_target):
            filename = os.path.basename(path).replace(".f", ".txt")
            final_path = os.path.join(output_target, filename)
            mode = 'w' # Em pastas, cada ficheiro tem o seu próprio arquivo, pode ser 'w'
        else:
            final_path = output_target
            mode = 'a' # Num ficheiro único, usamos 'append' para não apagar os anteriores

        with open(final_path, mode) as f:
            if mode == 'a':
                f.write(f"\n# --- CÓDIGO PARA: {path} ---\n")
            f.write(code)
            f.write('\n')
        print(f"[{path}] Código guardado em: {final_path}")
    else:
        print(f"\n========== Código gerado para: {path} ==========")
        print(code)
        print("=" * (30 + len(path)))

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
        "target",
        help="ficheiro fonte Fortran (.f) OU diretoria para testar todos os ficheiros"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="modo resumido"
    )

    parser.add_argument(
        "-o", "--output",
        metavar="OUT",
        default=None,
        help="ficheiro/diretoria de saída para o código gerado (apenas para a fase codegen)"
    )

    return parser

# --------------------------------------------- Main --------------------------------------------- #

def main():
    parser = build_parser()
    args = parser.parse_args()

    if os.path.isdir(args.target):
        files_to_process = sorted(glob.glob(os.path.join(args.target, "*.f")))
    elif os.path.isfile(args.target):
        files_to_process = [args.target]
    else:
        fail(f"Caminho inválido: {args.target}")

    if not files_to_process:
        fail(f"Nenhum ficheiro .f encontrado em: {args.target}")

    print_header(f"Compilador Fortran 77 — PL2026 | Fase: {args.phase.upper()}")

    for filepath in files_to_process:
        try:
            if args.phase == "lex":
                execute_lexer(filepath, args.summary)

            elif args.phase == "parse":
                execute_parser(filepath)

            elif args.phase == "sem":
                execute_semantic(filepath, args.summary)

            elif args.phase == "codegen":
                execute_codegen(filepath, args.output)

        except KeyboardInterrupt:
            fail("\nExecução interrompida pelo utilizador.", 130)

        except Exception as e:
            print(f"Erro em {filepath}: {e}", file=sys.stderr)
            if len(files_to_process) == 1: # Se for apenas um ficheiro, sai com erro
                sys.exit(1)
            # Se forem vários, continua para o próximo

    print("\nConcluído.")


if __name__ == "__main__":
    main()
