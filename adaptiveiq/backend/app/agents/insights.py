"""Lecturer Insights Agent: answers a lecturer's question about one of their courses from real data.

How it works, every step logged in agent_runs / agent_steps:
    1. plan     Grok picks up to MAX_TOOLS read-only tools from insight_tools.TOOLS for the question.
                Without Grok (no key, INSIGHTS_AI=false, paused, or a bad reply) a keyword router picks them.
                Grok's choice is checked: unknown tools, unknown arguments and quizzes outside the course
                are refused and logged.
    2. tools    The chosen tools run on the database (scoped to the lecturer's own course).
    3. answer   Grok words the answer from the tool results only. Every number in its answer must appear in
                those results, or the answer is thrown away and a template answer is used instead.
                Without Grok the answer is built from templates.
    4. names    Grok only ever sees "Student 1", "Student 2"...; real names are put back for the lecturer.

The agent is read-only: it cannot change marks, questions, quizzes or anything else. It never labels a
student as cheating and it says when there is not enough evidence.
"""
import json
import re
import time

from sqlalchemy.orm import Session

from app.agents.insight_tools import MIN_TOPIC_ANSWERS, TOOLS, InsightTools
from app.agents.recorder import Recorder
from app.core.config import Settings
from app.models import Course, User
from app.services.quality_service import AIReviewError, QualityEvaluator, extract_json_object, scrub_secrets

AGENT = "lecturer_insights"
MAX_TOOLS = 3
MAX_DATA_CHARS = 14000          # tool results sent to the LLM are cut to this size
QUESTION_MAX = 500

PLAN_SYSTEM = """You plan which read-only analytics tools to run to answer a university lecturer's question
about their own course. Reply with JSON only, no other text:
{"tools": [{"name": "<tool name>", "args": {}}], "reason": "<one sentence>"}
Rules: use at most 3 tools; only the tools listed; only the arguments each tool lists; a quiz_id must be one
of the listed quizzes. If the question is not about this course's teaching data, reply {"tools": [], "reason": "..."}."""

ANSWER_SYSTEM = """You help a university lecturer understand their class. Answer the question using ONLY the
data given (JSON from analytics tools). Reply with JSON only, no other text:
{"answer": "<2-4 sentences>", "findings": ["..."], "suggestions": ["..."], "caveats": ["..."]}
Rules:
- Every number you write must appear in the data. Do not compute new numbers, estimate or guess.
- If submissions is 0, count is 0, lists are empty, or averages/metrics are null, state plainly that no submitted data exists yet rather than writing 0% or estimating.
- Students appear as "Student 1", "Student 2"...; refer to them only by these labels.
- If the data is too small (e.g. enough_evidence or enough_data is false, or few submissions) say so in caveats.
- Suggestions are teaching actions for the lecturer (revisit a topic, review a question, check in with a student).
- Never say or suggest that a student cheated. Never invent topics, quizzes or students.
- At most 5 findings, 3 suggestions and 3 caveats, each one short sentence."""

KEYWORDS = [
    ("create_lecturer_report", r"\breport\b|\bsummar|\boverview\b|everything"),
    ("get_student_performance", r"\bstudents?\b|\bwho\b|struggl|support|\bhelp\b|at risk|behind|individual|\bnames?\b"),
    ("get_topic_mastery", r"\btopics?\b|mastery|concept|\bunits?\b|\bweak|strong|understand|syllabus"),
    ("get_question_statistics", r"\bquestions?\b|\bitems?\b|missed|\bflag|discriminat|confus|wrong answer|skipp"),
    ("get_assessment_results", r"\bquiz(zes)?\b|assessment|\bexams?\b|\btests?\b|results?|marks|\bscores?\b"),
    ("get_class_analytics", r"average|median|\bclass\b|overall|completion|distribution|difficult|easy|hard"),
]

NUM = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")
THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}\b)")
ALIAS = re.compile(r"\bStudent (\d+)\b")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_SKIP_NAME_PARTS = frozenset({
    "student", "students", "test", "user", "admin", "lecturer", "one", "two", "three", "four", "five",
    "class", "course", "quiz", "quizzes", "topic", "topics", "unit", "subject", "help", "support",
})


def _parse_json(text: str) -> dict:
    return extract_json_object(text)


def _numbers(text: str) -> list[float]:
    normalized = THOUSANDS.sub("", ALIAS.sub("", text))
    return [float(x) for x in NUM.findall(normalized)]


def ungrounded_numbers(texts: list[str], sources: list[str]) -> list[str]:
    """Numbers in the answer that do not appear (allowing rounding) anywhere in the data or the question."""
    have = set()
    for s in sources:
        have.update(_numbers(s))
    bad = []
    for t in texts:
        for n in _numbers(t):
            if n == 0 or any(abs(a - n) <= 0.051 or round(a) == n for a in have):
                continue
            bad.append(f"{n:g}")
    return bad


_SCORE_PCT_KEYS = frozenset({"average_pct", "median_pct", "accuracy_pct", "correct_pct", "skipped_pct"})


def _pct_presence(node, stats=None) -> dict[str, bool]:
    if stats is None:
        stats = {"score": False, "completion": False}
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _SCORE_PCT_KEYS and isinstance(v, (int, float)):
                stats["score"] = True
            elif k == "completion_pct" and isinstance(v, (int, float)):
                stats["completion"] = True
            elif isinstance(v, (dict, list)):
                _pct_presence(v, stats)
    elif isinstance(node, list):
        for item in node:
            _pct_presence(item, stats)
    return stats


def _ungrounded_zero_pct(texts: list[str], results: dict) -> bool:
    """True if the AI wrote 0% for scores/accuracy when no submitted percentage metrics exist yet."""
    stats = _pct_presence(results)
    if stats["score"]:
        return False
    combined = " ".join(texts)
    for m in re.finditer(r"(?<!\d)0+(?:\.0+)?\s*%", combined):
        window = combined[max(0, m.start() - 30):min(len(combined), m.end() + 30)].lower()
        if stats["completion"] and "complet" in window:
            continue
        return True
    return False


def _summary(res: dict) -> dict:
    """What the step log keeps of a tool result: sizes, not the whole table."""
    out = {}
    for k, v in res.items():
        if isinstance(v, list):
            out[k] = f"{len(v)} rows"
        elif isinstance(v, dict):
            out[k] = "section"
        else:
            out[k] = v
    return out


class LecturerInsightsAgent:
    def __init__(self, db: Session, user: User, course: Course, s: Settings, llm: QualityEvaluator | None):
        self.db, self.user, self.course, self.s, self.llm = db, user, course, s, llm
        self.tools = InsightTools(db, course, s)

    # ---------- privacy ----------

    def _private(self, text: str, safe_words: set[str] | None = None) -> str:
        """Removes student names and emails from text before it goes to an external LLM or audit log."""
        safe = _SKIP_NAME_PARTS | (safe_words or set())
        for alias, name in sorted(self.tools.names.items(), key=lambda kv: -len(kv[1])):
            if name and len(name) >= 3:
                text = re.sub(rf"\b{re.escape(name)}\b" if name.replace(" ", "").isalnum() else re.escape(name),
                              alias, text, flags=re.I)
        # Also mask individual name parts (first/last name alone) while avoiding course/topic words
        token_aliases: dict[str, set[str]] = {}
        for alias, name in self.tools.names.items():
            for part in re.findall(r"[A-Za-z]{3,}", name or ""):
                low = part.lower()
                if low not in safe:
                    token_aliases.setdefault(low, set()).add(alias)
        for token, aliases in sorted(token_aliases.items(), key=lambda kv: -len(kv[0])):
            rep = next(iter(aliases)) if len(aliases) == 1 else "[student]"
            text = re.sub(rf"\b{re.escape(token)}\b", rep, text, flags=re.I)
        for st in self.tools.students:
            if st.email:
                text = text.replace(st.email, "[email]")
        return scrub_secrets(EMAIL.sub("[email]", text), (self.s.grok_api_key,))

    def _names_back(self, v):
        if isinstance(v, str):
            return ALIAS.sub(lambda m: self.tools.names.get(m.group(0), m.group(0)), v)
        if isinstance(v, list):
            return [self._names_back(x) for x in v]
        return v

    # ---------- planning ----------

    def _ai_off_reason(self) -> str | None:
        if not self.s.insights_ai:
            return "AI wording is turned off (INSIGHTS_AI=false)."
        if self.llm is None:
            return "No AI model is set up (GROK_API_KEY is empty)."
        return self.llm.llm_unavailable()

    def _route(self, question: str, quiz_id: int | None) -> list[dict]:
        q = question.lower()
        names = [name for name, rx in KEYWORDS if re.search(rx, q)]
        if "create_lecturer_report" in names:
            names = ["create_lecturer_report"]
        if not names:
            names = ["get_class_analytics", "get_topic_mastery"]
        calls = []
        for n in names[:MAX_TOOLS]:
            args = {"quiz_id": quiz_id} if quiz_id and "quiz_id" in TOOLS[n]["args"] else {}
            calls.append({"name": n, "args": args})
        return calls

    def _check_plan(self, rec: Recorder, plan: dict) -> list[dict]:
        calls, seen = [], set()
        raw = plan.get("tools")
        if not isinstance(raw, list):
            raise ValueError("'tools' is not a list")
        for c in raw:
            name = c.get("name") if isinstance(c, dict) else None
            args = c.get("args") if isinstance(c, dict) and isinstance(c.get("args"), dict) else {}
            if name not in TOOLS:
                rec.decide("refuse_tool", "The AI asked for a tool that does not exist, so it is not run.",
                           tool=str(name)[:60])
                continue
            extra = sorted(set(args) - set(TOOLS[name]["args"]))
            if extra:
                rec.decide("refuse_args", "Arguments the tool does not take were removed.", tool=name, removed=extra)
                args = {k: v for k, v in args.items() if k in TOOLS[name]["args"]}
            if isinstance(args.get("quiz_id"), bool) or args.get("quiz_id") not in (None, "", 0):
                try:
                    self.tools.check_quiz(args["quiz_id"])
                except ValueError:
                    rec.decide("refuse_tool", "The AI named a quiz that is not in this course, so the call is "
                               "not run.", tool=name, quiz_id=str(args["quiz_id"])[:20])
                    continue
            key = (name, json.dumps(args, sort_keys=True, default=str))
            if key in seen:
                continue
            seen.add(key)
            calls.append({"name": name, "args": args})
        if len(calls) > MAX_TOOLS:
            rec.decide("limit_tools", f"Only the first {MAX_TOOLS} tool calls are run.", dropped=len(calls) - MAX_TOOLS)
            calls = calls[:MAX_TOOLS]
        return calls

    def _llm(self, rec: Recorder, name: str, messages: list[dict], max_tokens: int) -> dict | None:
        t0 = time.perf_counter()
        try:
            text = self.llm.llm_chat(messages, max_tokens)
            out = _parse_json(text)
        except AIReviewError as e:
            clean = scrub_secrets(str(e), (self.s.grok_api_key,))
            rec.llm(name, {"model": self.s.grok_model}, {"error": clean, "kind": e.kind}, False, int((time.perf_counter() - t0) * 1000))
            self._ai_note = clean
            return None
        except (ValueError, TypeError) as e:
            clean = scrub_secrets(f"Unusable reply: {e}", (self.s.grok_api_key,))[:300]
            rec.llm(name, {"model": self.s.grok_model}, {"error": clean}, False,
                    int((time.perf_counter() - t0) * 1000))
            self._ai_note = "The AI sent a reply that could not be read."
            return None
        rec.llm(name, {"model": self.s.grok_model}, {k: out.get(k) for k in ("tools", "reason", "answer")
                                                     if k in out}, True, int((time.perf_counter() - t0) * 1000))
        return out

    # ---------- the run ----------

    def ask(self, question: str, quiz_id: int | None = None) -> dict:
        question = (question or "").strip()[:QUESTION_MAX]
        self.tools.check_quiz(quiz_id)                  # raises ValueError for a quiz outside the course
        ctx = self.tools.context()
        if quiz_id:
            ctx["selected_quiz_id"] = quiz_id
        safe_words = {
            w.lower()
            for part in [ctx.get("course", ""), *(ctx.get("topics") or []),
                         *(z.get("title", "") for z in ctx.get("quizzes") or [])]
            for w in re.findall(r"[A-Za-z]{3,}", str(part))
        }
        private_q = self._private(question, safe_words)
        rec = Recorder.start(self.db, AGENT, self.user.id, course_id=self.course.id,
                             input={"question": private_q, "quiz_id": quiz_id})
        self._ai_note = None
        off = self._ai_off_reason()
        use_ai = off is None
        if not use_ai:
            self._ai_note = off

        # 1. plan
        calls = None
        if use_ai:
            plan = self._llm(rec, "plan_tools", [
                {"role": "system", "content": PLAN_SYSTEM},
                {"role": "user", "content": "Tools:\n" + json.dumps({k: {"description": v["description"],
                                                                          "args": v["args"]} for k, v in TOOLS.items()})
                 + "\n\nCourse:\n" + json.dumps(ctx, default=str) + f"\n\nQuestion: {private_q}"}], 300)
            if plan is not None:
                try:
                    calls = self._check_plan(rec, plan)
                except (ValueError, AttributeError) as e:
                    self._ai_note = f"The AI's plan could not be used ({e})."
                    calls = None
                if calls == [] and plan.get("tools") == []:
                    rec.decide("out_of_scope", str(plan.get("reason") or "The question is not about this course's data.")[:300])
                    result = {"answer": "I can only answer questions about this course's quizzes, topics, questions "
                                        "and students, from the data recorded here.",
                              "findings": [], "suggestions": [], "caveats": []}
                    return self._done(rec, question, result, [], "ai")
                if calls == []:
                    calls = None
        if calls is None:
            calls = self._route(question, quiz_id)
            rec.decide("route_by_keywords", "Tools picked by keywords in the question" +
                       (f" because {self._ai_note[0].lower() + self._ai_note[1:]}" if self._ai_note else "."),
                       tools=[c["name"] for c in calls])
            use_ai = use_ai and self.llm.llm_unavailable() is None and self.s.insights_ai
        else:
            rec.decide("use_ai_plan", str(plan.get("reason") or "Tools chosen by the AI.")[:300],
                       tools=[c["name"] for c in calls])

        # 2. tools
        results, used = {}, []
        for c in calls:
            try:
                res = rec.tool(c["name"], c["args"], lambda c=c: self.tools.call(c["name"], c["args"]), _summary)
            except ValueError as e:
                used.append({"name": c["name"], "args": c["args"], "ok": False, "error": str(e)})
                continue
            key = c["name"] + (f"(quiz {c['args']['quiz_id']})" if c["args"].get("quiz_id") else "")
            results[key] = res
            used.append({"name": c["name"], "args": c["args"], "ok": True})
        data = json.dumps(results, default=str)

        # 3. answer
        rules = self._rules_answer(results)
        result, mode = None, "rules"
        if use_ai and results:
            out = self._llm(rec, "write_answer", [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": f"Course: {self.course.title}\nQuestion: {private_q}\n\nData:\n"
                                            + data[:MAX_DATA_CHARS]}], 700)
            if out is not None:
                ans = {"answer": out.get("answer"), "findings": out.get("findings") or [],
                       "suggestions": out.get("suggestions") or [], "caveats": out.get("caveats") or []}
                ok_shape = isinstance(ans["answer"], str) and ans["answer"].strip() and all(
                    isinstance(ans[k], list) and all(isinstance(x, str) for x in ans[k])
                    for k in ("findings", "suggestions", "caveats"))
                if not ok_shape:
                    rec.decide("reject_answer", "The AI's answer was not in the expected format; the template "
                               "answer is used.")
                    self._ai_note = "The AI's answer was not in the expected format."
                else:
                    ans = {k: (v.strip() if isinstance(v, str) else [x.strip() for x in v[:5]]) for k, v in ans.items()}
                    texts = [ans["answer"], *ans["findings"], *ans["suggestions"], *ans["caveats"]]
                    bad = ungrounded_numbers(texts, [data, private_q, json.dumps(ctx, default=str)])
                    zero_pct = _ungrounded_zero_pct(texts, results)
                    labels = {f"Student {m}" for t in texts for m in ALIAS.findall(t)}
                    unknown = sorted(labels - set(self.tools.names))
                    if bad or zero_pct or unknown:
                        why = (f"numbers not in the data: {', '.join(bad[:6])}" if bad else
                               "0% metrics without any submitted scores or accuracy data" if zero_pct else
                               f"students not in the course: {', '.join(unknown[:4])}")
                        rec.decide("reject_answer", f"The AI's answer used {why}; the template answer is used.")
                        self._ai_note = "The AI's answer used numbers that are not in the data, so it was not shown."
                    elif re.search(r"\bcheat", " ".join(texts), re.I):
                        rec.decide("reject_answer", "The AI's answer talked about cheating; the template answer is "
                                   "used.")
                        self._ai_note = "The AI's answer was not shown (it went beyond the data)."
                    else:
                        rec.decide("accept_answer", "Every number in the AI's answer appears in the tool results.")
                        result, mode = ans, "ai"
        if result is None:
            result = rules
            if not results:
                rec.decide("no_data", "No tool returned data.")
        return self._done(rec, question, result, used, mode)

    def _done(self, rec, question, result, used, mode) -> dict:
        shown = {k: self._names_back(v) for k, v in result.items()}
        rec.finish("done", output={"mode": mode, "tools": [u["name"] for u in used]})
        return {"agent_run_id": rec.run.id, "question": question, **shown, "mode": mode,
                "ai_note": None if mode == "ai" else self._ai_note, "tools_used": used,
                "model": self.s.grok_model if mode == "ai" else None}

    # ---------- answers without the AI ----------

    def _rules_answer(self, results: dict) -> dict:
        f, sug, cav = [], [], []
        lead = None                                   # what the first (most relevant) tool could say
        for key, r in results.items():
            name = key.split("(")[0]
            if name == "create_lecturer_report":
                for part in ("class", "assessments", "topics", "questions", "students"):
                    a, b, c = self._rules_part(part, r[part])
                    f += a; sug += b; cav += c
                continue
            part = {"get_class_analytics": "class", "get_topic_mastery": "topics",
                    "get_question_statistics": "questions", "get_student_performance": "students",
                    "get_assessment_results": "assessments"}[name]
            a, b, c = self._rules_part(part, r)
            if lead is None and not a and c:
                lead = c[0]                           # the main tool has no finding, only a limit: say that first
            lead = lead or ""
            f += a; sug += b; cav += c
        f, sug, cav = _dedupe(f), _dedupe(sug), _dedupe(cav)
        if lead:
            answer = lead
            cav = [x for x in cav if x != lead]
        elif f:
            answer = f[0]
        elif cav:
            answer = "There is not enough data yet to answer this well."
        else:
            answer = "I could not find data for this question in this course."
        findings = f[:7] if lead else f[1:8]
        return {"answer": answer, "findings": findings, "suggestions": sug[:4], "caveats": cav[:5]}

    def _rules_part(self, part: str, r: dict):
        f, sug, cav = [], [], []
        if part == "class":
            if not r["submissions"]:
                cav.append("No submitted attempts yet, so there are no results to analyse.")
                return f, sug, cav
            scope = "In this quiz" if r["scope"] == "quiz" else "Across the published quizzes"
            f.append(f"{scope}, the average score is {r['average_pct']}% (median {r['median_pct']}%) over "
                     f"{_n(r['submissions'], 'submission')} from a class of {r['students']}.")
            if r["completion_pct"] is not None:
                f.append(f"Completion is {r['completion_pct']}% of the expected submissions.")
            parts = [f"{d['difficulty']} {d['accuracy_pct']}%" for d in r["accuracy_by_difficulty"] if d["answered"]]
            if parts:
                f.append("Accuracy by difficulty: " + ", ".join(parts) + ".")
            if r["submissions"] < 5:
                cav.append(f"Only {_n(r['submissions'], 'submission')} so far; treat these numbers with care.")
        elif part == "topics":
            judged = [t for t in r["topics"] if t["enough_evidence"] and t["accuracy_pct"] is not None]
            thin = [t for t in r["topics"] if not t["enough_evidence"]]
            judged.sort(key=lambda t: t["accuracy_pct"])
            for t in judged[:3]:
                f.append(f"{t['topic']}: {t['accuracy_pct']}% correct over {t['answered']} answers.")
            weak = [t for t in judged if t["accuracy_pct"] < 60]
            if weak:
                sug.append(f"Revisit {weak[0]['topic']} with the class; it has the lowest accuracy "
                           f"({weak[0]['accuracy_pct']}%).")
            if not r["topics"]:
                cav.append("No topics are defined in this course yet.")
            elif thin:
                cav.append(f"{len(thin)} of {len(r['topics'])} topics have fewer than {MIN_TOPIC_ANSWERS} answers, "
                           "so they are not judged (insufficient evidence)." if len(thin) > 1 or len(r['topics']) > 1 else
                           f"The topic has fewer than {MIN_TOPIC_ANSWERS} answers, so it is not judged (insufficient evidence).")
        elif part == "questions":
            qs = [q for q in r["questions"] if q["enough_data"]]
            for q in qs[:3]:
                f.append(f"Question {q['question_no']} of {q['quiz']} (\"{q['text'][:70]}\") was answered correctly "
                         f"by {q['correct_pct']}% of {q['answers']} students.")
            flagged = [q for q in qs if q["flags"]]
            if flagged:
                sug.append(f"Review question {flagged[0]['question_no']} of {flagged[0]['quiz']}: "
                           f"{flagged[0]['flags'][0].rstrip('.')}.")
            if r["questions_with_answers"] and not qs:
                cav.append("No question has 10 or more answers yet, so question statistics are not reliable.")
            if not r["questions_with_answers"]:
                cav.append("No question in this course has been answered yet.")
        elif part == "students":
            need = [x for x in r["students"] if x["needs_support"]]
            scored = [x for x in r["students"] if x["average_pct"] is not None]      # already lowest first
            if r["count"] == 0:
                cav.append("No students are enrolled in this course.")
            elif not scored:
                cav.append(f"{_n(r['count'], 'student')} enrolled, but no quiz submissions have been recorded yet.")
            elif need:
                f.append(f"{len(need)} of {r['count']} students may need support.")
                for x in need[:5]:
                    f.append(f"{x['student']}: {x['support_reason']}")
                sug.append(f"Check in with {need[0]['student']} first.")
            else:
                f.append(f"None of the {r['count']} students is currently flagged as needing support.")
            if scored:
                f.append("Lowest averages: " + ", ".join(f"{x['student']} {x['average_pct']}% "
                                                         f"({x['submissions']} quiz{'zes' if x['submissions'] != 1 else ''})"
                                                         for x in scored[:3]) + ".")
                if all(x["submissions"] < 2 for x in scored):
                    cav.append("Each student has at most one submitted quiz, so these averages rest on little evidence.")
        elif part == "assessments":
            with_subs = [a for a in r["assessments"] if a["submissions"]]
            for a in with_subs:
                f.append(f"{a['quiz']}: average {a['average_pct']}% (median {a['median_pct']}%) over "
                         f"{_n(a['submissions'], 'submission')}.")
            if not r["assessments"]:
                cav.append("This course has no published assessments yet.")
            elif not with_subs:
                cav.append("Assessments exist, but no student submissions have been recorded yet.")
        return f, sug, cav


def _n(k: int, word: str) -> str:
    return f"{k} {word}{'' if k == 1 else 's'}"


def _dedupe(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
