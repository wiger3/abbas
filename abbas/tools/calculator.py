import ast
import math
import operator

MAX_POW = 128

MAX_VALUE = 2**MAX_POW
MAX_LSHIFT = MAX_POW-1

def _get_max_factorial():
    a = 2
    for i in range(2, MAX_POW):
        if a >= MAX_VALUE:
            break
        a *= i
    return i-1
MAX_FACTORIAL = _get_max_factorial()

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

    ops = {
        ast.UAdd: operator.pos,
        ast.USub: operator.neg,
        ast.Invert: operator.invert,
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.LShift: operator.lshift,
        ast.RShift: operator.rshift,
        ast.BitOr: operator.or_,
        ast.BitXor: operator.xor,
        ast.BitAnd: operator.and_,
        ast.Compare: operator.eq,
        ast.NotEq: operator.ne,
        ast.Lt: operator.lt,
        ast.LtE: operator.le,
        ast.Gt: operator.gt,
        ast.GtE: operator.ge
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

        for child in ast.iter_child_nodes(node):
            _validate(child)
    _validate(tree)

    def _evaluate(node):
        if isinstance(node, ast.Constant):
            result = node.value
        elif isinstance(node, ast.Name):
            result = locals[node.id]
        elif isinstance(node, ast.Expression):
            result = _evaluate(node.body)
        elif isinstance(node, ast.Call):
            target = node.func.id
            args = tuple(_evaluate(x) for x in node.args)
            kwargs = {x.arg: _evaluate(x.value) for x in node.keywords}
            
            if target == 'factorial':
                if args[0] > MAX_FACTORIAL:
                    raise OverflowError
            if target == 'comb' or target == 'perm':
                if (target == 'comb' and len(args) == 2
                    or target == 'perm' and 1 <= len(args) <= 2):

                    if len(args) >= 2 and args[1] > args[0]:
                        return 0
                    if any(x > MAX_FACTORIAL for x in args):
                        raise OverflowError

            globals = {'__builtins__': None}
            locals_ = locals.copy()
            locals_.update({'target': locals[target], 'args': args, 'kwargs': kwargs})
            
            # call in sandbox
            result = eval("target(*args, **kwargs)", globals, locals_)
        elif isinstance(node, ast.UnaryOp):
            operator = ops[type(node.op)]
            operand = _evaluate(node.operand)
            result = operator(operand)
        elif isinstance(node, ast.BinOp):
            operator = ops[type(node.op)]
            left = _evaluate(node.left)
            right = _evaluate(node.right)

            if isinstance(node.op, ast.Pow):
                if abs(left) > MAX_POW or abs(right) > MAX_POW:
                    raise OverflowError
            if isinstance(node.op, ast.LShift):
                if right > MAX_LSHIFT:
                    raise OverflowError

            result = operator(left, right)
        else:
            raise ValueError(f"Invalid ast node? {type(node).__name__}")
        
        if abs(result) > MAX_VALUE:
            raise OverflowError
        return result
    
    try:
        result = _evaluate(tree)
    except (ZeroDivisionError, OverflowError):
        result = math.inf
    return result

if __name__ == "__main__":
    while True:
        try:
            print(calculator(input("> ")))
        except (ValueError, SyntaxError, TypeError) as e:
            print(e)