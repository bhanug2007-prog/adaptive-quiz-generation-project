from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    title: str = Field(min_length=2, max_length=200)
    program: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    academic_year: str | None = Field(default=None, max_length=20)


class CourseUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=30)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    program: str | None = Field(default=None, max_length=120)
    semester: int | None = Field(default=None, ge=1, le=12)
    academic_year: str | None = Field(default=None, max_length=20)
    join_enabled: bool | None = None
    archived: bool | None = None


class SubjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=30)
    quiz_weight_cap_pct: float = Field(default=100.0, ge=0, le=100)
    grading_notes: str | None = Field(default=None, max_length=2000)


class SubjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    code: str | None = Field(default=None, max_length=30)
    quiz_weight_cap_pct: float | None = Field(default=None, ge=0, le=100)
    grading_notes: str | None = Field(default=None, max_length=2000)


class UnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    position: int | None = Field(default=None, ge=0)


class TopicCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    prerequisite_topic_id: int | None = None


class TopicUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    prerequisite_topic_id: int | None = None


class ObjectiveCreate(BaseModel):
    text: str = Field(min_length=3, max_length=400)
    code: str | None = Field(default=None, max_length=30)


class ObjectiveOut(BaseModel):
    id: int
    code: str | None
    text: str


class TopicOut(BaseModel):
    id: int
    name: str
    description: str | None
    prerequisite_topic_id: int | None
    objectives: list[ObjectiveOut] = []


class UnitOut(BaseModel):
    id: int
    name: str
    position: int
    topics: list[TopicOut] = []


class SubjectOut(BaseModel):
    id: int
    name: str
    code: str | None
    quiz_weight_cap_pct: float
    quiz_weight_used_pct: float = 0.0
    grading_notes: str | None
    units: list[UnitOut] = []


class CourseOut(BaseModel):
    id: int
    code: str
    title: str
    program: str | None
    semester: int | None
    academic_year: str | None
    archived: bool
    created_at: datetime
    lecturer_name: str | None = None
    join_code: str | None = None        # only for the owning lecturer
    join_enabled: bool | None = None
    student_count: int | None = None
    quiz_count: int | None = None


class CourseDetail(CourseOut):
    subjects: list[SubjectOut] = []


class EnrollByEmail(BaseModel):
    emails: list[EmailStr] = Field(min_length=1, max_length=200)


class EnrollResult(BaseModel):
    enrolled: list[str]
    already_enrolled: list[str]
    not_found: list[str]                # no student account with this email; they must register first


class JoinRequest(BaseModel):
    join_code: str = Field(min_length=4, max_length=12)


class RosterEntry(BaseModel):
    student_id: int
    full_name: str
    email: str
    roll_number: str | None
    status: str
    enrolled_via: str
    enrolled_at: datetime
