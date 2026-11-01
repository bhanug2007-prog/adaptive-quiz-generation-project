"""Question bank and the lecturer's review workflow."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_lecturer
from app.models import AnswerOption, LearningObjective, Question, QuestionReviewRecord, QuizQuestion, User
from app.schemas.quizzes import QuestionCreate, QuestionEdit, QuestionFull, ReviewAction
from app.services import permissions as perm
from app.services.generation_service import question_snapshot
from app.services.quiz_views import question_full

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
    if q.review_status == "approved":
        q.review_status = "draft"                     # an edited question needs approving again
    db.add(QuestionReviewRecord(question_id=q.id, reviewer_id=user.id, action="edited", note=body.note,
                                before=before, after=question_snapshot(q)))
    db.commit()
    return question_full(db, q)


@router.post("/{question_id}/review", response_model=QuestionFull)
def review_question(question_id: int, body: ReviewAction, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    q = perm.own_question(db, user, question_id)
    if q.review_status == "personal":
        raise HTTPException(409, "Personal practice questions are not part of the review workflow.")
    if sum(o.is_correct for o in q.options) != 1 or len(q.options) != 4:
        raise HTTPException(422, "A question needs exactly four options and one correct answer before review.")
    q.review_status = {"approve": "approved", "reject": "rejected", "reset": "draft"}[body.action]
    db.add(QuestionReviewRecord(question_id=q.id, reviewer_id=user.id,
                                action={"approve": "approved", "reject": "rejected", "reset": "edited"}[body.action],
                                note=body.note, after=question_snapshot(q)))
    db.commit()
    return question_full(db, q)


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
