from lexer import tokenize_file
from parser import parse_file
# from semantic import ...
# from codegen import ...

def run_lexer(path):
    return tokenize_file(path)

def run_parser(path):
    return parse_file(path)

# ...