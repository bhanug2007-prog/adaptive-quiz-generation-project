"""The two agents' endpoints: "Ask about your class" and the step logs (what each agent did and why)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.insights import AGENT as INSIGHTS, QUESTION_MAX, LecturerInsightsAgent
from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer
from app.models import AgentRun, AgentStep, GenerationRun, User
from app.services import permissions as perm

router = APIRouter(prefix="/api/lecturer", tags=["agents"])


class AskRequest(BaseModel):
    course_id: int
    quiz_id: int | None = None
    question: str = Field(min_length=3, max_length=QUESTION_MAX)


def _step(st: AgentStep) -> dict:
    return {"seq": st.seq, "kind": st.kind, "name": st.name, "args": st.args, "result": st.result, "ok": st.ok,
            "duration_ms": st.duration_ms, "at": st.created_at}


def _run(db: Session, r: AgentRun, steps: bool = True) -> dict:
    out = {"id": r.id, "agent": r.agent, "status": r.status, "course_id": r.course_id,
           "generation_run_id": r.generation_run_id, "input": r.input, "output": r.output,
           "llm_calls": r.llm_calls, "error": r.error, "created_at": r.created_at, "finished_at": r.finished_at}
    if steps:
        out["steps"] = [_step(s) for s in db.scalars(select(AgentStep).where(AgentStep.agent_run_id == r.id)
                                                     .order_by(AgentStep.seq))]
    return out


@router.post("/insights/ask")
def ask(body: AskRequest, request: Request, user: User = Depends(require_lecturer), db: Session = Depends(get_db),
        s: Settings = Depends(get_settings_dep)):
    course = perm.own_course(db, user, body.course_id)
    limiter = request.app.state.insights_limiter
    key = f"insights:{user.id}"
    wait = limiter.blocked(key)
    if wait:
        raise HTTPException(429, f"Too many questions. Try again in {wait} seconds.")
    limiter.fail(key)                                  # counts every question, not only failures
    agent = LecturerInsightsAgent(db, user, course, s, request.app.state.quality)
    try:
        out = agent.ask(body.question, body.quiz_id)
    except ValueError:
        db.rollback()
        raise perm.not_found("Quiz") from None
    db.commit()
    return out


@router.get("/insights/history")
def history(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    perm.own_course(db, user, course_id)
    runs = db.scalars(select(AgentRun).where(AgentRun.agent == INSIGHTS, AgentRun.user_id == user.id,
                                             AgentRun.course_id == course_id)
                      .order_by(AgentRun.id.desc()).limit(20))
    return [_run(db, r, steps=False) for r in runs]


@router.get("/agent-runs/{run_id}")
def agent_run(run_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    r = db.get(AgentRun, run_id)
    if r is None or r.user_id != user.id:
        raise perm.not_found("Agent run")
    return _run(db, r)


@router.get("/generation/{run_id}/agent")
def generation_agent(run_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """The Question Quality Agent's steps for one generation run of this lecturer."""
    g = db.get(GenerationRun, run_id)
    if g is None or g.requested_by != user.id:
        raise perm.not_found("Generation run")
    r = db.scalar(select(AgentRun).where(AgentRun.generation_run_id == run_id).order_by(AgentRun.id.desc()))
    if r is None:
        raise perm.not_found("Agent run")
    return _run(db, r)
