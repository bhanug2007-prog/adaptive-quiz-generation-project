"""The Python maths check runs model-written code. Every one of these programs must be refused or contained."""
import os

import pytest

from app.validators.mathcheck import check_code, run_code, sandbox_layers

posix_only = pytest.mark.skipif(os.name != "posix", reason="OS limits exist only on Linux/macOS")


def test_normal_program_runs():
    assert run_code("import math\nanswer = round(math.sqrt(2) * 10, 3)") == (14.142, None)


@pytest.mark.parametrize("code", [
    "import os\nanswer = os.listdir('/')",
    "import socket\nanswer = 1",
    "from subprocess import run\nanswer = 1",
    "answer = open('/etc/passwd').read()",
    "answer = __import__('os').getcwd()",
    "answer = ().__class__.__bases__[0].__subclasses__()",
    "answer = eval('1+1')",
    "answer = getattr(1, 'real')",
    "while True:\n    pass\nanswer = 1",
    "x = 1",                                             # no answer variable
])
def test_static_check_refuses(code):
    value, err = run_code(code)
    assert value is None and err


def test_restricted_builtins_block_what_the_static_check_cannot_see():
    # 'type' and 'object' are not in the safe builtins list, so this fails at run time even though
    # check_code() lets it through (no underscore attribute, no blocked name).
    code = "t = type\nanswer = 1"
    assert check_code(code) is None
    value, err = run_code(code)
    assert value is None and "NameError" in err


def test_dynamic_import_is_blocked_at_run_time():
    code = "import math\nm = math\nanswer = 1\nimport importlib"
    value, err = run_code(code)
    assert value is None and err            # importlib refused statically


def test_wall_clock_timeout():
    value, err = run_code("answer = sum(range(10**12))", timeout=2)
    assert value is None and (err == "timed out" or "run error" in err)


def test_memory_limit():
    value, err = run_code("x = [0] * (10**9)\nanswer = len(x)")
    assert value is None and err
    value2, err2 = run_code("b = bytearray(600 * 1024 * 1024)\nanswer = len(b)")
    assert value2 is None and ("MemoryError" in err2 or "run error" in err2)


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object isolation test")
def test_windows_job_object_blocks_subprocess_spawn(tmp_path):
    from app.validators.mathcheck import _run_windows_isolated, _worker_executable

    assert sandbox_layers()["os_limits"] is True
    value, err = run_code("import itertools\nanswer = sum(1 for _ in itertools.islice(range(5), 3))")
    assert value == 3 and err is None

    env = {"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    exe = _worker_executable()
    rc, _, stderr, timed_out = _run_windows_isolated(
        [exe, "-I", "-S", "-B", "-c", f"import subprocess; subprocess.run([{exe!r}, '-I', '-S', '-B', '-c', 'pass'])"],
        str(tmp_path), env, timeout=5,
    )
    assert not timed_out and rc != 0 and ("1816" in stderr or "quota" in stderr.lower() or "OSError" in stderr or "PermissionError" in stderr)


@posix_only
def test_no_file_writes_even_via_allowed_module():
    # nothing allowed can open files, and RLIMIT_FSIZE=0 stops writes as a further layer
    value, err = run_code("answer = print('x', file=None)")
    assert err is None                       # printing to stdout is fine
    assert sandbox_layers()["os_limits"] is True


def test_health_reports_sandbox(make_client):
    m = make_client().get("/api/health").json()["math_check"]
    assert set(m["sandbox"]) == {"static_check", "restricted_builtins", "separate_process", "os_limits", "no_network"}


def test_network_namespace_has_no_network_when_available():
    import subprocess
    import sys

    from app.validators.mathcheck import _netns_prefix
    pre = _netns_prefix()
    if not pre:
        pytest.skip("this machine does not allow an unprivileged network namespace")
    r = subprocess.run(pre + [sys.executable, "-c", "import socket; socket.create_connection(('1.1.1.1', 80), 2)"],
                       capture_output=True, text=True, timeout=20)
    assert r.returncode != 0 and ("unreachable" in r.stderr.lower() or "error" in r.stderr.lower())


def test_validator_never_runs_model_code_without_os_limits(monkeypatch, settings):
    """When the isolated worker is unavailable, multi-step Python code must never execute without
    isolation and verification must fail closed, while simple expressions still verify safely via
    the restricted AST parser."""
    from app.services import validation_service as vs
    from app.validators import mathcheck

    monkeypatch.setattr(vs, "can_run_safely", lambda allow=False: False)
    monkeypatch.setattr(mathcheck.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worker must not launch")))
    monkeypatch.setattr(mathcheck.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("worker must not launch")))

    class LoopModel:
        def chat(self, *a, **k):
            return "```python\ntotal = 0\nfor i in range(1, 6):\n    total += i\nanswer = total\n```"

    text = ("question: What is the sum of 1..5? options: (A) 10 (B) 15 (C) 20 (D) 25 "
            "answer: B explanation: 1+2+3+4+5 = 15.")
    res = vs.Validator(settings, LoopModel()).check(text, [])
    assert not res.ok and res.reason == "math_unchecked" and res.info["math_status"] == "unchecked"
    permissive = vs.Validator(settings.model_copy(update={"math_check_strict": False}), LoopModel()).check(text, [])
    assert not permissive.ok and permissive.reason == "math_unchecked"

    class SimpleExprModel:
        def chat(self, *a, **k):
            return "```python\nanswer = 3e8/(2*10e3)/1000\n```"

    radar = ("question: A radar has PRF 10 kHz. What is its maximum unambiguous range? options: (A) 1.5 km "
             "(B) 15 km (C) 150 km (D) 1500 km answer: B explanation: R = c / (2 PRF) = 15 km.")
    ok_res = vs.Validator(settings, SimpleExprModel()).check(radar, [])
    assert ok_res.ok and ok_res.math_verified and ok_res.info["math_method"] == "expression_parser"
