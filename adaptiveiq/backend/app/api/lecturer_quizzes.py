"""Lecturer quiz management: settings, items, preview, publishing, feedback release."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_lecturer, verified_lecturer
from app.models import Quiz, QuizAssignment, QuizQuestion, QuizSession, Subject, User
from app.models.base import utcnow
from app.schemas.quizzes import ItemsUpdate, QuizDetail, QuizOut, QuizSettings
from app.services import permissions as perm
from app.services.grading import weight_used
from app.services.quiz_views import quiz_detail, quiz_out

router = APIRouter(prefix="/api/lecturer/quizzes", tags=["lecturer quizzes"])


def _has_attempts(db: Session, quiz_id: int) -> bool:
    return db.scalar(select(QuizSession.id).where(QuizSession.quiz_id == quiz_id).limit(1)) is not None


def _renumber(z: Quiz):
    for k, it in enumerate(sorted(z.items, key=lambda i: i.position)):
        it.position = k
    z.max_marks = float(sum(i.marks for i in z.items))


def validate_for_publish(db: Session, z: Quiz) -> list[str]:
    problems = []
    if not z.items:
        problems.append("The quiz has no questions.")
    not_ok = [i.position + 1 for i in z.items if i.question.review_status != "approved"]
    if not_ok:
        problems.append(f"Approve or remove question(s) {', '.join(map(str, not_ok))} first.")
    if z.course_id is None:
        problems.append("Choose a course.")
    if z.opens_at and z.due_at and z.opens_at >= z.due_at:
        problems.append("The due date must be after the opening date.")
    if z.late_policy != "none":
        if not z.due_at:
            problems.append("Late submissions need a due date.")
        elif not z.closes_at or z.closes_at <= z.due_at:
            problems.append("Late submissions need a final close date after the due date.")
    if z.feedback_release == "after_due" and not z.due_at:
        problems.append("'Release feedback after the due date' needs a due date.")
    if z.graded and z.contribution_pct and z.subject_id:
        s = db.get(Subject, z.subject_id)
        used = weight_used(db, s.id, z.id)
        if used + z.contribution_pct > s.quiz_weight_cap_pct + 1e-9:
            problems.append(f"{s.name}: quizzes may contribute {s.quiz_weight_cap_pct:g}% in total; other quizzes "
                            f"already use {used:g}%, so this one can be at most {max(0, s.quiz_weight_cap_pct - used):g}%.")
    return problems


@router.get("", response_model=list[QuizOut])
def list_quizzes(user: User = Depends(require_lecturer), db: Session = Depends(get_db), course_id: int | None = None,
                 status: str | None = None):
    stmt = select(Quiz).where(Quiz.owner_id == user.id, Quiz.kind == "assessment")
    if course_id:
        stmt = stmt.where(Quiz.course_id == course_id)
    if status:
        stmt = stmt.where(Quiz.status == status)
    return [quiz_out(db, z) for z in db.scalars(stmt.order_by(Quiz.created_at.desc()))]


@router.get("/{quiz_id}", response_model=QuizDetail)
def get_quiz(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    return quiz_detail(db, perm.own_quiz(db, user, quiz_id))


@router.patch("/{quiz_id}", response_model=QuizDetail)
def update_settings(quiz_id: int, body: QuizSettings, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status not in ("draft", "published"):
        raise HTTPException(409, "This quiz can no longer be changed.")
    data = body.model_dump(exclude_unset=True)
    if z.status == "published":
        allowed = {"title", "instructions", "due_at", "closes_at", "feedback_release", "late_policy", "late_penalty_pct"}
        # Only fields whose value actually changes count, so resending unchanged settings is fine.
        blocked = {k for k in set(data) - allowed if getattr(z, k) != data[k]}
        if blocked and _has_attempts(db, z.id):
            raise HTTPException(409, "Students have started this quiz, so only the title, instructions, dates, late "
                                     "policy and feedback release can change.")
    for k, v in data.items():
        setattr(z, k, v)
    if z.late_policy == "none":
        z.closes_at = None
    if z.status == "published":
        problems = validate_for_publish(db, z)
        if problems:
            db.rollback()
            raise HTTPException(422, " ".join(problems))
    db.commit()
    return quiz_detail(db, z)


@router.post("/{quiz_id}/items", response_model=QuizDetail)
def update_items(quiz_id: int, body: ItemsUpdate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status != "draft":
        raise HTTPException(409, "Questions can only change while the quiz is a draft.")
    by_id = {i.id: i for i in z.items}
    for iid in body.remove_item_ids or []:
        if iid in by_id:
            z.items.remove(by_id.pop(iid))
    for m in body.marks or []:
        if m.item_id in by_id:
            by_id[m.item_id].marks = m.marks
    for qid in body.add_question_ids or []:
        q = perm.own_question(db, user, qid)
        if q.review_status == "personal":
            raise HTTPException(422, "Personal practice questions cannot be added to an assessment.")
        if any(i.question_id == q.id for i in z.items):
            continue
        z.items.append(QuizQuestion(question_id=q.id, position=len(z.items) + 1000, marks=1.0))
    if body.order:
        if sorted(body.order) != sorted(by_id):
            raise HTTPException(422, "The new order must list every question in the quiz once.")
        for k, iid in enumerate(body.order):
            by_id[iid].position = k
    db.flush()
    _renumber(z)
    db.commit()
    db.refresh(z)
    return quiz_detail(db, z)


@router.post("/{quiz_id}/publish", response_model=QuizDetail)
def publish(quiz_id: int, user: User = Depends(verified_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status != "draft":
        raise HTTPException(409, f"Only a draft can be published (this quiz is {z.status}).")
    if z.course_id:
        perm.own_course(db, user, z.course_id)
    problems = validate_for_publish(db, z)
    if problems:
        raise HTTPException(422, " ".join(problems))
    z.status, z.published_at = "published", utcnow()
    if not db.scalar(select(QuizAssignment.id).where(QuizAssignment.quiz_id == z.id)):
        db.add(QuizAssignment(quiz_id=z.id, course_id=z.course_id, student_id=None))
    db.commit()
    return quiz_detail(db, z)


@router.post("/{quiz_id}/unpublish", response_model=QuizDetail)
def unpublish(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status != "published":
        raise HTTPException(409, "The quiz is not published.")
    if _has_attempts(db, z.id):
        raise HTTPException(409, "Students have already started this quiz. Archive it instead.")
    z.status = "draft"
    db.commit()
    return quiz_detail(db, z)


@router.post("/{quiz_id}/archive", response_model=QuizDetail)
def archive(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status == "generating":
        raise HTTPException(409, "Wait for generation to finish or cancel it first.")
    z.status = "archived"
    db.commit()
    return quiz_detail(db, z)


@router.post("/{quiz_id}/release-feedback", response_model=QuizDetail)
def release_feedback(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    z.feedback_released = True
    db.commit()
    return quiz_detail(db, z)


@router.get("/{quiz_id}/preview")
def preview(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """Exactly what a student receives when starting the quiz (no answer keys)."""
    z = perm.own_quiz(db, user, quiz_id)
    return {"title": z.title, "instructions": z.instructions, "time_limit_min": z.time_limit_min,
            "max_marks": z.max_marks, "confidence_enabled": z.confidence_enabled,
            "questions": [{"question_id": i.question_id, "position": i.position + 1, "marks": i.marks,
                           "text": i.question.text, "difficulty": i.question.difficulty, "topic": i.question.topic_label,
                           "options": [{"id": o.id, "label": o.label, "text": o.text} for o in i.question.options]}
                          for i in z.items]}


@router.delete("/{quiz_id}", status_code=204)
def delete_draft(quiz_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    z = perm.own_quiz(db, user, quiz_id)
    if z.status not in ("draft", "archived") or _has_attempts(db, z.id):
        raise HTTPException(409, "Only drafts without attempts can be deleted.")
    db.delete(z)
    db.commit()


@router.post("", response_model=QuizDetail, status_code=201)
def create_empty(course_id: int, subject_id: int, title: str, user: User = Depends(require_lecturer),
                 db: Session = Depends(get_db)):
    """A draft quiz built by hand from the question bank (no generation)."""
    c = perm.own_course(db, user, course_id)
    s = perm.own_subject(db, user, subject_id)
    if s.course_id != c.id:
        raise HTTPException(422, "The subject does not belong to that course.")
    if not 2 <= len(title.strip()) <= 200:
        raise HTTPException(422, "The title needs 2 to 200 characters.")
    z = Quiz(owner_id=user.id, kind="assessment", course_id=c.id, subject_id=s.id, title=title.strip(), status="draft")
    db.add(z)
    db.commit()
    return quiz_detail(db, z)

