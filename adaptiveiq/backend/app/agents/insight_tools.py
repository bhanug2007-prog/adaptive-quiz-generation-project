"""Read-only analytics tools for the Lecturer Insights Agent.

Every tool works on one course the lecturer owns (checked before the agent starts) and returns numbers
computed here from the database by the existing analytics code (services/class_analytics.py). Tools
cannot write, cannot see other lecturers' courses, and take only the arguments listed in TOOLS.

Students are never named in tool output: they appear as "Student 1", "Student 2"... The mapping stays in
this process and real names are put back only in the answer shown to the lecturer.
"""
import statistics
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Course, Question, Quiz
from app.services import class_analytics as ca

MIN_TOPIC_ANSWERS = 10          # below this a topic's accuracy is reported as "not enough evidence"
TEXT_MAX = 160

TOOLS = {
    "get_class_analytics": {
        "description": "Class average, median, score distribution, completion, skipping and accuracy by difficulty "
                       "for the course, or for one quiz when quiz_id is given.",
        "args": {"quiz_id": "optional, a quiz id from this course"},
    },
    "get_topic_mastery": {
        "description": "Per topic: answers, accuracy, skipping, and how many students are at each mastery level "
                       "(including insufficient evidence).",
        "args": {},
    },
    "get_question_statistics": {
        "description": "Per question: answers, % correct, % skipped, discrimination and review flags. Only quizzes "
                       "students have taken have data.",
        "args": {"quiz_id": "optional, a quiz id from this course"},
    },
    "get_student_performance": {
        "description": "Per student (anonymised as Student 1, 2, ...): average, submissions, topics needing "
                       "improvement, and who needs support and why.",
        "args": {},
    },
    "get_assessment_results": {
        "description": "Results of each assessment (or one quiz): submissions, average and median.",
        "args": {"quiz_id": "optional, a quiz id from this course"},
    },
    "create_lecturer_report": {
        "description": "A short course report built from all the tools above.",
        "args": {},
    },
}


def _pct(x):
    return None if x is None else round(x * 100, 1)


class InsightTools:
    def __init__(self, db: Session, course: Course, s: Settings):
        self.db, self.course, self.s = db, course, s
        self.quizzes = ca.course_quizzes(db, course.id)
        self.quiz_ids = {z.id for z in self.quizzes}
        self._perf = {}
        self.names: dict[str, str] = {}             # "Student 1" -> real name (never leaves the backend)
        self._alias: dict[int, str] = {}
        self.students = ca.course_students(db, course.id)
        for st in self.students:                    # fixed labels for the whole question, in name order
            self.alias(st.id, st.full_name)

    # ---------- helpers ----------

    def alias(self, student_id: int, name: str) -> str:
        if student_id not in self._alias:
            a = f"Student {len(self._alias) + 1}"
            self._alias[student_id] = a
            self.names[a] = name
        return self._alias[student_id]

    def perf(self, quiz_id: int | None = None) -> dict:
        if quiz_id not in self._perf:
            self._perf[quiz_id] = ca.class_performance(self.db, self.course, ca.Filters(quiz_id=quiz_id), self.s)
        return self._perf[quiz_id]

    def check_quiz(self, quiz_id) -> int | None:
        if isinstance(quiz_id, bool):
            raise ValueError("quiz_id must be a number")
        if quiz_id in (None, "", 0):
            return None
        try:
            qid = int(quiz_id)
        except (TypeError, ValueError):
            raise ValueError("quiz_id must be a number") from None
        if qid not in self.quiz_ids:
            raise ValueError("That quiz is not in this course.")
        return qid

    def context(self) -> dict:
        """What the planner may know: names of quizzes and topics, no results and no students."""
        topics = ca.course_topics(self.db, self.course.id)
        return {"course": self.course.title, "quizzes": [{"quiz_id": z.id, "title": z.title, "status": z.status}
                                                         for z in self.quizzes],
                "topics": [t.name for t, _, _ in topics]}

    # ---------- tools ----------

    def get_class_analytics(self, quiz_id=None) -> dict:
        qid = self.check_quiz(quiz_id)
        p = self.perf(qid)
        return {"scope": "quiz" if qid else "course", "quiz_id": qid, "students": p["students"],
                "quizzes": p["quizzes"], "submissions": p["submissions"], "average_pct": p["average"],
                "median_pct": p["median"], "completion_pct": _pct(p["completion_rate"]),
                "skipped_pct": _pct(p["skipped_rate"]),
                "score_distribution": [d for d in p["distribution"] if d["count"]],
                "accuracy_by_difficulty": [{"difficulty": d["difficulty"], "answered": d["answered"],
                                            "accuracy_pct": _pct(d["accuracy"])} for d in p["by_difficulty"]],
                "note": p["note"]}

    def get_topic_mastery(self) -> dict:
        p = self.perf(None)
        acc = defaultdict(lambda: {"correct": 0, "answered": 0, "skipped": 0})
        for x in ca.best_sessions(self.db, list(self.quiz_ids)):
            for a in x.answers:
                q = self.db.get(Question, a.question_id)
                if q is None or q.topic_id is None:
                    continue
                t = acc[q.topic_id]
                if a.selected_option_id is None:
                    t["skipped"] += 1
                else:
                    t["answered"] += 1
                    t["correct"] += bool(a.is_correct)
        rows = []
        for d in p["mastery_distribution"]:
            t = acc.get(d["topic_id"], {"correct": 0, "answered": 0, "skipped": 0})
            n = t["answered"]
            seen = n + t["skipped"]
            rows.append({"topic": d["topic"], "unit": d["unit"], "answered": n,
                         "accuracy_pct": round(t["correct"] / n * 100, 1) if n else None,
                         "skipped_pct": round(t["skipped"] / seen * 100, 1) if seen else None,
                         "enough_evidence": n >= MIN_TOPIC_ANSWERS,
                         "students_by_mastery": d["counts"]})
        return {"topics": rows, "min_answers_for_evidence": MIN_TOPIC_ANSWERS,
                "mastery_levels": "needs_improvement < developing < proficient < strong; insufficient_evidence "
                                  "means too few answers to judge; not_attempted means no answers"}

    def get_question_statistics(self, quiz_id=None) -> dict:
        qid = self.check_quiz(quiz_id)
        quizzes = [z for z in self.quizzes if z.id == qid] if qid else self.quizzes
        rows = ca.question_analytics(self.db, quizzes)
        out = []
        for r in rows:
            if not r["answers"]:
                continue
            out.append({"quiz": r["quiz_title"], "question_no": r["position"], "question_id": r["question_id"],
                        "text": r["text"][:TEXT_MAX], "topic": r["topic"], "difficulty": r["difficulty"],
                        "answers": r["answers"], "correct_pct": _pct(r["pct_correct"]),
                        "skipped_pct": _pct(r["pct_skipped"]),
                        "discrimination": None if r["discrimination"] is None else round(r["discrimination"], 2),
                        "enough_data": r["enough_data"], "flags": [f["text"] for f in r["flags"]]})
        out.sort(key=lambda r: (r["correct_pct"] if r["correct_pct"] is not None else 101))
        return {"questions": out[:25], "questions_with_answers": len(out),
                "note": "Flags and discrimination need at least 10 answers (enough_data)."}

    def get_student_performance(self) -> dict:
        p = self.perf(None)
        support = {s["student_id"]: s for s in p["needs_support"]}
        rows = []
        sessions = ca.best_sessions(self.db, list(self.quiz_ids))
        by_student = defaultdict(list)
        for x in sessions:
            if x.result:
                by_student[x.student_id].append(x.result.final_percentage)
        for st in self.students:
            a = self.alias(st.id, st.full_name)
            sc = by_student.get(st.id, [])
            sp = support.get(st.id)
            rows.append({"student": a, "submissions": len(sc),
                         "average_pct": round(statistics.mean(sc), 1) if sc else None,
                         "needs_support": bool(sp), "support_reason": sp["reason"] if sp else None,
                         "support_kind": sp["kind"] if sp else None,
                         "weak_topics": sp["weak_topics"] if sp else []})
        rows.sort(key=lambda r: (r["average_pct"] if r["average_pct"] is not None else -1))
        return {"students": rows, "count": len(rows)}

    def get_assessment_results(self, quiz_id=None) -> dict:
        qid = self.check_quiz(quiz_id)
        p = self.perf(qid)
        res = [t for t in p["trend"] if (qid is None or t["quiz_id"] == qid)]
        out = []
        for t in res:
            z = next(z for z in self.quizzes if z.id == t["quiz_id"])
            pq = self.perf(z.id)
            out.append({"quiz_id": z.id, "quiz": z.title, "status": z.status, "submissions": t["submissions"],
                        "average_pct": t["average"], "median_pct": pq["median"]})
        return {"assessments": out}

    def create_lecturer_report(self) -> dict:
        return {"class": self.get_class_analytics(), "topics": self.get_topic_mastery(),
                "questions": self.get_question_statistics(), "students": self.get_student_performance(),
                "assessments": self.get_assessment_results()}

    def call(self, name: str, args: dict) -> dict:
        if name not in TOOLS:
            raise ValueError(f"Unknown tool {name}")
        allowed = set(TOOLS[name]["args"])
        clean = {k: v for k, v in (args or {}).items() if k in allowed and v not in (None, "")}
        return getattr(self, name)(**clean)


def quiz_title(db: Session, quiz_id: int | None) -> str | None:
    z = db.get(Quiz, quiz_id) if quiz_id else None
    return z.title if z else None
