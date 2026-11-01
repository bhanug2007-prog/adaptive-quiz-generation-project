"""Python maths check for generated MCQs.

For a numeric question, the model writes a short Python program that computes the answer from the
question alone (it never sees the options, the key or the explanation). The program runs in a
separate, locked-down Python process, and the result is compared with the keyed option.

    from mathcheck import math_check
    res = math_check(mcq, generate)        # mcq = parse_mcq(...) dict, generate(messages) -> str
    if res["accept"]: save it  else: regenerate

Statuses:
    not_math      no computation needed (fewer than 3 numeric options); accepted, model not called
    verified      Python result matches the keyed option; accepted
    wrong_key     Python result matches a different option; rejected
    no_match      Python result matches no option; rejected
    unchecked     model gave no usable program twice; rejected unless allow_unchecked=True
"""
import ast
import os
import re
import subprocess
import sys
import tempfile

LETTERS = "ABCD"
NUM = r"-?\d+(?:\.\d+)?(?:[eE]-?\d+)?"
TOL = 0.02                                    # 2% relative tolerance, the same as numcheck.py

SOLVER_SYSTEM = "You are a careful engineering professor who solves numeric problems with Python."
SOLVER_USER = """Solve this exam question with a short Python program.

Question: {question}

Rules:
- Compute the answer step by step from the numbers in the question. Use only the math module if needed.
- Store the final answer in a variable named answer. Use a plain number in the unit the question asks for
  (for a percentage, store the percentage, like 60 for 60%). For a bit pattern or code, store a string like "0001".
- If the question needs no calculation, write exactly: answer = None
- Reply with only the code in one ```python block."""

ALLOWED_IMPORTS = {"math", "cmath", "fractions", "decimal", "statistics", "itertools"}
BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
                 "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
                 "__builtins__", "os", "sys", "subprocess"}


# ---------- reading numbers out of options ----------

def option_value(o):
    """'15 km' -> 15.0, '60%' -> 60.0, '1/4' -> 0.25, '0001' -> 1.0, 'Deadlock' -> None."""
    o = o.replace(",", "").strip()
    m = re.fullmatch(r"(?:about |approximately |approx\. |~|≈)?(" + NUM + r")\s*(?:/\s*(" + NUM + r"))?"
                     r"\s*[a-zA-Z%°Ωμ/ ^0-9.-]{0,14}", o, re.I)
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


# ---------- running the model's program safely ----------

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
            if bad: return f"import not allowed: {bad}"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS: return f"import not allowed: {node.module}"
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            return f"name not allowed: {node.id}"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return f"attribute not allowed: {node.attr}"
        elif isinstance(node, (ast.While, ast.AsyncFunctionDef, ast.Global, ast.Nonlocal)):
            return f"{type(node).__name__} not allowed"
    if not any(isinstance(n, ast.Name) and n.id == "answer" and isinstance(n.ctx, ast.Store) for n in ast.walk(tree)):
        return "no answer variable"
    return None


def _limits():                                # Linux/macOS only: cap memory at 512 MB and CPU at 5 s
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512 * 2**20, 512 * 2**20))
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))


def run_code(code, timeout=10):
    """Run checked code in a fresh isolated Python. Returns (value, error)."""
    reason = check_code(code)
    if reason:
        return None, reason
    script = code + "\nprint('__ANSWER__=' + repr(answer))\n"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "solve.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        try:
            r = subprocess.run([sys.executable, "-I", "-S", path], cwd=d, capture_output=True, text=True,
                               timeout=timeout, stdin=subprocess.DEVNULL,
                               env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")},
                               preexec_fn=_limits if os.name == "posix" else None)
        except subprocess.TimeoutExpired:
            return None, "timed out"
    m = re.search(r"__ANSWER__=(.*)", r.stdout)
    if r.returncode != 0 or not m:
        return None, "run error: " + (r.stderr.strip().splitlines() or ["no output"])[-1][:200]
    try:
        return ast.literal_eval(m.group(1).strip()), None
    except (ValueError, SyntaxError):
        return None, "answer is not a plain value"


# ---------- comparing with the options ----------

def close(a, b):
    return abs(a - b) <= TOL * max(abs(a), abs(b), 1e-9)


def matching_letters(value, options):
    """Letters of every option that equals the computed value."""
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, str):
        v = value.strip().lower()
        hits = [l for l, o in zip(LETTERS, options) if o.strip().lower() == v]
        if hits: return hits
        if re.fullmatch(r"[01]+", v):
            return []                         # a bit pattern must match as text, never as a number
        try: value = float(v)
        except ValueError: return []
    if isinstance(value, complex):
        return []
    value = float(value)
    hits = []
    for l, o in zip(LETTERS, options):
        ov = option_value(o)
        if ov is None or is_bits(o):
            continue
        pct = "%" in o or "percent" in o.lower()
        if close(value, ov) or (pct and close(value * 100, ov)):
            hits.append(l)
    return hits


# ---------- the check ----------

def math_check(mcq, generate, tries=2, allow_unchecked=False):
    """generate(messages) -> model text. messages is a chat list of role/content dicts."""
    if not needs_math(mcq):
        return {"status": "not_math", "accept": True}
    messages = [{"role": "system", "content": SOLVER_SYSTEM},
                {"role": "user", "content": SOLVER_USER.format(question=mcq["question"])}]
    errors = []
    for _ in range(tries):
        code = extract_code(generate(messages))
        value, err = run_code(code)
        if err:
            errors.append(err)
            continue
        if value is None:                     # the model says no calculation is needed
            return {"status": "not_math", "accept": True, "code": code}
        hits = matching_letters(value, mcq["options"])
        base = {"value": value, "code": code}
        if hits == [mcq["answer"]]:
            return {"status": "verified", "accept": True, **base}
        if len(hits) == 1:
            return {"status": "wrong_key", "accept": False, "correct": hits[0], **base}
        if len(hits) > 1:
            return {"status": "no_match", "accept": False, "note": f"several options match: {hits}", **base}
        return {"status": "no_match", "accept": False, **base}
    return {"status": "unchecked", "accept": allow_unchecked, "errors": errors}
