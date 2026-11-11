"""Mathematical verification for generated MCQs.

For a numeric question, the model provides a calculation from the question stem alone (without
seeing the options, the key, or the explanation):

  1. Simple calculations are parsed and evaluated directly by a restricted AST mathematical
     expression evaluator (eval_math_expression / try_eval_math_program) with zero eval()/exec().
  2. Multi-step calculations requiring Python code execution (loops, collections, fractions...)
     run only inside an isolated worker process enforcing OS memory, CPU, process, UI, and timeout
     limits (Linux/macOS setrlimit + netns when allowed; Windows Job Object). Arbitrary model
     code is NEVER executed without isolation. If safe verification is unavailable, math_check fails
     closed.

Statuses:
    not_math      no computation needed (fewer than 3 numeric options); accepted, model not called
    verified      computed result matches only the keyed option; accepted
    wrong_key     computed result matches a different single option; rejected
    no_match      computed result matches no option; rejected
    ambiguous     computed result matches multiple options or returned multiple values; rejected
    unsupported   model output used unsupported/blocked syntax or bounds; rejected
    unchecked     verification worker timed out, was unavailable, or failed to run; rejected unless allow_unchecked=True
"""
import ast
import math
import operator
import os
import re
import shutil
import subprocess
import sys
import tempfile

LETTERS = "ABCD"
NUM = r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?"
TOL = 0.02                                    # 2% relative tolerance, the same as numcheck.py

SOLVER_SYSTEM = "You are a careful engineering professor who solves numeric problems with Python."
SOLVER_USER = """Solve this exam question with a short calculation.

Question: {question}

Rules:
- Compute the answer step by step from the numbers in the question. Prefer a direct mathematical expression; use only the math module if needed.
- Store the final answer in a variable named answer. Use a plain number in the unit the question asks for
  (for a percentage, store the percentage, like 60 for 60%). For a bit pattern or code, store a string like "0001".
- If the question needs no calculation, write exactly: answer = None
- Reply with only the code in one ```python block."""

ALLOWED_IMPORTS = {"math", "cmath", "fractions", "decimal", "statistics", "itertools"}
BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
                 "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
                 "__builtins__", "os", "sys", "subprocess"}

# Strictly pure scalar mathematical constants and functions for Tier 1 expression parsing (no exec/eval).
SAFE_MATH_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

def _safe_factorial(n):
    if isinstance(n, bool) or not isinstance(n, int) or n < 0 or n > 170:
        raise ValueError("factorial argument out of safe bounds")
    return math.factorial(n)

def _safe_comb(n, k):
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (n, k)) or not (0 <= n <= 1000 and 0 <= k <= 1000):
        raise ValueError("comb arguments out of safe bounds")
    return math.comb(n, k)

def _safe_perm(n, k=None):
    k_val = n if k is None else k
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (n, k_val)) or not (0 <= n <= 1000 and 0 <= k_val <= 1000):
        raise ValueError("perm arguments out of safe bounds")
    return math.perm(n) if k is None else math.perm(n, k)

def _safe_exp(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x > 709:
        raise ValueError("exp argument out of safe bounds")
    return math.exp(x)

def _safe_pow(base, exp):
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (base, exp)):
        raise ValueError("pow requires real numbers")
    if not (math.isfinite(base) and math.isfinite(exp)):
        raise ValueError("non-finite operand")
    if abs(exp) > 1000:
        raise ValueError("exponent too large")
    if abs(exp) > 10 and abs(base) > 1e6:
        raise ValueError("exponent too large")
    if isinstance(base, int) and isinstance(exp, int) and exp >= 0:
        if max(1, abs(base).bit_length()) * exp > 4096:
            raise ValueError("exponent too large")
    res = base ** exp
    if isinstance(res, complex):
        raise ValueError("complex numbers are not supported")
    if isinstance(res, int) and res.bit_length() > 4096:
        raise ValueError("integer result too large")
    if isinstance(res, float) and not math.isfinite(res):
        raise ValueError("non-finite result")
    return res

def _safe_float(x):
    if isinstance(x, bool):
        raise ValueError("bool is not supported")
    if isinstance(x, str):
        if len(x) > 32:
            raise ValueError("string too long for float")
        v = float(x)
    elif isinstance(x, (int, float)):
        v = float(x)
    else:
        raise ValueError("unsupported float argument")
    if not math.isfinite(v):
        raise ValueError("non-finite float")
    return v

def _safe_int(x):
    if isinstance(x, bool):
        raise ValueError("bool is not supported")
    if isinstance(x, str) and len(x) > 32:
        raise ValueError("string too long for int")
    v = int(x)
    if v.bit_length() > 4096:
        raise ValueError("integer result too large")
    return v

def _safe_minmax(fn):
    def _wrap(*args):
        if not args or len(args) > 16:
            raise ValueError("wrong number of arguments")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in args):
            raise ValueError("numeric arguments required")
        return fn(args)
    return _wrap

def _safe_round(x, ndigits=None):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("round requires a number")
    if ndigits is None:
        return round(x)
    if isinstance(ndigits, bool) or not isinstance(ndigits, int) or abs(ndigits) > 100:
        raise ValueError("invalid round precision")
    return round(x, ndigits)

def _safe_abs(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("abs requires a number")
    return abs(x)

def _num1(fn):
    def _wrap(x):
        if isinstance(x, bool) or not isinstance(x, (int, float)):
            raise ValueError("numeric argument required")
        v = fn(x)
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("non-finite result")
        return v
    return _wrap

def _num2(fn):
    def _wrap(a, b):
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (a, b)):
            raise ValueError("numeric arguments required")
        v = fn(a, b)
        if isinstance(v, float) and not math.isfinite(v):
            raise ValueError("non-finite result")
        return v
    return _wrap

def _int_fn(fn):
    def _wrap(*args):
        if not args or len(args) > 8:
            raise ValueError("invalid integer arguments")
        if any(isinstance(x, bool) or not isinstance(x, int) or x.bit_length() > 1024 for x in args):
            raise ValueError("bounded integer arguments required")
        return fn(*args)
    return _wrap

SAFE_MATH_FUNCS = {
    "sqrt": _num1(math.sqrt),
    "cbrt": _num1(math.cbrt),
    "exp": _safe_exp,
    "expm1": _num1(math.expm1),
    "log": lambda *a: _num1(math.log)(*a) if len(a) == 1 else (_num2(math.log)(*a) if len(a) == 2 else (_ for _ in ()).throw(ValueError("log takes 1 or 2 arguments"))),
    "log2": _num1(math.log2),
    "log10": _num1(math.log10),
    "log1p": _num1(math.log1p),
    "sin": _num1(math.sin),
    "cos": _num1(math.cos),
    "tan": _num1(math.tan),
    "asin": _num1(math.asin),
    "acos": _num1(math.acos),
    "atan": _num1(math.atan),
    "atan2": _num2(math.atan2),
    "sinh": _num1(math.sinh),
    "cosh": _num1(math.cosh),
    "tanh": _num1(math.tanh),
    "asinh": _num1(math.asinh),
    "acosh": _num1(math.acosh),
    "atanh": _num1(math.atanh),
    "floor": _num1(math.floor),
    "ceil": _num1(math.ceil),
    "trunc": _num1(math.trunc),
    "fabs": _num1(math.fabs),
    "fmod": _num2(math.fmod),
    "remainder": _num2(math.remainder),
    "hypot": _num2(math.hypot),
    "degrees": _num1(math.degrees),
    "radians": _num1(math.radians),
    "copysign": _num2(math.copysign),
    "gcd": _int_fn(math.gcd),
    "lcm": _int_fn(math.lcm),
    "isqrt": lambda n: math.isqrt(n) if (not isinstance(n, bool) and isinstance(n, int) and 0 <= n and n.bit_length() <= 1024) else (_ for _ in ()).throw(ValueError("isqrt requires non-negative bounded int")),
    "factorial": _safe_factorial,
    "comb": _safe_comb,
    "perm": _safe_perm,
}

SAFE_BUILTIN_MATH_FUNCS = {
    "abs": _safe_abs,
    "round": _safe_round,
    "min": _safe_minmax(min),
    "max": _safe_minmax(max),
    "pow": _safe_pow,
    "int": _safe_int,
    "float": _safe_float,
}


# ---------- reading numbers out of options ----------

def option_value(o):
    """'15 km' -> 15.0, '60%' -> 60.0, '1/4' -> 0.25, '0001' -> 1.0, '10 - 20 km' -> None, 'Deadlock' -> None."""
    s = o.replace(",", "").strip()
    if re.search(r"\b(?:or|to|and)\b", s, re.I) or re.search(r"(?:\+/-|±)", s):
        return None
    if re.search(r"\d\s*[-–]\s*\d", s) or re.search(r"\d\s*\^\s*-?\d", s):
        return None
    unit = r"(?:\s*(?:[a-zA-Z%°Ωμ]+(?:\s*/\s*[a-zA-Z%°Ωμ]+)*(?:\^-?\d+)?(?:\s+[a-zA-Z%°Ωμ]+(?:\^-?\d+)?){0,2}))?"
    m = re.fullmatch(r"(?:about |approximately |approx\. |~|≈)?(" + NUM + r")\s*(?:/\s*(" + NUM + r"))?" + unit, s, re.I)
    if not m:
        return None
    try:
        v = float(m.group(1))
        return v / float(m.group(2)) if m.group(2) else v
    except (ValueError, ZeroDivisionError):
        return None


def is_bits(o):
    return re.fullmatch(r"[01]{2,}", o.strip()) is not None


def needs_math(mcq):
    opts = mcq["options"]
    return sum(option_value(o) is not None for o in opts) >= 3 or sum(is_bits(o) for o in opts) >= 3


# ---------- Layer 1 & Layer 2 calculation engine ----------

class _NeedsWorker(Exception):
    """Raised when statically checked Python code legitimately needs isolated worker execution."""


class _ExprError(Exception):
    """Raised when an expression violates mathematical safety bounds or uses disallowed operations."""


_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_INT_BIT_OPS = {
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}
SAFE_BUILTINS = ["abs", "all", "any", "bin", "bool", "complex", "dict", "divmod", "enumerate", "filter",
                 "float", "format", "frozenset", "hex", "int", "isinstance", "len", "list", "map", "max", "min",
                 "oct", "pow", "print", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str",
                 "sum", "tuple", "zip", "ArithmeticError", "Exception", "OverflowError", "TypeError",
                 "ValueError", "ZeroDivisionError"]
_WORKER_BUILTINS = set(SAFE_BUILTINS) - set(SAFE_BUILTIN_MATH_FUNCS)
_WORKER_MODULES = ALLOWED_IMPORTS - {"math"}
_WORKER_AST_NODES = (
    ast.For, ast.FunctionDef, ast.Return, ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Subscript,
    ast.AugAssign, ast.If, ast.IfExp, ast.Compare, ast.BoolOp, ast.Lambda,
    ast.Delete, ast.Break, ast.Continue, ast.Pass, ast.Try, ast.Raise,
)

MAX_EXPR_CHARS = 4096
MAX_STATEMENTS = 30
MAX_AST_NODES = 250
MAX_AST_DEPTH = 24


def _check_finite_real(v):
    if isinstance(v, complex):
        raise _ExprError("complex numbers are not supported")
    if isinstance(v, float) and not math.isfinite(v):
        raise _ExprError("non-finite result")
    if isinstance(v, int) and not isinstance(v, bool) and v.bit_length() > 4096:
        raise _ExprError("integer result too large")
    return v


def _eval_node(node, env: dict, math_aliases: set[str], imported_math: dict, depth: int = 0):
    if depth > MAX_AST_DEPTH:
        raise _ExprError("unsupported expression: nesting too deep")

    if isinstance(node, ast.Constant):
        v = node.value
        if v is None or isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            if isinstance(v, float) and not math.isfinite(v):
                raise _ExprError("non-finite constant")
            if isinstance(v, int) and v.bit_length() > 1024:
                raise _ExprError("integer constant too large")
            return v
        if isinstance(v, str):
            if len(v) > 64:
                raise _ExprError("string constant too long")
            return v
        raise _ExprError(f"unsupported constant type: {type(v).__name__}")

    if isinstance(node, ast.Name):
        ident = node.id
        if ident in env:
            return env[ident]
        if ident in imported_math:
            val = imported_math[ident]
            if callable(val):
                raise _ExprError(f"unsupported expression: bare function {ident}")
            return val
        if ident in SAFE_MATH_CONSTANTS:
            return SAFE_MATH_CONSTANTS[ident]
        if ident in ("True", "False", "None"):
            return {"True": True, "False": False, "None": None}[ident]
        if ident in _WORKER_BUILTINS or ident in _WORKER_MODULES:
            raise _NeedsWorker(ident)
        raise _ExprError(f"unsupported expression: unknown name {ident}")

    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id in math_aliases:
            if node.attr in SAFE_MATH_CONSTANTS:
                return SAFE_MATH_CONSTANTS[node.attr]
            raise _ExprError(f"unsupported expression: math.{node.attr}")
        if isinstance(node.value, ast.Name) and (node.value.id in env or node.value.id in _WORKER_MODULES):
            raise _NeedsWorker(node.attr)
        raise _ExprError("unsupported expression: attribute access")

    if isinstance(node, ast.UnaryOp):
        val = _eval_node(node.operand, env, math_aliases, imported_math, depth + 1)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise _ExprError("unary operator requires a real number")
        if isinstance(node.op, ast.UAdd):
            return +val
        if isinstance(node.op, ast.USub):
            return -val
        if isinstance(node.op, ast.Invert):
            if not isinstance(val, int):
                raise _ExprError("bitwise invert requires an integer")
            return ~val
        raise _ExprError(f"unsupported unary operator: {type(node.op).__name__}")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, env, math_aliases, imported_math, depth + 1)
        right = _eval_node(node.right, env, math_aliases, imported_math, depth + 1)
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in (left, right)):
            raise _ExprError("unsupported expression: binary operation requires real numbers")
        op_type = type(node.op)
        if op_type is ast.Pow:
            try:
                return _safe_pow(left, right)
            except ValueError as e:
                raise _ExprError(str(e)) from e
        if op_type in _INT_BIT_OPS:
            if not (isinstance(left, int) and isinstance(right, int)):
                raise _ExprError("bitwise operation requires integers")
            if op_type in (ast.LShift, ast.RShift) and (right < 0 or right > 512):
                raise _ExprError("bit shift out of safe bounds")
            return _check_finite_real(_INT_BIT_OPS[op_type](left, right))
        if op_type in _BIN_OPS:
            try:
                res = _BIN_OPS[op_type](left, right)
            except ZeroDivisionError as e:
                raise _ExprError("division by zero") from e
            except OverflowError as e:
                raise _ExprError("math overflow") from e
            return _check_finite_real(res)
        raise _ExprError(f"unsupported operator: {op_type.__name__}")

    if isinstance(node, ast.Call):
        if node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
            if isinstance(node.func, ast.Name) and node.func.id in _WORKER_BUILTINS:
                raise _NeedsWorker(node.func.id)
            raise _ExprError("unsupported expression: keyword or starred arguments")
        fn = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            mod = node.func.value.id
            if mod in math_aliases:
                fn = SAFE_MATH_FUNCS.get(node.func.attr)
                if fn is None:
                    raise _ExprError(f"unsupported expression: math.{node.func.attr}")
            elif mod in _WORKER_MODULES or mod in env:
                raise _NeedsWorker(f"{mod}.{node.func.attr}")
            else:
                raise _ExprError(f"unsupported expression: {mod}.{node.func.attr}")
        elif isinstance(node.func, ast.Name):
            name = node.func.id
            if name in imported_math:
                candidate = imported_math[name]
                if callable(candidate):
                    fn = candidate
            elif name in SAFE_BUILTIN_MATH_FUNCS:
                fn = SAFE_BUILTIN_MATH_FUNCS[name]
            elif name in _WORKER_BUILTINS:
                raise _NeedsWorker(name)
            else:
                raise _ExprError(f"unsupported expression: call to {name}")
        else:
            raise _ExprError("unsupported expression: dynamic call")
        if fn is None:
            raise _ExprError("unsupported function call")
        args = [_eval_node(a, env, math_aliases, imported_math, depth + 1) for a in node.args]
        try:
            return _check_finite_real(fn(*args))
        except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
            raise _ExprError(str(e)) from e

    if isinstance(node, _WORKER_AST_NODES):
        raise _NeedsWorker(type(node).__name__)
    raise _ExprError(f"unsupported expression node: {type(node).__name__}")


def extract_code(text):
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (m.group(1) if m else text).strip()


def check_code(code):
    """Return None if the code is safe to run, else the reason it is refused."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"syntax error: {e.msg}"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad = [a.name for a in node.names if a.name.split(".")[0] not in ALLOWED_IMPORTS]
            if bad:
                return f"import not allowed: {bad}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                return f"import not allowed: {node.module}"
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            return f"name not allowed: {node.id}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"attribute not allowed: {node.attr}"
        elif isinstance(node, (ast.While, ast.AsyncFunctionDef, ast.Global, ast.Nonlocal)):
            return f"{type(node).__name__} not allowed"
    if not any(isinstance(n, ast.Name) and n.id == "answer" and isinstance(n.ctx, ast.Store) for n in ast.walk(tree)):
        return "no answer variable"
    return None


def eval_math_expression(expr: str, variables: dict | None = None):
    """Evaluate one standalone mathematical expression safely without eval()/exec().
    Returns (value, error). Uses strict AST depth/node/domain limits."""
    src = (expr or "").strip()
    if not src or len(src) > MAX_EXPR_CHARS:
        return None, "unsupported expression: empty or too large"
    try:
        tree = ast.parse(src, mode="eval")
    except SyntaxError as e:
        return None, f"syntax error: {e.msg}"
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        return None, "unsupported expression: too complex"
    try:
        val = _eval_node(tree.body, dict(variables or {}), {"math"}, {})
        return val, None
    except (_ExprError, _NeedsWorker) as e:
        msg = str(e)
        return None, msg if "unsupported" in msg or "exponent" in msg or "bounds" in msg or "division" in msg or "overflow" in msg or "complex" in msg or "constant" in msg or "finite" in msg else f"unsupported expression: {msg}"


def try_eval_math_program(code: str) -> tuple[bool, object, str | None]:
    """Tier 1 calculation path: restricted AST evaluator for simple scalar math assignments.

    Returns (handled, value, error):
      - handled=True, error=None     -> verified safely without spawning any Python process
      - handled=True, error!=None    -> unsafe, invalid, or violated expression bounds (do NOT run in worker)
      - handled=False                -> valid statically checked Python needing isolated Tier 2 worker
    """
    reason = check_code(code)
    if reason:
        return True, None, reason
    if len(code) > MAX_EXPR_CHARS:
        return True, None, "unsupported expression: program too large"
    tree = ast.parse(code)
    if len(tree.body) > MAX_STATEMENTS or sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        return True, None, "unsupported expression: program too complex"

    env: dict = {}
    math_aliases: set[str] = {"math"}
    imported_math: dict = {}

    try:
        for stmt in tree.body:
            if isinstance(stmt, ast.Import):
                for alias in stmt.names:
                    top = alias.name.split(".")[0]
                    if top == "math":
                        math_aliases.add(alias.asname or "math")
                    elif top in _WORKER_MODULES:
                        raise _NeedsWorker(top)
                    else:
                        raise _ExprError(f"import not allowed: {alias.name}")
            elif isinstance(stmt, ast.ImportFrom):
                mod = (stmt.module or "").split(".")[0]
                if mod == "math":
                    for alias in stmt.names:
                        if alias.name == "*":
                            raise _NeedsWorker("import *")
                        sym = alias.name
                        val = SAFE_MATH_FUNCS.get(sym) if sym in SAFE_MATH_FUNCS else SAFE_MATH_CONSTANTS.get(sym)
                        if val is None:
                            raise _ExprError(f"unsupported expression: math.{sym}")
                        imported_math[alias.asname or sym] = val
                elif mod in _WORKER_MODULES:
                    raise _NeedsWorker(mod)
                else:
                    raise _ExprError(f"import not allowed: {stmt.module}")
            elif isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                    raise _NeedsWorker("multi-target or structured assignment")
                target = stmt.targets[0].id
                if target.startswith("_") or target in ("None", "True", "False"):
                    raise _ExprError(f"name not allowed: {target}")
                env[target] = _eval_node(stmt.value, env, math_aliases, imported_math, depth=0)
            else:
                raise _NeedsWorker(type(stmt).__name__)
    except _NeedsWorker:
        return False, None, "requires worker"
    except _ExprError as e:
        return True, None, str(e)

    if "answer" not in env:
        return True, None, "no answer variable"
    return True, env["answer"], None


# The isolated Tier 2 worker runs behind independent defence-in-depth layers:
#   1. static check        check_code() refuses imports outside ALLOWED_IMPORTS, dangerous names,
#                          "_" attributes (blocks __class__/__subclasses__ escapes), and while loops
#   2. restricted builtins child executes with a strict builtins allowlist (no open, eval, getattr...)
#                          and an import hook restricting imports to ALLOWED_IMPORTS
#   3. separate process    fresh `python -I -S -B` inside an empty temporary folder, minimal env,
#                          no stdin, killed after `timeout` seconds of wall time
#   4. OS resource limits  (Linux/macOS) 512 MB AS, 5 s CPU, RLIMIT_FSIZE 0, 32 open files;
#                          (Windows) kernel Job Object assigned BEFORE thread resume enforcing 512 MB
#                          process/job memory, 5 s per-process user CPU limit, ActiveProcessLimit=1
#                          (blocks subprocesses/fork bombs), UI handle restrictions & KILL_ON_JOB_CLOSE
#   5. no network          (Linux, when unprivileged userns/netns is permitted) `unshare -rn`

RUNNER = """
import builtins, sys
ALLOWED = %(allowed)r
_real_import = builtins.__import__
def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0 or name.split('.')[0] not in ALLOWED:
        raise ImportError('import not allowed: ' + name)
    return _real_import(name, globals, locals, fromlist, level)
safe = {k: getattr(builtins, k) for k in %(safe)r}
safe['__import__'] = _guarded_import
src = open('solve.py', encoding='utf-8').read()
code = compile(src, 'solve.py', 'exec')
ns = {'__builtins__': safe, '__name__': '__solve__'}
exec(code, ns)
sys.stdout.write('__ANSWER__=' + repr(ns.get('answer')) + '\\n')
"""


def _limits():                                # Linux/macOS, applied in the child just before it starts
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))


_NETNS = None
_WIN_JOB_OK = None


def _netns_prefix() -> list[str]:
    """['unshare', '-rn'] when this Linux machine lets an ordinary process drop its network, else []."""
    global _NETNS
    if _NETNS is None:
        _NETNS = []
        if sys.platform.startswith("linux") and shutil.which("unshare"):
            try:
                ok = subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=5).returncode == 0
                _NETNS = ["unshare", "-rn"] if ok else []
            except (OSError, subprocess.SubprocessError):
                _NETNS = []
    return _NETNS


def _win32_job_api():
    """Bind kernel32 Job Object and suspended-thread-resume Win32 APIs with explicit 64-bit HANDLE types."""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                    ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                    ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class JOBOBJECT_BASIC_UI_RESTRICTIONS(ctypes.Structure):
        _fields_ = [("UIRestrictionsClass", wintypes.DWORD)]

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.SetInformationJobObject.restype = wintypes.BOOL
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.AssignProcessToJobObject.restype = wintypes.BOOL
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.TerminateJobObject.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    k32.Thread32First.restype = wintypes.BOOL
    k32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    k32.Thread32Next.restype = wintypes.BOOL
    k32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenThread.restype = wintypes.HANDLE
    k32.ResumeThread.argtypes = [wintypes.HANDLE]
    k32.ResumeThread.restype = wintypes.DWORD
    return (k32, ctypes, wintypes, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
            JOBOBJECT_BASIC_UI_RESTRICTIONS, THREADENTRY32)


def _create_windows_job(k32, ctypes, ext_cls, ui_cls, timeout: int):
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError("CreateJobObjectW failed")
    try:
        info = ext_cls()
        info.BasicLimitInformation.LimitFlags = (
            0x00000002          # JOB_OBJECT_LIMIT_PROCESS_TIME
            | 0x00000008        # JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | 0x00000100        # JOB_OBJECT_LIMIT_PROCESS_MEMORY
            | 0x00000200        # JOB_OBJECT_LIMIT_JOB_MEMORY
            | 0x00002000        # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.BasicLimitInformation.PerProcessUserTimeLimit = min(max(int(timeout), 1), 5) * 10_000_000
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = 512 * 1024 * 1024
        info.JobMemoryLimit = 512 * 1024 * 1024
        if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(f"SetInformationJobObject(ExtendedLimit) failed: {ctypes.get_last_error()}")

        ui = ui_cls()
        ui.UIRestrictionsClass = 0xFF           # HANDLES | CLIPBOARD | SYSTEMPARAMETERS | DISPLAYSETTINGS | GLOBALATOMS | DESKTOP | EXITWINDOWS
        if not k32.SetInformationJobObject(job, 4, ctypes.byref(ui), ctypes.sizeof(ui)):
            raise OSError(f"SetInformationJobObject(UIRestrictions) failed: {ctypes.get_last_error()}")
        return job
    except Exception:
        k32.CloseHandle(job)
        raise


def _windows_job_available() -> bool:
    global _WIN_JOB_OK
    if os.name != "nt":
        return False
    if _WIN_JOB_OK is None:
        try:
            k32, ctypes, _, ext_cls, ui_cls, _ = _win32_job_api()
            job = _create_windows_job(k32, ctypes, ext_cls, ui_cls, timeout=5)
            k32.CloseHandle(job)
            _WIN_JOB_OK = True
        except Exception:
            _WIN_JOB_OK = False
    return _WIN_JOB_OK


def _worker_executable() -> str:
    """Resolve the direct python.exe binary on Windows so venv shims do not trip ActiveProcessLimit=1."""
    if os.name == "nt":
        base = getattr(sys, "_base_executable", None)
        if base and os.path.exists(base):
            return base
    return sys.executable


def _run_windows_isolated(cmd: list[str], cwd: str, env: dict, timeout: int):
    k32, ctypes, wintypes, ext_cls, ui_cls, te_cls = _win32_job_api()
    job = _create_windows_job(k32, ctypes, ext_cls, ui_cls, timeout=timeout)
    p = None
    try:
        p = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            stdin=subprocess.DEVNULL, env=env,
            creationflags=0x00000004 | 0x08000000,   # CREATE_SUSPENDED | CREATE_NO_WINDOW
        )
        if not k32.AssignProcessToJobObject(job, wintypes.HANDLE(int(p._handle))):
            p.kill()
            p.communicate()
            raise OSError(f"AssignProcessToJobObject failed: {ctypes.get_last_error()}")

        snap = k32.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snap == wintypes.HANDLE(-1).value:
            k32.TerminateJobObject(job, 1)
            p.communicate()
            raise OSError("CreateToolhelp32Snapshot failed")
        resumed = 0
        try:
            te = te_cls()
            te.dwSize = ctypes.sizeof(te)
            ok = k32.Thread32First(snap, ctypes.byref(te))
            while ok:
                if te.th32OwnerProcessID == p.pid:
                    ht = k32.OpenThread(0x0002, False, te.th32ThreadID)  # THREAD_SUSPEND_RESUME
                    if ht:
                        try:
                            if k32.ResumeThread(ht) != 0xFFFFFFFF:
                                resumed += 1
                        finally:
                            k32.CloseHandle(ht)
                ok = k32.Thread32Next(snap, ctypes.byref(te))
        finally:
            k32.CloseHandle(snap)
        if resumed == 0:
            k32.TerminateJobObject(job, 1)
            p.communicate()
            raise OSError("could not resume suspended worker thread")

        try:
            stdout, stderr = p.communicate(timeout=timeout)
            return p.returncode, stdout, stderr, False
        except subprocess.TimeoutExpired:
            k32.TerminateJobObject(job, 1)
            p.communicate()
            return -1, "", "timed out", True
    finally:
        k32.CloseHandle(job)


def has_os_limits() -> bool:
    if os.name == "posix":
        return True
    if os.name == "nt":
        return _windows_job_available()
    return False


def sandbox_layers() -> dict:
    """Which protection layers this machine provides (shown in /api/health and the docs)."""
    return {"static_check": True, "restricted_builtins": True, "separate_process": True,
            "os_limits": has_os_limits(), "no_network": bool(_netns_prefix())}


def can_run_safely(allow_without_os_limits: bool = False) -> bool:
    return has_os_limits() or allow_without_os_limits


def run_code(code, timeout=10, allow_without_os_limits: bool = False, worker_available: bool | None = None):
    """Run statically checked Python code in an isolated worker. Returns (value, error).
    Never executes arbitrary Python without isolation unless allow_without_os_limits is explicitly set."""
    reason = check_code(code)
    if reason:
        return None, reason
    is_safe = can_run_safely(allow_without_os_limits) if worker_available is None else worker_available
    if not is_safe:
        return None, "isolated verification worker unavailable"
    runner = RUNNER % {"allowed": sorted(ALLOWED_IMPORTS), "safe": SAFE_BUILTINS}
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "solve.py"), "w", encoding="utf-8") as f:
            f.write(code)
        with open(os.path.join(d, "runner.py"), "w", encoding="utf-8") as f:
            f.write(runner)
        env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        if os.name == "nt" and not allow_without_os_limits:
            cmd = [_worker_executable(), "-I", "-S", "-B", "runner.py"]
            try:
                rc, stdout, stderr, timed_out = _run_windows_isolated(cmd, d, env, timeout=timeout)
            except OSError:
                return None, "isolated verification worker unavailable"
            if timed_out:
                return None, "timed out"
        elif os.name == "nt":
            cmd = [sys.executable, "-I", "-S", "-B", "runner.py"]
            try:
                r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout,
                                   stdin=subprocess.DEVNULL, env=env)
                rc, stdout, stderr = r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                return None, "timed out"
        else:
            cmd = _netns_prefix() + [sys.executable, "-I", "-S", "-B", "runner.py"]
            try:
                r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout,
                                   stdin=subprocess.DEVNULL, env=env, preexec_fn=_limits)
                rc, stdout, stderr = r.returncode, r.stdout, r.stderr
            except subprocess.TimeoutExpired:
                return None, "timed out"
    m = re.search(r"__ANSWER__=(.*)", stdout)
    if rc != 0 or not m:
        return None, "run error: " + (stderr.strip().splitlines() or ["no output"])[-1][:200]
    try:
        return ast.literal_eval(m.group(1).strip()), None
    except (ValueError, SyntaxError):
        return None, "answer is not a plain value"


def evaluate_math_code(code: str, timeout=10, allow_without_os_limits: bool = False,
                       worker_available: bool | None = None):
    """Evaluate a calculation snippet, preferring Tier 1 AST parser and falling back to Tier 2 worker.
    Returns (value, error, method)."""
    handled, value, err = try_eval_math_program(code)
    if handled:
        return value, err, "expression_parser"
    value, err = run_code(
        code, timeout=timeout, allow_without_os_limits=allow_without_os_limits, worker_available=worker_available,
    )
    return value, err, "isolated_worker"


# ---------- comparing with the options ----------

def close(a, b):
    return abs(a - b) <= TOL * max(abs(a), abs(b), 1e-9)


def _range_bounds(o: str):
    s = o.replace(",", "").strip()
    m = re.fullmatch(r"(" + NUM + r")\s*(?:-|–|to)\s*(" + NUM + r")(?:\s*[a-zA-Z%°Ωμ/]{0,12})?", s, re.I)
    if not m:
        return None
    try:
        lo, hi = float(m.group(1)), float(m.group(2))
        return (lo, hi) if lo < hi else None
    except ValueError:
        return None


def matching_letters(value, options):
    """Letters of every option that equals the computed value."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (list, tuple, set, dict)):
        return []
    if isinstance(value, str):
        v = value.strip().lower()
        hits = [l for l, o in zip(LETTERS, options) if o.strip().lower() == v]
        if hits: return hits
        if re.fullmatch(r"[01]+", v):
            return []                         # a bit pattern must match as text, never as a number
        try: value = float(v)
        except ValueError: return []
    if isinstance(value, complex) or not isinstance(value, (int, float)):
        return []
    value = float(value)
    if not math.isfinite(value):
        return []
    hits = []
    for l, o in zip(LETTERS, options):
        ov = option_value(o)
        if ov is not None and not is_bits(o):
            pct = "%" in o or "percent" in o.lower()
            if close(value, ov) or (pct and close(value * 100, ov)):
                hits.append(l)
            continue
        rb = _range_bounds(o)
        if rb is not None:
            lo, hi = rb
            if lo - TOL * max(abs(lo), 1e-9) <= value <= hi + TOL * max(abs(hi), 1e-9):
                hits.append(l)
    return hits


def _error_kind(err: str) -> str:
    low = err.lower()
    if "worker unavailable" in low:
        return "unavailable"
    if low == "timed out":
        return "timeout"
    if any(t in low for t in (
        "unsupported", "import not allowed", "name not allowed", "attribute not allowed",
        "not allowed", "exponent too large", "integer result too large", "out of safe bounds",
        "complex numbers", "too complex", "nesting too deep", "non-finite", "math overflow",
    )):
        return "unsupported"
    return "runtime"


# ---------- the check ----------

def math_check(mcq, generate, tries=2, allow_unchecked=False, worker_timeout=10,
               allow_without_os_limits: bool = False, worker_available: bool | None = None):
    """generate(messages) -> model text. messages is a chat list of role/content dicts."""
    if not needs_math(mcq):
        return {"status": "not_math", "accept": True}
    messages = [{"role": "system", "content": SOLVER_SYSTEM},
                {"role": "user", "content": SOLVER_USER.format(question=mcq["question"])}]
    errors = []
    kinds = []
    for _ in range(tries):
        code = extract_code(generate(messages))
        value, err, method = evaluate_math_code(
            code, timeout=worker_timeout, allow_without_os_limits=allow_without_os_limits,
            worker_available=worker_available,
        )
        if err:
            errors.append(err)
            kinds.append(_error_kind(err))
            continue
        if value is None:                     # the model says no calculation is needed
            return {"status": "not_math", "accept": True, "code": code, "method": method}
        if isinstance(value, (complex, dict)) or (isinstance(value, float) and not math.isfinite(value)):
            errors.append("complex, dict, or non-finite answer is not supported")
            kinds.append("unsupported")
            continue
        if isinstance(value, (list, tuple, set)):
            return {
                "status": "ambiguous", "accept": False, "method": method, "code": code,
                "note": "calculation produced multiple values",
            }
        hits = matching_letters(value, mcq["options"])
        base = {"value": value, "code": code, "method": method}
        if hits == [mcq["answer"]]:
            return {"status": "verified", "accept": True, **base}
        if len(hits) == 1:
            return {"status": "wrong_key", "accept": False, "correct": hits[0], **base}
        if len(hits) > 1:
            return {"status": "ambiguous", "accept": False, "note": f"several options match: {hits}",
                    "matches": hits, **base}
        return {"status": "no_match", "accept": False, **base}

    if any(k in ("unavailable", "timeout") for k in kinds):
        return {"status": "unchecked", "accept": False, "errors": errors, "error_kinds": kinds}
    if errors and all(k == "unsupported" for k in kinds):
        return {"status": "unsupported", "accept": False, "errors": errors, "error_kinds": kinds}
    return {"status": "unchecked", "accept": allow_unchecked, "errors": errors, "error_kinds": kinds}
