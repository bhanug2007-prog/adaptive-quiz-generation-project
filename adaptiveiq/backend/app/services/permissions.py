"""Resource-level access rules. Every API handler goes through these; hiding buttons is not security.

Lookups that fail authorization raise 404, not 403, so ids of other users' records are not confirmed.
"""
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (Course, CourseEnrollment, Question, Quiz, QuizAssignment, QuizSession, Subject, Topic, Unit,
                        User)


def not_found(what: str = "Item") -> HTTPException:
    return HTTPException(404, f"{what} not found.")


def own_course(db: Session, lecturer: User, course_id: int) -> Course:
    c = db.get(Course, course_id)
    if c is None or c.lecturer_id != lecturer.id:
        raise not_found("Course")
    return c


def own_subject(db: Session, lecturer: User, subject_id: int) -> Subject:
    s = db.get(Subject, subject_id)
    if s is None or s.course.lecturer_id != lecturer.id:
        raise not_found("Subject")
    return s


def own_unit(db: Session, lecturer: User, unit_id: int) -> Unit:
    u = db.get(Unit, unit_id)
    if u is None or u.subject.course.lecturer_id != lecturer.id:
        raise not_found("Unit")
    return u


def own_topic(db: Session, lecturer: User, topic_id: int) -> Topic:
    t = db.get(Topic, topic_id)
    if t is None or t.unit.subject.course.lecturer_id != lecturer.id:
        raise not_found("Topic")
    return t


def own_question(db: Session, user: User, question_id: int) -> Question:
    q = db.get(Question, question_id)
    if q is None or q.owner_id != user.id:
        raise not_found("Question")
    return q


def own_quiz(db: Session, user: User, quiz_id: int) -> Quiz:
    q = db.get(Quiz, quiz_id)
    if q is None or q.owner_id != user.id:
        raise not_found("Quiz")
    return q


def enrolled_course_ids_for(db: Session, student_id: int) -> list[int]:
    return list(db.scalars(select(CourseEnrollment.course_id).where(CourseEnrollment.student_id == student_id,
                                                                    CourseEnrollment.status == "active")))


def enrolled_course_ids(db: Session, student: User) -> list[int]:
    return enrolled_course_ids_for(db, student.id)


def is_enrolled(db: Session, student_id: int, course_id: int) -> bool:
    return db.scalar(select(CourseEnrollment.id).where(CourseEnrollment.student_id == student_id,
                                                       CourseEnrollment.course_id == course_id,
                                                       CourseEnrollment.status == "active")) is not None


def assigned_quiz_ids(db: Session, student: User) -> list[int]:
    courses = enrolled_course_ids(db, student)
    if not courses:
        return []
    rows = db.scalars(select(QuizAssignment.quiz_id).where(
        QuizAssignment.course_id.in_(courses),
        or_(QuizAssignment.student_id.is_(None), QuizAssignment.student_id == student.id)))
    return sorted(set(rows))


def student_quiz(db: Session, student: User, quiz_id: int) -> Quiz:
    """A quiz the student may see: their own practice quiz, or a published assessment assigned to them."""
    q = db.get(Quiz, quiz_id)
    if q is None:
        raise not_found("Quiz")
    if q.kind == "practice" and q.owner_id == student.id:
        return q
    if q.kind == "assessment" and q.status == "published" and quiz_id in assigned_quiz_ids(db, student):
        return q
    raise not_found("Quiz")


def student_session(db: Session, student: User, session_id: int) -> QuizSession:
    s = db.get(QuizSession, session_id)
    if s is None or s.student_id != student.id:
        raise not_found("Attempt")
    return s


def lecturer_student(db: Session, lecturer: User, student_id: int) -> User:
    """A student the lecturer may see: enrolled (now or before) in one of the lecturer's courses."""
    row = db.scalar(select(CourseEnrollment.id).join(Course, Course.id == CourseEnrollment.course_id)
                    .where(Course.lecturer_id == lecturer.id, CourseEnrollment.student_id == student_id))
    u = db.get(User, student_id)
    if row is None or u is None:
        raise not_found("Student")
    return u


def lecturer_course_ids(db: Session, lecturer: User) -> list[int]:
    return list(db.scalars(select(Course.id).where(Course.lecturer_id == lecturer.id)))
