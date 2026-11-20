"""Importing this package registers every table on Base.metadata (needed by Alembic and tests)."""
from app.models.attempts import (LearningRecommendation, QuizResult, QuizSession, RevisionSchedule,  # noqa: F401
                                 StudentAnswer, TopicMasterySnapshot)
from app.models.courses import Course, CourseEnrollment, LearningObjective, Subject, Topic, Unit  # noqa: F401
from app.models.integrations import ExternalIntegration, FormExport  # noqa: F401
from app.models.learning_agent import (LangGraphCheckpoint, LangGraphCheckpointBlob,  # noqa: F401
                                       LangGraphCheckpointWrite, LearningPlan, LearningPlanExecution,
                                       LearningPlanItem)
from app.models.monitoring import MonitoringEvent, MonitoringSession  # noqa: F401
from app.models.quizzes import (AgentRun, AgentStep, AnswerOption, GenerationRun, ModelVersion,  # noqa: F401
                                Question, QuestionEvaluation, QuestionReviewRecord, Quiz, QuizAssignment,
                                QuizQuestion)
from app.models.users import Institution, LecturerProfile, PasswordResetToken, StudentProfile, User  # noqa: F401
