import sys
import glob
from collections import Counter

# importar o lexer criado
try:
    from lexer import tokenize_file
except ImportError:
    print("Erro: não foi possível importar 'lexer.py'.")
    sys.exit(1)


def format_token(tok) -> str:
    if tok.type == 'STR_LITERAL':
        val_str = f"'{tok.value}'"
    elif tok.type == 'NEWLINE':
        val_str = '↵'
    else:
        val_str = str(tok.value)

    line_str = f"L{tok.lineno:>4}"
    return f"  {line_str}  {tok.type:<15}  {val_str}"


def print_tokens(tokens: list, verbose: bool = True, summary: bool = False):
    if verbose:
        print("\nLINHA  TIPO             VALOR")
        print("  " + "─" * 55)
        for tok in tokens:
            print(format_token(tok))

    if summary or not verbose:
        print()
        counts = Counter(tok.type for tok in tokens)
        total = len(tokens)
        print(f"Resumo: {total} tokens")
        print("  " + "─" * 40)
        for token_type, count in sorted(counts.items(), key=lambda x: -x[1]):
            bar = '█' * min(count, 30)
            print(f"  {token_type:<15}  {count:>4}  {bar}")


# Testar um único ficheiro
def test_file(path: str, verbose: bool, summary: bool) -> bool:
    print()
    print("=" * 60)
    print(f"Ficheiro: {path}")
    print("=" * 60)

    try:
        tokens = tokenize_file(path)
    except FileNotFoundError:
        print(f"Erro: ficheiro não encontrado: {path}")
        return False
    except Exception as e:
        print(f"Erro inesperado: {e}")
        return False

    if not tokens:
        print("Aviso: nenhum token produzido")
        return True

    print_tokens(tokens, verbose=verbose, summary=summary)
    return True


def main():
    print("\nLexer Fortran 77 — PL2026")

    paths = glob.glob("tests/**/*", recursive=True)
    paths = [p for p in paths if not p.endswith("/")]

    if not paths:
        print("Nenhum ficheiro encontrado em tests/")
        sys.exit(1)

    all_ok = True
    for path in paths:
        ok = test_file(path, verbose=True, summary=True)
        all_ok = all_ok and ok

    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()