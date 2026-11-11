"""Question Quality Agent: runs one generation request from the requirements to a lecturer-review draft.

Tools it may call (and nothing else):
    generate_questions        Qwen writes one question for a slot (first try)
    regenerate_question       Qwen writes it again from a different context (a retry)
    validate_question         the Python checks: format, give-away, numbers, source overlap, maths
    check_duplicate_questions the duplicate part of those checks, reported on its own
    evaluate_question_quality the AI reviewer (Grok), or "not done" with the reason
    save_question_draft       stores the question as a draft in the quiz (never approved, never published)
    check_difficulty_distribution  requested vs judged difficulty mix over the stored set
    get_generation_status     the run's state, logged as the last step

Decisions, all bounded and logged with a reason:
    accept          a question that passed every check is saved
    retry           a failed question is regenerated, only that one, while tries remain
                    (MAX_ATTEMPTS_PER_QUESTION, default 3)
    keep_as_failed  lecturer drafts: after the last try the best attempt is saved marked "Failed checks"
    drop            practice and single regenerations: nothing that failed is saved
    stop            three unusable model replies in a row end the run (the model is not working)
    await_lecturer_approval  the end of every lecturer run; publishing stays the lecturer's action

The decisions are rules, not an LLM's choice: the agent is predictable and every step can be audited.
"""
import time
from collections import Counter

from app.agents.recorder import Recorder
from app.models import GenerationRun
from app.services.model_service import ModelBadResponse
from app.services.validation_service import REASONS

AGENT = "question_quality"


def _validate_summary(c) -> dict:
    out = {"passed": c.ok, "reason": c.reason, "reason_text": REASONS.get(c.reason) if c.reason else None,
           "_ok": c.ok}
    for k in ("math_status", "grounding"):
        if k in (c.info or {}):
            out[k] = c.info[k]
    return out


def _quality_summary(r) -> dict:
    return {"evaluator": r.evaluator, "passed": r.passed, "reason": r.reason,
            "reason_text": REASONS.get(r.reason) if r.reason else None, "score": r.score,
            "judged_difficulty": r.assessed_difficulty, "ai_not_done_because": r.ai_error, "_ok": r.passed}


def _source_label(meta: dict | None) -> str | None:
    if not meta:
        return None
    parts = []
    if meta.get("section"):
        parts.append(f"Section: {meta['section']}")
    if meta.get("page") is not None:
        p_end = meta.get("page_end")
        parts.append(f"Pages {meta['page']}-{p_end}" if p_end and p_end != meta["page"] else f"Page {meta['page']}")
    return " · ".join(parts) if parts else None


class QuestionQualityAgent:
    def __init__(self, gs, db, run: GenerationRun, flag, rejected: Counter, times: list[float]):
        self.gs, self.db, self.run, self.flag, self.rejected, self.times = gs, db, run, flag, rejected, times
        p = run.params or {}
        self.rec = Recorder.start(db, AGENT, run.requested_by, generation_run_id=run.id, course_id=p.get("course_id"),
                                  input={"purpose": p.get("purpose"), "source_mode": p.get("source_mode", "topic"),
                                         "document_name": p.get("document_name"),
                                         "subject": p.get("subject"),
                                         "topic": p.get("topic"), "questions": run.total,
                                         "difficulty": p.get("difficulty"), "distribution": p.get("distribution"),
                                         "objectives": p.get("objectives") or [],
                                         "reference_material": bool(p.get("reference_text")),
                                         "max_tries_per_question": gs.s.max_attempts_per_question})

    def run_slots(self, contexts: list[str | dict]):
        gs, db, run, flag, rejected, rec = self.gs, self.db, self.run, self.flag, self.rejected, self.rec
        p = run.params
        if not contexts:
            return
        from app.services.generation_service import difficulty_plan, model_version_id
        plan = difficulty_plan(p.get("difficulty", "mixed"), run.total, p.get("distribution"))
        rec.decide("plan", f"{len(plan)} questions in this order of difficulty", plan=plan)
        existing = gs._existing_texts(db, run)
        mv_id = model_version_id(db, gs.s)
        run.model_version_id = mv_id                   # so reliability can be reported per model version
        purpose = p.get("purpose")
        use_ai = gs.quality.enabled_for(purpose)
        keep_failed = purpose == "lecturer_draft"
        tries = gs.s.max_attempts_per_question
        bad_responses = 0
        is_doc = p.get("source_mode") == "document"
        is_grounded = is_doc or (p.get("reference_text") is not None)
        for i, level in enumerate(plan):
            t0 = time.time()
            best = None                                # (rank, Checked, context_item, QualityResult | None, reason, log row)
            stored = False
            slot = i + 1
            for attempt in range(tries):
                if flag.is_set():
                    rec.decide("stop", "The lecturer cancelled the run.", slot=slot)
                    return
                run.stage = f"Generating question {slot} of {run.total}" + (f" (retry {attempt})" if attempt else "")
                run.attempts += 1
                db.commit()
                ctx_item = contexts[(i + attempt * 7) % len(contexts)]
                ctx_text = ctx_item["text"] if isinstance(ctx_item, dict) else ctx_item
                ctx_meta = {k: v for k, v in ctx_item.items() if k != "text"} if isinstance(ctx_item, dict) else None
                tool = "regenerate_question" if attempt else "generate_questions"
                try:
                    text = rec.tool(tool, {"slot": slot, "difficulty": level, "try": attempt + 1},
                                    lambda: gs.model.generate_mcq_text(
                                        p["subject"], p["topic"], level, ctx_text,
                                        strict_source=is_doc, source_label=_source_label(ctx_meta)),
                                    lambda t: {"characters": len(t or "")})
                except ModelBadResponse:
                    bad_responses += 1
                    if bad_responses >= 3:
                        rec.decide("stop", "Three unusable replies from the model: it is not working, so the run stops.",
                                   slot=slot)
                        raise
                    rejected["format"] += 1
                    rec.decide("retry" if attempt + 1 < tries else "give_up", "The model's reply was unusable.", slot=slot)
                    continue
                run.stage = f"Checking question {slot} of {run.total}"
                db.commit()
                c = rec.tool("validate_question", {"slot": slot, "try": attempt + 1},
                             lambda: gs.validator.check(
                                 text, existing, passage=ctx_text,
                                 grounded=is_grounded, strict_grounding=is_doc, source_meta=ctx_meta),
                             _validate_summary)
                if c.ok and not keep_failed and (c.info or {}).get("math_status") == "unchecked":
                    c.ok = False
                    c.reason = "math_unchecked"
                if c.mcq is not None:
                    sim = (c.info or {}).get("similarity", (c.info or {}).get("max_similarity"))
                    rec.tool("check_duplicate_questions", {"slot": slot, "compared_with": len(existing)},
                             lambda: c.reason != "duplicate",
                             lambda ok: {"duplicate": not ok, "highest_similarity": sim, "_ok": ok})
                if not c.ok:
                    rejected[c.reason] += 1
                    run.rejected = dict(rejected)
                    row = gs._log(db, run, i, attempt, level, c, None, c.reason, raw=text)
                    if keep_failed and c.mcq is not None and (best is None or best[0] == 0):
                        best = (0, c, ctx_item, None, c.reason, row)
                    self._after_fail(slot, attempt, tries, c.reason)
                    db.commit()
                    continue
                q_res = None
                if use_ai:
                    run.stage = f"AI review of question {slot} of {run.total}"
                    db.commit()
                    q_res = rec.tool("evaluate_question_quality", {"slot": slot, "requested_difficulty": level},
                                     lambda: gs.quality.evaluate(
                                         c.mcq, p["subject"], p["topic"], level, ctx_text, c.info, strict_source=is_doc),
                                     _quality_summary)
                    if q_res.ai_called:                         # shown as "N AI calls" in the agent log
                        rec.run.llm_calls = (rec.run.llm_calls or 0) + 1
                    if not q_res.passed:
                        rejected[q_res.reason] += 1
                        run.rejected = dict(rejected)
                        row = gs._log(db, run, i, attempt, level, c, q_res, q_res.reason)
                        if keep_failed:
                            best = (1, c, ctx_item, q_res, q_res.reason, row)     # passed the Python checks: preferred
                        self._after_fail(slot, attempt, tries, q_res.reason)
                        db.commit()
                        continue
                rec.decide("accept", "It passed the Python checks" + (
                    " and the AI review." if q_res and q_res.evaluator == "grok" else
                    "; the AI review was not done." if use_ai else "."), slot=slot)
                q = rec.tool("save_question_draft", {"slot": slot, "difficulty": level},
                             lambda: gs._store(db, run, c, level, ctx_item, mv_id, q_res),
                             lambda q: {"question_id": q.id, "review_status": q.review_status})
                gs._log(db, run, i, attempt, level, c, q_res, None, question_id=q.id)
                existing.insert(0, c.mcq["question"])
                self.times.append(time.time() - t0)
                run.ready += 1
                run.rejected = dict(rejected)
                db.commit()
                stored = True
                break
            if stored or flag.is_set():
                continue
            if best is not None:
                _, c, ctx_item, q_res, reason, row = best
                rec.decide("keep_as_failed", f"No try passed. The best attempt is kept for the lecturer, marked "
                           f"\"Failed checks\" ({REASONS.get(reason, reason)}). It is not approved.", slot=slot)
                q = rec.tool("save_question_draft", {"slot": slot, "difficulty": level, "failed_checks": True},
                             lambda: gs._store(db, run, c, level, ctx_item, mv_id, q_res, failed_reason=reason),
                             lambda q: {"question_id": q.id, "review_status": q.review_status, "failed_checks": True})
                row.question_id, row.snapshot = q.id, None
                existing.insert(0, c.mcq["question"])
                db.commit()
            else:
                rec.decide("drop", "No try passed, so nothing is saved for this question" + (
                    "." if keep_failed else " (only passing questions are kept here)."), slot=slot)
                db.commit()

    def _after_fail(self, slot: int, attempt: int, tries: int, reason: str):
        text = REASONS.get(reason, reason)
        if attempt + 1 < tries:
            self.rec.decide("retry", f"Failed: {text}. Only this question is generated again.", slot=slot,
                            tries_left=tries - attempt - 1)
        else:
            self.rec.decide("give_up", f"Failed: {text}. No tries left.", slot=slot)

    def finish(self):
        """After the run's status is set: the mix check, the status, and the hand-over to the lecturer."""
        gs, db, run, rec = self.gs, self.db, self.run, self.rec
        summary = rec.tool("check_difficulty_distribution", {"requested": (run.quality or {}).get("requested")},
                           lambda: run.quality or gs._quality_summary(db, run),
                           lambda q: {"requested": q.get("requested"), "judged": q.get("ai_assessed"),
                                      "matches": q.get("mix_matches"), "differs": q.get("mismatched_question_ids"),
                                      "_ok": q.get("mix_matches") is not False})
        if summary.get("mix_matches") is False:
            rec.decide("report_mix", "The judged difficulty mix differs from the request; the questions that differ "
                       "are shown to the lecturer.", question_ids=summary.get("mismatched_question_ids"))
        elif summary.get("mix_matches") is None and summary.get("question_count"):
            rec.decide("report_mix", "The difficulty mix could not be fully checked (no AI judgement for every "
                       "question); labels are the requested ones.")
        status = rec.tool("get_generation_status", {"run_id": run.id},
                          lambda: {"status": run.status, "ready": run.ready, "total": run.total,
                                   "failed_kept": summary.get("failed_kept", 0)})
        if (run.params or {}).get("purpose") == "lecturer_draft" and run.status in ("done", "partial"):
            rec.decide("await_lecturer_approval", "The questions are saved as a draft. The agent never approves or "
                       "publishes; the lecturer reviews every question.")
        rec.finish(run.status, output={**status, "ai_review": summary.get("ai_review")}, error=run.error)


def close_unfinished(db, run: GenerationRun, error: str):
    """Marks the agent run of a generation that crashed or was interrupted."""
    from sqlalchemy import select
    from app.models import AgentRun
    from app.models.base import utcnow
    ar = db.scalar(select(AgentRun).where(AgentRun.generation_run_id == run.id, AgentRun.status == "running"))
    if ar is not None:
        ar.status, ar.error, ar.finished_at = "failed", error, utcnow()
