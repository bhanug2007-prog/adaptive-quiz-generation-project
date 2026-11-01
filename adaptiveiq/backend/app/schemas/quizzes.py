from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Difficulty = Literal["easy", "medium", "hard"]
DifficultyChoice = Literal["easy", "medium", "hard", "mixed"]


def _clean(v: str | None) -> str | None:
    return " ".join(v.split()) if isinstance(v, str) else v


class Distribution(BaseModel):
    easy: int = Field(default=0, ge=0, le=30)
    medium: int = Field(default=0, ge=0, le=30)
    hard: int = Field(default=0, ge=0, le=30)

    @property
    def total(self) -> int:
        return self.easy + self.medium + self.hard


class DraftGenerateRequest(BaseModel):
    """Lecturer quiz builder, steps 1-3."""
    course_id: int
    subject_id: int
    topic_id: int
    title: str = Field(min_length=2, max_length=200)
    question_count: int = Field(ge=1, le=30)
    difficulty: DifficultyChoice = "mixed"
    distribution: Distribution | None = None
    reference_text: str | None = Field(default=None, max_length=12000)
    objective_ids: list[int] = Field(default=[], max_length=10)
    target_duration_min: int | None = Field(default=None, ge=1, le=300)
    marks_each: float = Field(default=1.0, gt=0, le=100)

    @model_validator(mode="after")
    def _dist(self):
        if self.distribution and self.distribution.total != self.question_count:
            raise ValueError(f"The difficulty mix adds up to {self.distribution.total}, not {self.question_count} questions.")
        if self.reference_text is not None and len(self.reference_text.split()) < 40:
            if self.reference_text.strip():
                raise ValueError("Reference material needs at least 40 words, or leave it empty.")
            self.reference_text = None
        return self


class PracticeGenerateRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=160)
    topic: str = Field(min_length=2, max_length=160)
    topic_id: int | None = None                       # a topic from an enrolled course, if picked
    unit: str | None = Field(default=None, max_length=160)
    question_count: Literal[5, 10, 15, 20] = 5
    difficulty: Literal["easy", "medium", "hard", "mixed", "adaptive"] = "mixed"
    reference_text: str | None = Field(default=None, max_length=12000)
    time_limit_min: int | None = Field(default=None, ge=1, le=180)
    confidence_enabled: bool = True

    @field_validator("subject", "topic", "unit")
    @classmethod
    def _c(cls, v):
        return _clean(v)

    @model_validator(mode="after")
    def _ref(self):
        if self.reference_text is not None and len(self.reference_text.split()) < 40:
            if self.reference_text.strip():
                raise ValueError("Reference material needs at least 40 words, or leave it empty.")
            self.reference_text = None
        return self


class RunStatus(BaseModel):
    run_id: int
    status: str
    stage: str
    ready: int
    total: int
    attempts: int
    rejected: dict[str, int]
    rejected_reasons: dict[str, str]
    error: str | None
    quiz_id: int | None
    queue_position: int
    elapsed_s: float
    avg_question_s: float | None
    grounded_on: str | None
    difficulty_note: str | None = None


class OptionOut(BaseModel):
    id: int
    label: str
    text: str


class OptionFull(OptionOut):
    is_correct: bool


class QuestionFull(BaseModel):
    """Owner view, includes the key."""
    id: int
    text: str
    explanation: str | None
    difficulty: str
    subject_label: str
    unit_label: str | None
    topic_label: str
    topic_id: int | None
    objective_id: int | None
    course_id: int | None
    review_status: str
    source_type: str
    source_excerpt: str | None
    validation: dict
    model: str | None
    options: list[OptionFull]
    created_at: datetime
    updated_at: datetime
    used_in_quizzes: int = 0
    answered_count: int = 0
    locked: bool = False                              # has student answers: edit a copy instead


def check_options(v):
    if v is None:
        return v
    v = [" ".join(o.split()) for o in v]
    if any(not o for o in v):
        raise ValueError("All four options need text.")
    if len({o.lower() for o in v}) < 4:
        raise ValueError("The four options must be different.")
    if any(len(o) > 500 for o in v):
        raise ValueError("Each option must be at most 500 characters.")
    return v


class QuestionEdit(BaseModel):
    text: str | None = Field(default=None, min_length=10, max_length=2000)
    options: list[str] | None = Field(default=None, min_length=4, max_length=4)
    correct_label: Literal["A", "B", "C", "D"] | None = None
    explanation: str | None = Field(default=None, max_length=3000)
    difficulty: Difficulty | None = None
    objective_id: int | None = None
    note: str | None = Field(default=None, max_length=500)

    @field_validator("options")
    @classmethod
    def _opts(cls, v):
        return check_options(v)


class QuestionCreate(BaseModel):
    """A question written by hand into the bank."""
    topic_id: int
    text: str = Field(min_length=10, max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_label: Literal["A", "B", "C", "D"]
    explanation: str | None = Field(default=None, max_length=3000)
    difficulty: Difficulty
    objective_id: int | None = None

    @field_validator("options")
    @classmethod
    def _opts(cls, v):
        return check_options(v)


class ReviewAction(BaseModel):
    action: Literal["approve", "reject", "reset"]
    note: str | None = Field(default=None, max_length=500)


class QuizItemOut(BaseModel):
    item_id: int
    position: int
    marks: float
    question: QuestionFull


class QuizSettings(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    instructions: str | None = Field(default=None, max_length=4000)
    graded: bool | None = None
    attempts_allowed: int | None = Field(default=None, ge=1, le=20)
    opens_at: datetime | None = None
    due_at: datetime | None = None
    closes_at: datetime | None = None
    time_limit_min: int | None = Field(default=None, ge=1, le=300)
    shuffle_questions: bool | None = None
    shuffle_options: bool | None = None
    feedback_release: Literal["immediate", "after_due", "manual"] | None = None
    late_policy: Literal["none", "allow", "penalty"] | None = None
    late_penalty_pct: float | None = Field(default=None, ge=0, le=100)
    contribution_pct: float | None = Field(default=None, ge=0, le=100)
    confidence_enabled: bool | None = None
    target_duration_min: int | None = Field(default=None, ge=1, le=300)

    @field_validator("opens_at", "due_at", "closes_at")
    @classmethod
    def _aware(cls, v):
        if v is not None and v.tzinfo is None:
            raise ValueError("Dates must include a time zone.")
        return v


class ItemMarks(BaseModel):
    item_id: int
    marks: float = Field(gt=0, le=100)


class ItemsUpdate(BaseModel):
    order: list[int] | None = None                    # item ids in the new order
    marks: list[ItemMarks] | None = None
    remove_item_ids: list[int] | None = None
    add_question_ids: list[int] | None = None         # from the bank


class QuizOut(BaseModel):
    id: int
    kind: str
    title: str
    instructions: str | None
    status: str
    course_id: int | None
    course_title: str | None = None
    subject_id: int | None
    subject_name: str | None = None
    topics: list[str] = []
    graded: bool
    max_marks: float
    question_count: int
    attempts_allowed: int
    opens_at: datetime | None
    due_at: datetime | None
    closes_at: datetime | None
    time_limit_min: int | None
    shuffle_questions: bool
    shuffle_options: bool
    feedback_release: str
    feedback_released: bool
    late_policy: str
    late_penalty_pct: float
    contribution_pct: float
    confidence_enabled: bool
    target_duration_min: int | None
    created_at: datetime
    published_at: datetime | None
    generation_run_id: int | None
    review_counts: dict[str, int] = {}


class QuizDetail(QuizOut):
    items: list[QuizItemOut] = []
    weight_cap_pct: float | None = None
    weight_used_elsewhere_pct: float | None = None


class StudentQuizCard(BaseModel):
    """What a student sees in Assigned Quizzes."""
    id: int
    title: str
    kind: str
    course_title: str | None
    subject: str | None
    topics: list[str]
    lecturer: str | None
    question_count: int
    max_marks: float
    time_limit_min: int | None
    opens_at: datetime | None
    due_at: datetime | None
    closes_at: datetime | None
    attempts_allowed: int
    attempts_used: int
    state: str                                        # upcoming | open | in_progress | submitted | expired | late_open
    in_progress_session_id: int | None
    last_session_id: int | None
    best_percentage: float | None
    graded: bool
    contribution_pct: float
    created_at: datetime
