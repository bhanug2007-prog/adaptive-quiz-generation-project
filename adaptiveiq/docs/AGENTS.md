# AI agents

AdaptiveIQ has two agents. Both use a fixed list of tools, log every step to the database
(`agent_runs` and `agent_steps`, migration `0004_agent_logs`), and show that log to the lecturer.
Neither can publish a quiz, approve a question or change marks.

## 1. Question Quality Agent

Code: `backend/app/agents/question_quality.py`, called from `services/generation_service.py`.

It runs every generation request (lecturer drafts, single-question regeneration and student practice).
It replaced the old generation loop without changing what it does: the same 140 earlier tests pass.

| Tool | What it does |
|---|---|
| `prepare_contexts` | Reads the lecturer's reference material, or writes study notes, to generate from |
| `generate_questions` | Qwen writes one question for a slot (first try) |
| `regenerate_question` | Qwen writes it again from a different passage (a retry) |
| `validate_question` | The Python checks: format, give-away, numbers, source overlap, maths |
| `check_duplicate_questions` | The duplicate part of those checks, reported on its own |
| `evaluate_question_quality` | The Grok reviewer, or "not done" with the reason (see `QUALITY_REVIEW.md`) |
| `save_question_draft` | Stores the question as a draft (never approved, never published) |
| `check_difficulty_distribution` | Requested vs judged difficulty mix |
| `get_generation_status` | The run's final state |

Decisions are rules, not an LLM's choice, so the agent is predictable:

| Decision | When |
|---|---|
| `plan` | Start: the difficulty of each question |
| `accept` | A question passed every check |
| `retry` | A question failed; only that one is generated again, while tries remain (`MAX_ATTEMPTS_PER_QUESTION`, default 3) |
| `give_up` | No tries left for that question |
| `keep_as_failed` | Lecturer drafts only: the best failed attempt is kept, marked "Failed checks" |
| `drop` | Practice and regeneration: nothing that failed is saved |
| `stop` | Cancelled, or three unusable model replies in a row |
| `report_mix` | The judged difficulty mix differs from the request, or could not be checked |
| `await_lecturer_approval` | The end of every lecturer run |

Where to see it: after a run on **Create Quiz** ("What the generation agent did"), and on a quiz's
**Preview & publish** tab ("How these questions were generated"). API: `GET /api/lecturer/generation/{run_id}/agent`.
Runs from before this change have no log.

## 2. Lecturer Insights Agent ("Ask about your class")

Code: `backend/app/agents/insights.py` and `insight_tools.py`. Screen: **Class analytics → Ask about your class**.
API: `POST /api/lecturer/insights/ask` `{course_id, quiz_id?, question}`.

Read-only tools, all limited to one course the lecturer owns (checked before anything runs):

| Tool | Returns |
|---|---|
| `get_class_analytics` | Average, median, distribution, completion, skipping, accuracy by difficulty (course or one quiz) |
| `get_topic_mastery` | Per topic: answers, accuracy, skipping, students at each mastery level; `enough_evidence` needs 10 answers |
| `get_question_statistics` | Per question: answers, % correct, % skipped, discrimination, review flags |
| `get_student_performance` | Per student, anonymised: average, submissions, who needs support and why |
| `get_assessment_results` | Each assessment's submissions, average and median |
| `create_lecturer_report` | All of the above |

How one question is answered:

1. **Plan.** With Grok: Grok picks up to 3 tools. Its plan is checked: unknown tools, extra arguments and
   quizzes outside the course are refused and logged (`refuse_tool`, `refuse_args`, `limit_tools`).
   Without Grok, or if its plan cannot be read, keywords in the question pick the tools (`route_by_keywords`).
   If Grok says the question is not about the course, no tool runs.
2. **Tools** run on the database.
3. **Answer.** With Grok: Grok words an answer from the tool results only. Every number in it must appear in
   those results (rounding allowed); an answer with any other number, an unknown "Student N", or a claim of
   cheating is thrown away (`reject_answer`) and the template answer is shown instead. Without Grok the
   answer is built from templates. Either way, missing evidence is listed under "Limits of this answer".
4. **Names.** Grok only ever sees "Student 1", "Student 2"... Names and email addresses in the lecturer's
   question are replaced before it is sent. Real names are put back only in the answer on the lecturer's screen.

The screen says whether the answer was worded by the AI or by fixed rules, why the AI was not used,
which tools ran, and can show every step.

Settings (`backend/.env`): `INSIGHTS_AI=true` (set `false` to never call Grok for this),
`INSIGHTS_PER_10_MIN=20` (questions per lecturer per 10 minutes). It uses the same `GROK_*` settings and the
same pause after a rate-limit, quota or key error as the question reviewer.

## 3. What is tested (backend `tests/test_agents.py`, frontend `components/lecturer/__tests__/agents.test.jsx`)

- The generation log has every tool and decision, never more than 3 tries per question, no publish step,
  and the quiz stays a draft with nothing approved. Only the owner can read it.
- Without Grok: keyword routing and template answers that match the class analytics numbers; real names shown.
- With the stand-in Grok: plan and answer accepted; no name, email or "Student One" in what is sent to Grok;
  invented numbers, unknown students and cheating claims rejected; refused tools; at most 3 tools;
  unreadable plan falls back; a quota error pauses Grok so the next question makes no call; off-topic questions;
  `INSIGHTS_AI=false`.
- Other lecturers and students get 404 / 403; a quiz from another course is refused; rate limit 429;
  the quiz and class analytics are identical before and after asking (read-only).

## 4. Limits

- Not yet run against the real xAI API; Grok's replies in tests are scripted.
- The number check proves numbers come from the data, not that the sentence around them is right.
  The lecturer should read the findings with the numbers shown.
- Keyword routing is simple; an unusual question may get a general class overview.
- Questions and answers are kept in `agent_runs` (visible to that lecturer only); there is no delete button yet.
