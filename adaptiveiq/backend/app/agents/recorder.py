"""Stores an agent's tool calls and decisions (agent_runs / agent_steps) as it works."""
import time

from sqlalchemy.orm import Session

from app.models import AgentRun, AgentStep
from app.models.base import utcnow
from app.services.quality_service import scrub_secrets

MAX_JSON_TEXT = 600


def _short(v):
    """Keeps step logs small and redacts credentials/tokens before saving."""
    if isinstance(v, str):
        clean = scrub_secrets(v)
        return clean if len(clean) <= MAX_JSON_TEXT else clean[:MAX_JSON_TEXT] + "…"
    if isinstance(v, dict):
        return {k: _short(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_short(x) for x in v]
    return v


class Recorder:
    def __init__(self, db: Session, run: AgentRun):
        self.db, self.run = db, run
        self.seq = 0

    @classmethod
    def start(cls, db: Session, agent: str, user_id: int, input: dict, course_id: int | None = None,
              generation_run_id: int | None = None) -> "Recorder":
        run = AgentRun(agent=agent, user_id=user_id, course_id=course_id, generation_run_id=generation_run_id,
                       status="running", input=_short(input), llm_calls=0)
        db.add(run)
        db.flush()
        return cls(db, run)

    def _add(self, kind: str, name: str, args: dict | None, result: dict | None, ok: bool, ms: int | None):
        self.seq += 1
        self.db.add(AgentStep(agent_run_id=self.run.id, seq=self.seq, kind=kind, name=name, args=_short(args or {}),
                              result=_short(result or {}), ok=ok, duration_ms=ms))

    def tool(self, name: str, args: dict, fn, summarize=None):
        """Runs one tool call and logs it. `summarize(result) -> dict` keeps the logged result small."""
        t0 = time.perf_counter()
        try:
            res = fn()
        except Exception as e:
            self._add("tool", name, args, {"error": str(e)[:300] or type(e).__name__}, False,
                      int((time.perf_counter() - t0) * 1000))
            raise
        summary = summarize(res) if summarize else (res if isinstance(res, dict) else {"value": res})
        ok = summary.pop("_ok", True) if isinstance(summary, dict) else True
        self._add("tool", name, args, summary, ok, int((time.perf_counter() - t0) * 1000))
        return res

    def decide(self, name: str, because: str, **data):
        """A decision the agent took, with the reason in plain words."""
        self._add("decision", name, data, {"because": because}, True, None)

    def llm(self, name: str, args: dict, result: dict, ok: bool, ms: int | None):
        self.run.llm_calls = (self.run.llm_calls or 0) + 1
        self._add("llm", name, args, result, ok, ms)

    def finish(self, status: str, output: dict | None = None, error: str | None = None):
        clean_err = scrub_secrets(error) if error else None
        self.run.status, self.run.output, self.run.error = status, _short(output) if output else None, clean_err
        self.run.finished_at = utcnow()
