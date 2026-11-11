"""TEST ONLY: a stand-in for llama-server so the backend can be tested without the real model.
It is never used by the app itself. It returns canned answers that exercise every check."""
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"n": 0, "mode": "normal"}     # modes: normal, clean, varied, down


def mcq(i):
    clean = STATE["mode"] in ("clean", "varied")   # "clean": every question passes the Python checks
    if STATE["mode"] == "varied":        # "varied": clean, and every stem is made of different made-up words,
        import random                    # so many quizzes on one topic never trip the duplicate check
        rng = random.Random(i)
        words = ["".join(rng.choice("bcdfghklmnprstvz") + rng.choice("aeiou") for _ in range(3)) for _ in range(6)]
        return (f"question: Which {' '.join(words)}? options: (A) Option alpha {i} (B) Option beta {i} "
                f"(C) Option gamma {i} (D) Option delta {i} answer: B explanation: Beta {i} is correct because of reason {i}.")
    if i % 5 == 1 and not clean:   # broken format: should be rejected
        return "Here is a question about the topic."
    if i % 5 == 3 and not clean:   # wrong maths key: radar range keyed 150 km, correct 15 km
        return ("question: A radar has PRF 10 kHz. What is its maximum unambiguous range? options: (A) 1.5 km (B) 15 km "
                "(C) 150 km (D) 1500 km answer: C explanation: R = c/(2 PRF) = 150 km.")
    stems = ["Which scheduler can starve long jobs", "What does a larger time quantum turn round robin into",
             "Which policy needs the burst length in advance", "What problem does aging solve",
             "Which metric does shortest job first minimise", "Which scheduler is non-preemptive by default",
             "What happens to response time when the quantum shrinks", "Which queue structure suits multilevel feedback",
             "Why is context switch cost important for small quanta", "Which algorithm suits time-sharing systems"]
    stem = stems[i % len(stems)] + ("" if i < len(stems) else f" in case {i}")
    return (f"question: {stem}? options: (A) Option alpha {i} (B) Option beta {i} (C) Option gamma {i} "
            f"(D) Option delta {i} answer: B explanation: Beta {i} is correct because of reason {i}.")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        self._send(200 if STATE["mode"] != "down" else 503, {"status": "ok"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        msgs = body["messages"]
        sys_, user = msgs[0]["content"], msgs[-1]["content"]
        if "Python" in sys_:
            nums = re.findall(r"PRF (\d+) kHz", user)
            text = f"```python\nanswer = 3e8/(2*{nums[0]}e3)/1000\n```" if nums else "```python\nanswer = None\n```"
        elif "List" in user and "subtopics" in user:
            text = "Round robin\nPriority scheduling\nShortest job first"
        elif "study notes" in user:
            text = ("Notes " * 60).strip()
        else:
            STATE["n"] += 1
            text = mcq(STATE["n"])
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}]})


def start(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


if __name__ == "__main__":       # TEST ONLY: python -m tests.fake_model_server --port 8080 --delay 0.5
    import argparse
    import time
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--delay", type=float, default=0.0, help="seconds per reply, to watch the progress UI")
    args = ap.parse_args()
    if args.delay:
        _orig = H.do_POST
        def slow(self):
            time.sleep(args.delay)
            _orig(self)
        H.do_POST = slow
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    print(f"TEST-ONLY fake model server on :{args.port}")
    srv.serve_forever()
