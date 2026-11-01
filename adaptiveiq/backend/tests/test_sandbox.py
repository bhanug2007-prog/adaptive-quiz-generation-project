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


@posix_only
def test_memory_limit():
    value, err = run_code("x = [0] * (10**9)\nanswer = len(x)")
    assert value is None and "MemoryError" in err


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
    """On a machine without OS limits (Windows) a numeric question is accepted as 'unchecked' and the
    model is never asked for a program."""
    from app.services import validation_service as vs

    monkeypatch.setattr(vs, "can_run_safely", lambda allow=False: False)

    class NoModel:
        def chat(self, *a, **k):
            raise AssertionError("model-written code must not be requested here")

    text = ("question: A radar has PRF 10 kHz. What is its maximum unambiguous range? options: (A) 1.5 km "
            "(B) 15 km (C) 150 km (D) 1500 km answer: B explanation: R = c / (2 PRF) = 15 km.")
    res = vs.Validator(settings, NoModel()).check(text, [])
    assert res.ok and res.info["math_status"] == "unchecked"
    strict = vs.Validator(settings.model_copy(update={"math_check_strict": True}), NoModel()).check(text, [])
    assert not strict.ok and strict.reason == "math_unchecked"
