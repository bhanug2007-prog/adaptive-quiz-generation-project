"""Question bank and the lecturer's review workflow."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import get_db, get_settings_dep, require_lecturer
from app.models import (AnswerOption, LearningObjective, Question, QuestionEvaluation, QuestionReviewRecord,
                        QuizQuestion, User)
from app.models.base import utcnow
from app.schemas.quizzes import QuestionCreate, QuestionEdit, QuestionFull, ReviewAction
from app.services import permissions as perm
from app.services.generation_service import question_snapshot
from app.services.model_service import ModelError
from app.services.quiz_views import question_full
from app.services.validation_service import REASONS, gives_answer_away, is_duplicate, verify_source_grounding
from app.validators.mathcheck import can_run_safely, math_check, needs_math
from app.validators.numcheck import numeric_conflict

router = APIRouter(prefix="/api/lecturer/questions", tags=["question bank"])


@router.get("", response_model=dict)
def list_questions(user: User = Depends(require_lecturer), db: Session = Depends(get_db),
                   q: str | None = Query(default=None, max_length=200), course_id: int | None = None,
                   topic_id: int | None = None, difficulty: str | None = None, review_status: str | None = None,
                   page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100)):
    stmt = select(Question).where(Question.owner_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Question.text).like(like), func.lower(Question.topic_label).like(like)))
    if course_id:
        stmt = stmt.where(Question.course_id == course_id)
    if topic_id:
        stmt = stmt.where(Question.topic_id == topic_id)
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if review_status:
        stmt = stmt.where(Question.review_status == review_status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Question.updated_at.desc()).offset((page - 1) * page_size).limit(page_size))
    return {"total": total, "page": page, "page_size": page_size,
            "items": [question_full(db, x).model_dump(mode="json") for x in rows]}


@router.get("/{question_id}", response_model=QuestionFull)
def get_question(question_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    return question_full(db, perm.own_question(db, user, question_id))


@router.post("", response_model=QuestionFull, status_code=201)
def create_question(body: QuestionCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    t = perm.own_topic(db, user, body.topic_id)
    if body.objective_id:
        o = db.get(LearningObjective, body.objective_id)
        if o is None or o.topic_id != t.id:
            raise HTTPException(422, "The objective does not belong to this topic.")
    q = Question(owner_id=user.id, course_id=t.unit.subject.course_id, topic_id=t.id, objective_id=body.objective_id,
                 topic_key=f"t:{t.id}", subject_label=t.unit.subject.name, unit_label=t.unit.name, topic_label=t.name,
                 text=" ".join(body.text.split()), explanation=body.explanation, difficulty=body.difficulty,
                 source_type="manual", review_status="approved", validation={"manual": True})
    for k, (label, txt) in enumerate(zip("ABCD", body.options)):
        q.options.append(AnswerOption(label=label, text=txt, is_correct=label == body.correct_label, position=k))
    db.add(q)
    db.flush()
    db.add(QuestionReviewRecord(question_id=q.id, reviewer_id=user.id, action="approved", note="Written by hand",
                                after=question_snapshot(q)))
    db.commit()
    return question_full(db, q)


UNVERIFIED_MATH_STATUSES = {"wrong_key", "no_match", "ambiguous", "unsupported", "unchecked"}


def math_block_reason(q: Question, math_check_enabled: bool = True) -> str | None:
    """Numerical questions with failed or unchecked math verification must not be approved or published."""
    v = q.validation or {}
    ms = v.get("math_status")
    fr = v.get("failure_reason") or ""
    if ms in UNVERIFIED_MATH_STATUSES or fr.startswith("math_"):
        return ("This numerical question has failed or unchecked mathematical verification. "
                "Edit it and run Check again until verification passes before approving.")
    if math_check_enabled and not v.get("manual") and len(q.options) == 4:
        answer = next((o.label for o in q.options if o.is_correct), "A")
        mcq = {"question": q.text, "options": [o.text for o in q.options], "answer": answer,
               "explanation": q.explanation or ""}
        if needs_math(mcq) and ms not in ("verified", "not_math"):
            return ("This numerical question has not passed mathematical verification. "
                    "Run Check again until verification passes before approving.")
    return None


def _locked(db: Session, q: Question) -> bool:
    from app.models import StudentAnswer
    return db.scalar(select(StudentAnswer.id).where(StudentAnswer.question_id == q.id).limit(1)) is not None


@router.patch("/{question_id}", response_model=QuestionFull)
def edit_question(question_id: int, body: QuestionEdit, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    q = perm.own_question(db, user, question_id)
    if _locked(db, q):
        raise HTTPException(409, "Students have already answered this question. Duplicate it and edit the copy, "
                                 "so past results stay correct.")
    before = question_snapshot(q)
    data = body.model_dump(exclude_unset=True)
    if "text" in data and data["text"]:
        q.text = " ".join(data["text"].split())
    if "explanation" in data:
        q.explanation = data["explanation"]
    if data.get("difficulty"):
        q.difficulty = data["difficulty"]
    if "objective_id" in data:
        if data["objective_id"]:
            o = db.get(LearningObjective, data["objective_id"])
            if o is None or q.topic_id is None or o.topic_id != q.topic_id:
                raise HTTPException(422, "The objective does not belong to this question's topic.")
        q.objective_id = data["objective_id"]
    if data.get("options"):
        for o, txt in zip(q.options, data["options"]):
            o.text = txt
    if data.get("correct_label"):
        for o in q.options:
            o.is_correct = o.label == data["correct_label"]
    after = question_snapshot(q)
    content_changed = any(after[k] != before[k] for k in ("text", "explanation", "options"))
    if q.review_status == "approved" or (q.review_status == "rejected" and content_changed):
        q.review_status = "draft"                     # an edited question needs approving again
    v = dict(q.validation or {})                      # new dict so the JSON column is saved
    changed_v = False
    if v.get("quality"):
        v["quality"] = {**v["quality"], "stale": True}
        changed_v = True
    if content_changed and len(q.options) == 4:
        after_mcq = {
            "question": q.text,
            "options": [o.text for o in q.options],
            "answer": next((o.label for o in q.options if o.is_correct), "A"),
            "explanation": q.explanation or "",
        }
        if (
            v.get("math_verified")
            or v.get("math_status") in (UNVERIFIED_MATH_STATUSES | {"verified"})
            or (not v.get("manual") and needs_math(after_mcq))
        ):
            v["math_verified"] = False
            v["math_status"] = "unchecked" if needs_math(after_mcq) else "not_math"
            v["evaluations_stale"] = True
            changed_v = True
    if v.get("quarantined") and content_changed:
        v["quarantined"] = False
        v["was_quarantined"] = True
        v["quarantine_recheck_required"] = True
        v["failed_validation"] = True
        v["failure_reason"] = "quarantine_recheck_required"
        v["failure_text"] = REASONS["quarantine_recheck_required"]
        changed_v = True
    if changed_v:
        q.validation = v
    db.add(QuestionReviewRecord(question_id=q.id, reviewer_id=user.id, action="edited", note=body.note,
                                before=before, after=after))
    db.commit()
    return question_full(db, q)


@router.post("/{question_id}/review", response_model=QuestionFull)
def review_question(question_id: int, body: ReviewAction, user: User = Depends(require_lecturer),
                    db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    q = perm.own_question(db, user, question_id)
    if q.review_status == "personal":
        raise HTTPException(409, "Personal practice questions are not part of the review workflow.")
    v = q.validation or {}
    if body.action in ("approve", "reset") and v.get("quarantined"):
        if _locked(db, q):
            raise HTTPException(409, "This question is quarantined because its stem or answer key is invalid, and "
                                     "students have already answered it. Duplicate it, edit the copy and check it instead.")
        if body.action == "approve":
            raise HTTPException(422, "This question is quarantined. Edit its content and run Check again before approving.")
    if body.action == "approve" and v.get("quarantine_recheck_required"):
        raise HTTPException(422, "This quarantined question was edited. Run Check again before approving it.")
    if sum(o.is_correct for o in q.options) != 1 or len(q.options) != 4:
        raise HTTPException(422, "A question needs exactly four options and one correct answer before review.")
    if body.action == "approve":
        math_err = math_block_reason(q, s.math_check)
        if math_err:
            raise HTTPException(422, math_err)
    before = question_snapshot(q)
    q.review_status = {"approve": "approved", "reject": "rejected", "reset": "draft"}[body.action]
    db.add(QuestionReviewRecord(question_id=q.id, reviewer_id=user.id,
                                action={"approve": "approved", "reject": "rejected", "reset": "edited"}[body.action],
                                note=body.note, before=before, after=question_snapshot(q)))
    db.commit()
    return question_full(db, q)


def _python_checks(db: Session, q: Question, mcq: dict, s: Settings) -> str | None:
    """The checks that need no model call (the maths check runs only during generation)."""
    texts = [o.text.strip().lower() for o in q.options]
    if len(q.text) < 10 or len(texts) != 4 or any(not t for t in texts) or len(set(texts)) != 4:
        return "format"
    others = list(db.scalars(select(Question.text).where(Question.topic_key == q.topic_key, Question.id != q.id,
                                                         Question.owner_id == q.owner_id,
                                                         Question.review_status != "rejected")
                             .order_by(Question.id.desc()).limit(300)))
    if is_duplicate(mcq["question"], others, s.duplicate_threshold)[0]:
        return "duplicate"
    if gives_answer_away(mcq):
        return "answer_in_question"
    if numeric_conflict(mcq):
        return "explanation_number"
    return None


@router.post("/{question_id}/check-quality", response_model=QuestionFull)
def check_quality(question_id: int, request: Request, user: User = Depends(require_lecturer),
                  db: Session = Depends(get_db), s: Settings = Depends(get_settings_dep)):
    """Runs the Python checks and, when available, the AI review again on the question as it is now
    (for example after an edit). Clears "Failed checks" only when the check that failed now passes."""
    q = perm.own_question(db, user, question_id)
    if q.review_status == "personal":
        raise HTTPException(409, "Personal practice questions are not part of the review workflow.")
    if sum(o.is_correct for o in q.options) != 1 or len(q.options) != 4:
        raise HTTPException(422, "A question needs exactly four options and one correct answer before it can be checked.")
    recent = db.scalar(select(QuestionEvaluation.created_at).where(QuestionEvaluation.question_id == q.id,
                                                                   QuestionEvaluation.generation_run_id.is_(None))
                       .order_by(QuestionEvaluation.id.desc()).limit(1))
    if recent is not None and utcnow() - recent < timedelta(seconds=10):
        raise HTTPException(429, "This question was just checked. Wait a few seconds and try again.")
    answer = next(o.label for o in q.options if o.is_correct)
    mcq = {"question": q.text, "options": [o.text for o in q.options], "answer": answer, "explanation": q.explanation or ""}
    v = dict(q.validation or {})
    if v.get("quarantined"):
        raise HTTPException(422, "Edit this quarantined question before running quality checks again.")
    py_reason = _python_checks(db, q, mcq, s)
    if q.source_type in ("document", "reference_text") and q.source_excerpt:
        g_ok, _g, g_info = verify_source_grounding(mcq, q.source_excerpt, strict=(q.source_type == "document"))
        v.update({k: g_info[k] for k in ("grounding", "stem_grounding", "grounding_verified") if k in g_info})
        if "ungrounded_numbers" in g_info:
            v["ungrounded_numbers"] = g_info["ungrounded_numbers"]
        else:
            v.pop("ungrounded_numbers", None)
        if py_reason is None and not g_ok:
            py_reason = "not_grounded"
    if py_reason is None and s.math_check and needs_math(mcq):
        model = request.app.state.model
        try:
            m_res = math_check(
                mcq,
                lambda m: model.chat(m, temperature=0.0, max_tokens=400),
                allow_unchecked=not s.math_check_strict,
                allow_without_os_limits=s.math_check_allow_without_os_limits,
                worker_available=can_run_safely(s.math_check_allow_without_os_limits),
            )
            ms = m_res["status"]
            v["math_status"] = ms
            v["math_verified"] = (ms == "verified")
            if m_res.get("method"):
                v["math_method"] = m_res["method"]
            if m_res.get("note"):
                v["math_note"] = m_res["note"]
            if m_res.get("errors"):
                v["math_errors"] = m_res["errors"][:3]
            if not m_res["accept"] or (ms not in ("verified", "not_math") and (s.math_check_strict or ms != "unchecked")):
                py_reason = f"math_{ms}"
        except ModelError as exc:
            v["math_status"] = "unchecked"
            v["math_verified"] = False
            v["math_note"] = str(exc)
            py_reason = "math_unchecked"
    elif py_reason is None and s.math_check and not needs_math(mcq) and v.get("math_status") in ("wrong_key", "no_match", "ambiguous", "unsupported", "unchecked"):
        v["math_status"] = "not_math"
        v["math_verified"] = False
    quality = request.app.state.quality
    res = None
    if py_reason is None and quality.enabled_for("lecturer_draft"):
        rules_ctx = {k: v[k] for k in ("math_status", "grounding", "grounding_verified") if k in v} or None
        res = quality.evaluate(mcq, q.subject_label, q.topic_label, q.difficulty, q.source_excerpt, rules_ctx,
                               strict_source=(q.source_type == "document"))
    reason = py_reason or (res.reason if res else None)
    if res is not None:
        v["quality"] = res.summary()
    else:
        v["quality"] = {"status": "failed" if py_reason else "not_checked", "evaluator": None,
                        "reason": py_reason, "reason_text": REASONS.get(py_reason) if py_reason else None,
                        "ai_error": None if py_reason else quality.skip_reason("lecturer_draft")}
    v["quality"]["checked_at"] = utcnow().isoformat()
    math_ok = not (s.math_check and needs_math(mcq)) or v.get("math_status") in ("verified", "not_math")
    if reason is None and math_ok:
        v.pop("evaluations_stale", None)
        v.pop("stale_reason", None)
    if v.get("failed_validation"):
        old = v.get("failure_reason") or ""
        fixed = (reason is None and math_ok
                 and (not old.startswith("quality_") or (res is not None and res.evaluator == "grok")))
        if fixed:
            for k in ("failed_validation", "failure_reason", "failure_text", "quarantine_recheck_required"):
                v.pop(k, None)
        elif reason:
            v.update(failure_reason=reason, failure_text=REASONS.get(reason, reason))
    elif reason:
        v.update(failed_validation=True, failure_reason=reason, failure_text=REASONS.get(reason, reason))
    q.validation = v
    db.add(QuestionEvaluation(
        question_id=q.id, evaluator=res.evaluator if res else "rules", evaluator_model=res.evaluator_model if res else None,
        requested_difficulty=q.difficulty, passed=reason is None, reason=reason, quality_score=res.score if res else None,
        checks=res.checks if res else {"python_checks": "failed" if py_reason else "passed"},
        feedback=res.feedback if res else None, regeneration_instructions=res.regeneration_instructions if res else None,
        ai_error=res.ai_error if res else None))
    db.commit()
    return question_full(db, q)


@router.get("/{question_id}/evaluations")
def evaluations(question_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """The quality-check log of a question, newest first."""
    q = perm.own_question(db, user, question_id)
    rows = db.scalars(select(QuestionEvaluation).where(QuestionEvaluation.question_id == q.id)
                      .order_by(QuestionEvaluation.id.desc()).limit(50))
    return [{"at": r.created_at, "evaluator": r.evaluator, "model": r.evaluator_model, "passed": r.passed,
             "reason": r.reason, "reason_text": REASONS.get(r.reason) if r.reason else None, "score": r.quality_score,
             "requested_difficulty": r.requested_difficulty, "feedback": r.feedback,
             "regeneration_instructions": r.regeneration_instructions, "ai_error": r.ai_error,
             "slot": r.slot, "attempt": r.attempt} for r in rows]


@router.post("/{question_id}/duplicate", response_model=QuestionFull, status_code=201)
def duplicate_question(question_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    q = perm.own_question(db, user, question_id)
    c = Question(owner_id=user.id, course_id=q.course_id, topic_id=q.topic_id, objective_id=q.objective_id,
                 topic_key=q.topic_key, subject_label=q.subject_label, unit_label=q.unit_label, topic_label=q.topic_label,
                 text=q.text, explanation=q.explanation, difficulty=q.difficulty, source_type=q.source_type,
                 source_excerpt=q.source_excerpt, model_version_id=q.model_version_id, review_status="draft",
                 validation=dict(q.validation or {}), derived_from_id=q.id)
    for o in q.options:
        c.options.append(AnswerOption(label=o.label, text=o.text, is_correct=o.is_correct, position=o.position))
    db.add(c)
    db.commit()
    return question_full(db, c)


@router.get("/{question_id}/history")
def review_history(question_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    q = perm.own_question(db, user, question_id)
    recs = db.scalars(select(QuestionReviewRecord).where(QuestionReviewRecord.question_id == q.id)
                      .order_by(QuestionReviewRecord.id))
    return [{"action": r.action, "note": r.note, "before": r.before, "after": r.after, "at": r.created_at} for r in recs]


@router.delete("/{question_id}", status_code=204)
def delete_question(question_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    q = perm.own_question(db, user, question_id)
    if _locked(db, q) or db.scalar(select(QuizQuestion.id).where(QuizQuestion.question_id == q.id).limit(1)):
        raise HTTPException(409, "This question is used in a quiz or has answers. Reject it instead of deleting it.")
    db.delete(q)
    db.commit()
