import ast
import math

MAX_VALUE = 2**128

def calculator(query: str):
    """A simple calculator. Supports math functions like "sqrt", "cos", etc. Use every time the user asks a math question."""
    if not query:
        return None
    if not isinstance(query, str):
        raise TypeError("Query must be str")
    locals = {x for x in dir(math) if not x.startswith('_')}
    locals = {x: getattr(math, x) for x in locals}
    locals['abs'] = abs
    tree = ast.parse(query, mode='eval')
    
    allowed_nodes = {
        ast.Expression,
        ast.BinOp,
        # literals
        ast.Constant,
        # unary operations
        ast.UnaryOp,
        ast.UAdd,
        ast.USub,
        ast.Invert,
        # math operators
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        # binary operators
        ast.LShift,
        ast.RShift,
        ast.BitOr,
        ast.BitXor,
        ast.BitAnd,
        # comparisions
        ast.Compare,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        # functions
        ast.Call,
        ast.Name,
        ast.Load,
    }

    def _validate(node):
        if type(node) not in allowed_nodes:
            raise ValueError(f"Disallowed operation: {type(node).__name__}")
        
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ValueError(f"Disallowed func type: {type(node.func).__name__}")
        if isinstance(node, ast.Name):
            if node.id not in locals:
                raise ValueError(f"Disallowed function: {node.id}")
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, bool)):
                raise ValueError(f"Disallowed value: {node.value}")
            if isinstance(node.value, (int, float)) and node.value > MAX_VALUE:
                raise ValueError(f"Disallowed value: {node.value}")

        for child in ast.iter_child_nodes(node):
            _validate(child)
    _validate(tree)

    globals = {'__builtins__': None}
    try:
        result = eval(compile(tree, '<unknown>', 'eval'), globals, locals)
    except (ZeroDivisionError, OverflowError):
        result = math.inf
    return result

if __name__ == "__main__":
    while True:
        try:
            print(calculator(input("> ")))
        except (ValueError, SyntaxError, TypeError) as e:
            print(e)