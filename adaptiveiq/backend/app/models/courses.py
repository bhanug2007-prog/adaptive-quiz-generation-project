from datetime import datetime

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.base import UTCDateTime, utcnow


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    lecturer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("institutions.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(200))
    program: Mapped[str | None] = mapped_column(String(120))
    semester: Mapped[int | None] = mapped_column(Integer)
    academic_year: Mapped[str | None] = mapped_column(String(20))
    join_code: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    join_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    subjects: Mapped[list["Subject"]] = relationship(back_populates="course", cascade="all, delete-orphan",
                                                     order_by="Subject.id")
    __table_args__ = (UniqueConstraint("lecturer_id", "code", name="uq_course_lecturer_code"),)


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")        # active | removed
    enrolled_via: Mapped[str] = mapped_column(String(20), default="join_code")  # join_code | lecturer
    enrolled_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    __table_args__ = (UniqueConstraint("course_id", "student_id", name="uq_enrollment"),)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    code: Mapped[str | None] = mapped_column(String(30))
    # Percentage of the subject's internal assessment that quizzes may contribute in total (lecturer's scheme)
    quiz_weight_cap_pct: Mapped[float] = mapped_column(Float, default=100.0)
    grading_notes: Mapped[str | None] = mapped_column(Text)
    course: Mapped[Course] = relationship(back_populates="subjects")
    units: Mapped[list["Unit"]] = relationship(back_populates="subject", cascade="all, delete-orphan",
                                               order_by="Unit.position")


class Unit(Base):
    __tablename__ = "units"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    position: Mapped[int] = mapped_column(Integer, default=0)
    subject: Mapped[Subject] = relationship(back_populates="units")
    topics: Mapped[list["Topic"]] = relationship(back_populates="unit", cascade="all, delete-orphan",
                                                 order_by="Topic.id")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("units.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    prerequisite_topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id", ondelete="SET NULL"))
    unit: Mapped[Unit] = relationship(back_populates="topics")
    objectives: Mapped[list["LearningObjective"]] = relationship(back_populates="topic", cascade="all, delete-orphan",
                                                                 order_by="LearningObjective.id")


class LearningObjective(Base):
    __tablename__ = "learning_objectives"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"), index=True)
    code: Mapped[str | None] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(String(400))
    topic: Mapped[Topic] = relationship(back_populates="objectives")
