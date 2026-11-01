"""AI question generation as background runs stored in the database.

A laptop CPU needs about a minute per question, so generation never blocks a request: the API creates
a GenerationRun row and a quiz in status "generating", then one worker thread fills it question by
question while the frontend polls the run. One worker, because the model server answers one request at
a time. Each accepted question is committed at once, so progress survives a page refresh.
"""
import logging
import math
import queue
import re
import threading
import time
from collections import Counter

from sqlalchemy import select

from app.core.config import Settings
from app.core.db import Database
from app.models import (AnswerOption, GenerationRun, ModelVersion, Question, QuestionReviewRecord, Quiz,
                        QuizQuestion)
from app.models.base import utcnow
from app.services.model_service import ModelBadResponse, ModelError, ModelService
from app.services.validation_service import Validator

log = logging.getLogger("adaptiveiq.generation")
LEVELS = ["easy", "medium", "hard"]
BANK_DUP_LIMIT = 300


def split_reference(text: str, target_words: int = 150) -> list[str]:
    """Cut pasted notes into pieces about the size of the training contexts (~145 words)."""
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    chunks, cur = [], []
    for s in sentences:
        cur.append(s)
        if len(" ".join(cur).split()) >= target_words:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        tail = " ".join(cur)
        if chunks and len(tail.split()) < target_words // 2:
            chunks[-1] += " " + tail
        else:
            chunks.append(tail)
    return [c for c in chunks if c.strip()]


def difficulty_plan(difficulty: str, n: int, distribution: dict | None = None) -> list[str]:
    """`distribution` like {"easy": 2, "medium": 3, "hard": 1} wins over `difficulty`.
    Levels are interleaved so a stopped run still has a spread."""
    if distribution:
        counts = {lvl: int(distribution.get(lvl, 0)) for lvl in LEVELS}
        out = []
        while any(counts.values()):
            for lvl in LEVELS:
                if counts[lvl]:
                    out.append(lvl)
                    counts[lvl] -= 1
        return out
    return [LEVELS[i % 3] for i in range(n)] if difficulty == "mixed" else [difficulty] * n


def model_version_id(db, s: Settings) -> int:
    adapter = s.model_adapter if s.model_variant == "finetuned" else None
    mv = db.scalar(select(ModelVersion).where(ModelVersion.name == s.model_name, ModelVersion.variant == s.model_variant,
                                              ModelVersion.base_model == s.model_base_id,
                                              ModelVersion.adapter.is_(adapter) if adapter is None else ModelVersion.adapter == adapter,
                                              ModelVersion.quantization == s.model_quantization))
    if mv is None:
        mv = ModelVersion(name=s.model_name, variant=s.model_variant, base_model=s.model_base_id, adapter=adapter,
                          quantization=s.model_quantization)
        db.add(mv)
        db.flush()
    return mv.id


def question_snapshot(q: Question) -> dict:
    return {"text": q.text, "explanation": q.explanation, "difficulty": q.difficulty,
            "options": [{"label": o.label, "text": o.text, "is_correct": o.is_correct} for o in q.options]}


class GenerationService:
    def __init__(self, settings: Settings, database: Database, model: ModelService):
        self.s, self.dbm, self.model = settings, database, model
        self.validator = Validator(settings, model)
        self.queue: "queue.Queue[int]" = queue.Queue()
        self.cancel_flags: dict[int, threading.Event] = {}
        self._worker = threading.Thread(target=self._work, daemon=True, name="question-generator")
        self._started = False

    def start(self):
        self._recover()
        if not self._started:
            self._worker.start()
            self._started = True

    # ---------- public ----------

    def enqueue(self, run_id: int):
        self.cancel_flags[run_id] = threading.Event()
        self.queue.put(run_id)

    def cancel(self, run_id: int):
        flag = self.cancel_flags.get(run_id)
        if flag:
            flag.set()

    def queue_length(self) -> int:
        return self.queue.qsize()

    # ---------- recovery ----------

    def _recover(self):
        """Runs left queued/running by a previous process can never finish: close them honestly."""
        with self.dbm.session() as db:
            for run in db.scalars(select(GenerationRun).where(GenerationRun.status.in_(["queued", "running"]))):
                run.status, run.finished_at = "failed", utcnow()
                run.error = "The server restarted before this generation finished."
                self._close_quiz(db, run)
            db.commit()

    # ---------- worker ----------

    def _work(self):
        while True:
            run_id = self.queue.get()
            try:
                self._process(run_id)
            except Exception:
                log.exception("generation run %s crashed", run_id)
                with self.dbm.session() as db:
                    run = db.get(GenerationRun, run_id)
                    if run and run.status in ("queued", "running"):
                        run.status, run.finished_at = "failed", utcnow()
                        run.error = "Unexpected server error while generating. Check the backend log."
                        self._close_quiz(db, run)
                        db.commit()
            finally:
                self.cancel_flags.pop(run_id, None)

    def _process(self, run_id: int):
        flag = self.cancel_flags.get(run_id) or threading.Event()
        with self.dbm.session() as db:
            run = db.get(GenerationRun, run_id)
            if run is None or run.status != "queued":
                return
            if flag.is_set():
                run.status, run.stage, run.finished_at = "cancelled", "Cancelled", utcnow()
                self._close_quiz(db, run)
                db.commit()
                return
            run.status, run.started_at, run.stage = "running", utcnow(), "Starting"
            db.commit()
            rejected: Counter = Counter()
            times: list[float] = []
            try:
                contexts, grounded_on = self._contexts(db, run, flag)
                run.grounded_on = grounded_on
                db.commit()
                self._generate(db, run, contexts, flag, rejected, times)
            except ModelError as e:
                run.rejected = dict(rejected)
                if run.ready == 0:
                    run.status, run.error = "failed", str(e)
                else:
                    run.status, run.error = "partial", f"{e} Stopped after {run.ready} questions."
            else:
                run.rejected = dict(rejected)
                if flag.is_set():
                    run.status, run.stage = "cancelled", "Cancelled"
                elif run.ready == 0:
                    run.status = "failed"
                    run.error = ("The model did not produce any question that passed the checks. "
                                 "Try a more specific topic or paste reference material.")
                elif run.ready < run.total:
                    run.status, run.stage = "partial", f"{run.ready} of {run.total} questions passed the checks"
                else:
                    run.status, run.stage = "done", "Questions ready"
            run.finished_at = utcnow()
            run.avg_question_s = round(sum(times) / len(times), 1) if times else None
            self._close_quiz(db, run)
            db.commit()

    def _close_quiz(self, db, run: GenerationRun):
        quiz_id = (run.params or {}).get("quiz_id")
        quiz = db.get(Quiz, quiz_id) if quiz_id else None
        if quiz is None or quiz.status != "generating":
            return
        has_items = bool(quiz.items)
        quiz.max_marks = float(sum(i.marks for i in quiz.items))
        if not has_items:
            quiz.status = "archived"
        elif quiz.kind == "practice":
            quiz.status, quiz.published_at = "published", utcnow()
        else:
            quiz.status = "draft"                              # lecturer must review before publishing

    def _contexts(self, db, run: GenerationRun, flag) -> tuple[list[str], str]:
        p = run.params
        if p.get("reference_text"):
            run.stage = "Reading the reference material"
            db.commit()
            return split_reference(p["reference_text"]), "reference_text"
        # The model was trained to write a question from a ~145-word context, so without reference
        # material it first writes short study notes on a few subtopics (or the lecturer's objectives).
        n_notes = min(5, max(1, math.ceil(run.total / 4)))
        objectives = [o for o in (p.get("objectives") or []) if o.strip()][:5]
        if objectives:
            aspects = objectives
        else:
            run.stage = "Planning subtopics"
            db.commit()
            aspects = self.model.generate_aspects(p["subject"], p["topic"], n_notes) or [p["topic"]]
        notes = []
        for k, aspect in enumerate(aspects, 1):
            if flag.is_set():
                break
            run.stage = f"Writing study notes {k} of {len(aspects)}"
            db.commit()
            note = self.model.generate_notes(p["subject"], p["topic"], aspect)
            if len(note.split()) >= 40:
                notes.append(note)
        if not notes and not flag.is_set():
            raise ModelBadResponse("The model could not write study notes for this topic. Try adding reference material.")
        return notes, "generated_notes"

    def _existing_texts(self, db, run: GenerationRun) -> list[str]:
        p = run.params
        q = (select(Question.text).where(Question.topic_key == p["topic_key"], Question.review_status != "rejected")
             .order_by(Question.id.desc()).limit(BANK_DUP_LIMIT))
        if p.get("purpose") == "practice":
            q = q.where(Question.owner_id == run.requested_by)
        return list(db.scalars(q))

    def _generate(self, db, run: GenerationRun, contexts: list[str], flag, rejected: Counter, times: list[float]):
        p = run.params
        if not contexts:
            return
        plan = difficulty_plan(p.get("difficulty", "mixed"), run.total, p.get("distribution"))
        existing = self._existing_texts(db, run)
        mv_id = model_version_id(db, self.s)
        run.model_version_id = mv_id                   # so reliability can be reported per model version
        bad_responses = 0
        for i, level in enumerate(plan):
            t0 = time.time()
            for attempt in range(self.s.max_attempts_per_question):
                if flag.is_set():
                    return
                run.stage = f"Generating question {i + 1} of {run.total}" + (f" (retry {attempt})" if attempt else "")
                run.attempts += 1
                db.commit()
                ctx = contexts[(i + attempt * 7) % len(contexts)]
                try:
                    text = self.model.generate_mcq_text(p["subject"], p["topic"], level, ctx)
                except ModelBadResponse:
                    bad_responses += 1
                    if bad_responses >= 3:
                        raise
                    rejected["format"] += 1
                    continue
                run.stage = f"Checking question {i + 1} of {run.total}"
                db.commit()
                c = self.validator.check(text, existing, passage=ctx, grounded=p.get("reference_text") is not None)
                if not c.ok:
                    rejected[c.reason] += 1
                    run.rejected = dict(rejected)
                    continue
                self._store(db, run, c, level, ctx, mv_id)
                existing.insert(0, c.mcq["question"])
                times.append(time.time() - t0)
                run.ready += 1
                run.rejected = dict(rejected)
                db.commit()
                break

    def _store(self, db, run: GenerationRun, c, level: str, ctx: str, mv_id: int):
        p, m = run.params, c.mcq
        q = Question(owner_id=run.requested_by, course_id=p.get("course_id"), topic_id=p.get("topic_id"),
                     objective_id=p.get("objective_id"), topic_key=p["topic_key"], subject_label=p["subject"],
                     unit_label=p.get("unit"), topic_label=p["topic"], text=m["question"],
                     explanation=m["explanation"] or None, difficulty=level,
                     source_type=run.grounded_on or "generated_notes", source_excerpt=ctx, model_version_id=mv_id,
                     generation_run_id=run.id,
                     review_status="personal" if p.get("purpose") == "practice" else "draft",
                     validation={"math_verified": c.math_verified, **c.info})
        for k, (label, txt) in enumerate(zip("ABCD", m["options"])):
            q.options.append(AnswerOption(label=label, text=txt, is_correct=(label == m["answer"]), position=k))
        db.add(q)
        db.flush()
        quiz_id = p.get("quiz_id")
        replace_id = p.get("replace_question_id")
        if quiz_id:
            quiz = db.get(Quiz, quiz_id)
            if replace_id:
                old_item = db.scalar(select(QuizQuestion).where(QuizQuestion.quiz_id == quiz_id,
                                                                QuizQuestion.question_id == replace_id))
                old = db.get(Question, replace_id)
                if old_item is not None:
                    old_item.question_id = q.id               # keeps position and marks
                if old is not None and old.review_status == "draft":
                    old.review_status = "rejected"
                    db.add(QuestionReviewRecord(question_id=old.id, reviewer_id=run.requested_by, action="regenerated",
                                                note=f"Replaced by question {q.id}", before=question_snapshot(old)))
            elif quiz is not None:
                pos = len(quiz.items)
                quiz.items.append(QuizQuestion(question_id=q.id, position=pos, marks=float(p.get("marks_each", 1.0))))
                quiz.max_marks = float(sum(i.marks for i in quiz.items))
