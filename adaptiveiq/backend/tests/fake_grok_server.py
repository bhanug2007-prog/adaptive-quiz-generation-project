"""TEST ONLY: a stand-in for the xAI (Grok) chat completions API, so the AI review can be tested
without a key or network. It is never used by the app itself.

Modes (STATE["mode"]):
  pass            every question passes; judged difficulty = the requested one
  fail_first:<k>  the first k reviews say the marked answer is wrong, then pass
  incorrect       every review says the marked answer is wrong
  hard            judges every question "hard" (difficulty mismatch unless hard was requested)
  bad_json        replies with text that is not JSON
  empty           replies with empty whitespace content
  wrong_schema    replies with JSON missing required fields
  think_pass      wraps valid JSON inside a <think>...</think> reasoning block
  model_not_found HTTP 404 model_not_found
  rate_limit      HTTP 429
  quota           HTTP 429 with a quota message
  auth            HTTP 401
  error           HTTP 500
  slow            sleeps STATE["sleep"] seconds before answering
  STATE["script"] a list of replies used first, one per request: a string (sent as the reply text) or a
                  (status, body) pair (sent as an HTTP error); used by the Lecturer Insights Agent tests
"""
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"mode": "pass", "calls": 0, "sleep": 2.0, "bodies": [], "auth": [], "script": []}


def review(requested: str, verdict="correct", assessed=None, score=88) -> dict:
    return {
        "quality_score": score,
        "correctness": {"verdict": verdict, "note": "The marked answer is right." if verdict == "correct" else "Option B is wrong."},
        "relevance": {"ok": True, "note": "Tests the topic."},
        "difficulty": {"assessed": assessed or requested, "note": "Matches the scale."},
        "options": {"ok": True, "note": "Distinct distractors."},
        "multiple_correct": {"value": False, "note": ""},
        "ambiguity": {"ambiguous": False, "note": ""},
        "explanation": {"supports_answer": True, "note": ""},
        "clarity": {"ok": True, "note": ""},
        "passed": verdict == "correct",
        "feedback": "Fine for an exam." if verdict == "correct" else "The key is wrong.",
        "regeneration_instructions": "" if verdict == "correct" else "Fix the answer key.",
    }


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        b = (obj if isinstance(obj, str) else json.dumps(obj)).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def _content(self, text):
        self._send(200, {"choices": [{"message": {"role": "assistant", "content": text}}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["calls"] += 1
        STATE["bodies"].append(body)
        STATE["auth"].append(self.headers.get("Authorization"))
        user = body["messages"][-1]["content"]
        requested = (re.search(r"Requested difficulty: (\w+)", user) or [None, "medium"])[1]
        if STATE["script"]:
            nxt = STATE["script"].pop(0)
            if isinstance(nxt, tuple):
                return self._send(nxt[0], nxt[1])
            return self._content(nxt)
        mode = STATE["mode"]
        if mode == "slow":
            time.sleep(STATE["sleep"])
            return self._content(json.dumps(review(requested)))
        if mode == "rate_limit":
            return self._send(429, {"error": "Too many requests"})
        if mode == "quota":
            return self._send(429, {"error": "You have exhausted your monthly quota"})
        if mode == "auth":
            return self._send(401, {"error": "Incorrect API key"})
        if mode == "model_not_found":
            return self._send(404, {"error": {"message": "The model `grok-test` does not exist or you do not have access to it.",
                                               "type": "invalid_request_error", "code": "model_not_found"}})
        if mode == "error":
            return self._send(500, {"error": "internal"})
        if mode == "empty":
            return self._content("   \n  ")
        if mode == "think_pass":
            return self._content("<think>Reasoning with {braces} inside.</think>\n```json\n"
                                 + json.dumps(review(requested)) + "\n```")
        if mode == "bad_json":
            return self._content("Looks good to me!")
        if mode == "wrong_schema":
            return self._content(json.dumps({"quality_score": 90, "passed": True}))
        if mode == "incorrect":
            return self._content(json.dumps(review(requested, verdict="incorrect", score=30)))
        if mode == "hard":
            return self._content("```json\n" + json.dumps(review(requested, assessed="hard")) + "\n```")
        if mode.startswith("fail_first:"):
            k = int(mode.split(":")[1])
            if STATE["calls"] <= k:
                return self._content(json.dumps(review(requested, verdict="incorrect", score=30)))
        return self._content(json.dumps(review(requested)))


def start(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def reset(mode="pass"):
    STATE.update(mode=mode, calls=0, bodies=[], auth=[], script=[])
