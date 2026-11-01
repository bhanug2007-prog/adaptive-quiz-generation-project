from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import (current_user, get_db, require_lecturer, require_student,
                           verified_lecturer, verified_student)
from app.core.security import new_join_code
from app.models import (Course, CourseEnrollment, LearningObjective, Quiz, Subject, Topic, Unit, User)
from app.schemas.courses import (CourseCreate, CourseDetail, CourseOut, CourseUpdate, EnrollByEmail, EnrollResult,
                                 JoinRequest, ObjectiveCreate, ObjectiveOut, RosterEntry, SubjectCreate, SubjectOut,
                                 SubjectUpdate, TopicCreate, TopicOut, TopicUpdate, UnitCreate, UnitOut)
from app.services import permissions as perm
from app.services.grading import weight_used

router = APIRouter(prefix="/api", tags=["courses"])


def _course_out(db: Session, c: Course, owner: bool) -> CourseOut:
    students = db.scalar(select(func.count()).select_from(CourseEnrollment)
                         .where(CourseEnrollment.course_id == c.id, CourseEnrollment.status == "active"))
    quizzes = db.scalar(select(func.count()).select_from(Quiz).where(Quiz.course_id == c.id, Quiz.kind == "assessment",
                                                                     Quiz.status == "published"))
    lecturer = db.get(User, c.lecturer_id)
    return CourseOut(id=c.id, code=c.code, title=c.title, program=c.program, semester=c.semester,
                     academic_year=c.academic_year, archived=c.archived, created_at=c.created_at,
                     lecturer_name=lecturer.full_name if lecturer else None,
                     join_code=c.join_code if owner else None, join_enabled=c.join_enabled if owner else None,
                     student_count=students if owner else None, quiz_count=quizzes)


def _subject_out(db: Session, s: Subject) -> SubjectOut:
    return SubjectOut(id=s.id, name=s.name, code=s.code, quiz_weight_cap_pct=s.quiz_weight_cap_pct,
                      quiz_weight_used_pct=weight_used(db, s.id), grading_notes=s.grading_notes,
                      units=[UnitOut(id=u.id, name=u.name, position=u.position,
                                     topics=[_topic_out(t) for t in u.topics]) for u in s.units])


def _topic_out(t: Topic) -> TopicOut:
    return TopicOut(id=t.id, name=t.name, description=t.description, prerequisite_topic_id=t.prerequisite_topic_id,
                    objectives=[ObjectiveOut(id=o.id, code=o.code, text=o.text) for o in t.objectives])


def _detail(db: Session, c: Course, owner: bool) -> CourseDetail:
    base = _course_out(db, c, owner).model_dump()
    return CourseDetail(**base, subjects=[_subject_out(db, s) for s in c.subjects])


# ---------------- lecturer: courses ----------------

@router.get("/lecturer/courses", response_model=list[CourseOut])
def my_courses(user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    cs = db.scalars(select(Course).where(Course.lecturer_id == user.id).order_by(Course.archived, Course.created_at.desc()))
    return [_course_out(db, c, True) for c in cs]


@router.post("/lecturer/courses", response_model=CourseDetail, status_code=201)
def create_course(body: CourseCreate, user: User = Depends(verified_lecturer), db: Session = Depends(get_db)):
    if db.scalar(select(Course.id).where(Course.lecturer_id == user.id, Course.code == body.code.strip())):
        raise HTTPException(409, f"You already have a course with code {body.code}.")
    for _ in range(5):
        code = new_join_code()
        if not db.scalar(select(Course.id).where(Course.join_code == code)):
            break
    c = Course(lecturer_id=user.id, institution_id=user.institution_id, code=body.code.strip(), title=body.title.strip(),
               program=body.program, semester=body.semester, academic_year=body.academic_year, join_code=code)
    db.add(c)
    db.commit()
    return _detail(db, c, True)


@router.get("/lecturer/courses/{course_id}", response_model=CourseDetail)
def course_detail(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    return _detail(db, perm.own_course(db, user, course_id), True)


@router.patch("/lecturer/courses/{course_id}", response_model=CourseDetail)
def update_course(course_id: int, body: CourseUpdate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    c = perm.own_course(db, user, course_id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None or k in ("program", "semester", "academic_year"):
            setattr(c, k, v.strip() if isinstance(v, str) else v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "You already have a course with that code.")
    return _detail(db, c, True)


@router.post("/lecturer/courses/{course_id}/join-code", response_model=CourseDetail)
def rotate_join_code(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    c = perm.own_course(db, user, course_id)
    c.join_code = new_join_code()
    db.commit()
    return _detail(db, c, True)


# ---------------- lecturer: hierarchy ----------------

@router.post("/lecturer/courses/{course_id}/subjects", response_model=SubjectOut, status_code=201)
def add_subject(course_id: int, body: SubjectCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    c = perm.own_course(db, user, course_id)
    s = Subject(course_id=c.id, **body.model_dump())
    db.add(s)
    db.commit()
    return _subject_out(db, s)


@router.patch("/lecturer/subjects/{subject_id}", response_model=SubjectOut)
def update_subject(subject_id: int, body: SubjectUpdate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    s = perm.own_subject(db, user, subject_id)
    data = body.model_dump(exclude_unset=True)
    if "quiz_weight_cap_pct" in data and data["quiz_weight_cap_pct"] is not None:
        used = weight_used(db, s.id)
        if data["quiz_weight_cap_pct"] < used:
            raise HTTPException(422, f"Quizzes in this subject already use {used:g}% of the internal assessment.")
    for k, v in data.items():
        if v is not None or k in ("code", "grading_notes"):
            setattr(s, k, v)
    db.commit()
    return _subject_out(db, s)


@router.delete("/lecturer/subjects/{subject_id}", status_code=204)
def delete_subject(subject_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    s = perm.own_subject(db, user, subject_id)
    if db.scalar(select(Quiz.id).where(Quiz.subject_id == s.id, Quiz.status == "published")):
        raise HTTPException(409, "This subject has published quizzes. Archive the quizzes first.")
    db.delete(s)
    db.commit()


@router.post("/lecturer/subjects/{subject_id}/units", response_model=UnitOut, status_code=201)
def add_unit(subject_id: int, body: UnitCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    s = perm.own_subject(db, user, subject_id)
    u = Unit(subject_id=s.id, name=body.name.strip(), position=body.position if body.position is not None else len(s.units))
    db.add(u)
    db.commit()
    return UnitOut(id=u.id, name=u.name, position=u.position, topics=[])


@router.patch("/lecturer/units/{unit_id}", response_model=UnitOut)
def rename_unit(unit_id: int, body: UnitCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    u = perm.own_unit(db, user, unit_id)
    u.name = body.name.strip()
    if body.position is not None:
        u.position = body.position
    db.commit()
    return UnitOut(id=u.id, name=u.name, position=u.position, topics=[_topic_out(t) for t in u.topics])


@router.delete("/lecturer/units/{unit_id}", status_code=204)
def delete_unit(unit_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    u = perm.own_unit(db, user, unit_id)
    db.delete(u)
    db.commit()


@router.post("/lecturer/units/{unit_id}/topics", response_model=TopicOut, status_code=201)
def add_topic(unit_id: int, body: TopicCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    u = perm.own_unit(db, user, unit_id)
    if body.prerequisite_topic_id:
        perm.own_topic(db, user, body.prerequisite_topic_id)
    t = Topic(unit_id=u.id, name=body.name.strip(), description=body.description,
              prerequisite_topic_id=body.prerequisite_topic_id)
    db.add(t)
    db.commit()
    return _topic_out(t)


@router.patch("/lecturer/topics/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicUpdate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    t = perm.own_topic(db, user, topic_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("prerequisite_topic_id"):
        if data["prerequisite_topic_id"] == t.id:
            raise HTTPException(422, "A topic cannot be its own prerequisite.")
        perm.own_topic(db, user, data["prerequisite_topic_id"])
    for k, v in data.items():
        if k == "name" and v:
            t.name = v.strip()
        elif k != "name":
            setattr(t, k, v)
    db.commit()
    return _topic_out(t)


@router.delete("/lecturer/topics/{topic_id}", status_code=204)
def delete_topic(topic_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    t = perm.own_topic(db, user, topic_id)
    db.delete(t)
    db.commit()


@router.post("/lecturer/topics/{topic_id}/objectives", response_model=ObjectiveOut, status_code=201)
def add_objective(topic_id: int, body: ObjectiveCreate, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    t = perm.own_topic(db, user, topic_id)
    o = LearningObjective(topic_id=t.id, code=body.code, text=body.text.strip())
    db.add(o)
    db.commit()
    return ObjectiveOut(id=o.id, code=o.code, text=o.text)


@router.delete("/lecturer/objectives/{objective_id}", status_code=204)
def delete_objective(objective_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    o = db.get(LearningObjective, objective_id)
    if o is None or o.topic.unit.subject.course.lecturer_id != user.id:
        raise perm.not_found("Objective")
    db.delete(o)
    db.commit()


# ---------------- lecturer: roster ----------------

@router.get("/lecturer/courses/{course_id}/roster", response_model=list[RosterEntry])
def roster(course_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    c = perm.own_course(db, user, course_id)
    rows = db.execute(select(CourseEnrollment, User).join(User, User.id == CourseEnrollment.student_id)
                      .where(CourseEnrollment.course_id == c.id).order_by(User.full_name))
    return [RosterEntry(student_id=u.id, full_name=u.full_name, email=u.email,
                        roll_number=u.student_profile.roll_number if u.student_profile else None, status=e.status,
                        enrolled_via=e.enrolled_via, enrolled_at=e.enrolled_at) for e, u in rows]


@router.post("/lecturer/courses/{course_id}/enroll", response_model=EnrollResult)
def enroll_by_email(course_id: int, body: EnrollByEmail, user: User = Depends(verified_lecturer), db: Session = Depends(get_db)):
    """Adds students who already have accounts. Unknown emails are reported back, never auto-created."""
    c = perm.own_course(db, user, course_id)
    res = EnrollResult(enrolled=[], already_enrolled=[], not_found=[])
    for email in dict.fromkeys(e.lower() for e in body.emails):
        st = db.scalar(select(User).where(User.email == email, User.role == "student"))
        if st is None:
            res.not_found.append(email)
            continue
        e = db.scalar(select(CourseEnrollment).where(CourseEnrollment.course_id == c.id, CourseEnrollment.student_id == st.id))
        if e and e.status == "active":
            res.already_enrolled.append(email)
        elif e:
            e.status, e.enrolled_via = "active", "lecturer"
            res.enrolled.append(email)
        else:
            db.add(CourseEnrollment(course_id=c.id, student_id=st.id, enrolled_via="lecturer"))
            res.enrolled.append(email)
    db.commit()
    return res


@router.delete("/lecturer/courses/{course_id}/students/{student_id}", status_code=204)
def remove_student(course_id: int, student_id: int, user: User = Depends(require_lecturer), db: Session = Depends(get_db)):
    """Marks the enrollment removed; the student's past attempts stay for the record."""
    c = perm.own_course(db, user, course_id)
    e = db.scalar(select(CourseEnrollment).where(CourseEnrollment.course_id == c.id, CourseEnrollment.student_id == student_id))
    if e is None:
        raise perm.not_found("Student")
    e.status = "removed"
    db.commit()


# ---------------- student ----------------

@router.post("/student/courses/join", response_model=CourseOut)
def join_course(body: JoinRequest, user: User = Depends(verified_student), db: Session = Depends(get_db)):
    c = db.scalar(select(Course).where(Course.join_code == body.join_code.strip().upper()))
    if c is None or not c.join_enabled or c.archived:
        raise HTTPException(404, "No open course has this join code. Check it with your lecturer.")
    e = db.scalar(select(CourseEnrollment).where(CourseEnrollment.course_id == c.id, CourseEnrollment.student_id == user.id))
    if e and e.status == "removed":
        raise HTTPException(403, "You were removed from this course. Ask your lecturer to add you again.")
    if e is None:
        db.add(CourseEnrollment(course_id=c.id, student_id=user.id, enrolled_via="join_code"))
        db.commit()
    return _course_out(db, c, False)


@router.get("/student/courses", response_model=list[CourseDetail])
def student_courses(user: User = Depends(require_student), db: Session = Depends(get_db)):
    ids = perm.enrolled_course_ids(db, user)
    cs = db.scalars(select(Course).where(Course.id.in_(ids)).order_by(Course.title)) if ids else []
    return [_detail(db, c, False) for c in cs]


@router.get("/topics/search")
def topic_choices(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Course topics this user can pick in a quiz form (lecturer: own courses, student: enrolled)."""
    ids = perm.lecturer_course_ids(db, user) if user.role == "lecturer" else perm.enrolled_course_ids(db, user)
    if not ids:
        return []
    rows = db.execute(select(Topic, Unit, Subject, Course).join(Unit, Unit.id == Topic.unit_id)
                      .join(Subject, Subject.id == Unit.subject_id).join(Course, Course.id == Subject.course_id)
                      .where(Course.id.in_(ids)).order_by(Course.title, Subject.name, Unit.position, Topic.id))
    return [{"topic_id": t.id, "topic": t.name, "unit_id": u.id, "unit": u.name, "subject_id": s.id, "subject": s.name,
             "course_id": c.id, "course": c.title, "objectives": [{"id": o.id, "text": o.text} for o in t.objectives]}
            for t, u, s, c in rows]
