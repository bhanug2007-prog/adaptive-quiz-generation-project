from datetime import datetime

from pydantic import BaseModel, Field


class AttemptOption(BaseModel):
    id: int
    label: str                       # display letter in this attempt's order
    text: str


class AttemptQuestion(BaseModel):
    question_id: int
    number: int
    text: str
    topic: str
    difficulty: str
    marks: float
    options: list[AttemptOption]


class SavedAnswer(BaseModel):
    option_id: int | None
    confidence: int | None
    checked: bool
    time_spent_s: float | None = None


class AttemptOut(BaseModel):
    session_id: int
    quiz_id: int
    quiz_title: str
    kind: str
    instructions: str | None
    attempt_no: int
    status: str
    started_at: datetime
    deadline_at: datetime | None
    server_now: datetime
    confidence_enabled: bool
    can_check_answers: bool          # practice: reveal answers one by one
    monitoring: dict | None = None   # what is monitored and the browser settings, when the attempt is monitored
    questions: list[AttemptQuestion]
    answers: dict[int, SavedAnswer]


class AnswerSave(BaseModel):
    option_id: int | None = None
    confidence: int | None = Field(default=None, ge=1, le=3)
    time_spent_s: float | None = Field(default=None, ge=0)


class ReviewOption(BaseModel):
    id: int
    label: str
    text: str
    is_correct: bool
    selected: bool


class ReviewItem(BaseModel):
    question_id: int
    number: int
    text: str
    topic: str
    difficulty: str
    marks: float
    outcome: str                     # correct | incorrect | skipped
    confidence: int | None
    options: list[ReviewOption]
    explanation: str | None
    math_verified: bool
    source_excerpt: str | None       # only when generated from supplied reference material
    source_ref: dict | None = None
    time_spent_s: float | None


class TopicPerformance(BaseModel):
    topic_key: str
    topic: str
    correct: int
    incorrect: int
    skipped: int
    accuracy: float | None
    mastery_label: str | None = None
    mastery_score: float | None = None
    next_difficulty: str | None = None


class ResultOut(BaseModel):
    session_id: int
    quiz_id: int
    quiz_title: str
    kind: str
    attempt_no: int
    submitted_at: datetime
    submitted_by: str | None
    is_late: bool
    feedback_available: bool
    feedback_message: str | None = None
    raw_score: float | None = None
    max_score: float | None = None
    percentage: float | None = None
    late_penalty_pct: float | None = None
    final_percentage: float | None = None
    contribution_pct: float | None = None
    contribution_earned: float | None = None
    correct: int | None = None
    incorrect: int | None = None
    unanswered: int | None = None
    duration_s: float | None = None
    active_time_s: float | None = None
    items: list[ReviewItem] = []
    topics: list[TopicPerformance] = []
    recommendations: list[dict] = []
    can_retry: bool = False


class HistoryEntry(BaseModel):
    session_id: int
    quiz_id: int
    quiz_title: str
    kind: str
    course_title: str | None
    topics: list[str]
    attempt_no: int
    status: str
    started_at: datetime
    submitted_at: datetime | None
    percentage: float | None
    correct: int | None
    incorrect: int | None
    unanswered: int | None
    feedback_available: bool
