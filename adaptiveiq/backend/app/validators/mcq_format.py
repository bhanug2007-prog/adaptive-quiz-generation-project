"""Prompt format + output parser shared by the notebook and the app."""
import re

LETTERS = "ABCD"


def build_input(branch, subject, topic, difficulty, context):
    return (f"generate mcq | branch: {branch} | subject: {subject} | "
            f"topic: {topic} | difficulty: {difficulty} | context: {context}")


_PATTERN = re.compile(
    r"question:\s*(?P<q>.+?)\s*options:\s*"
    r"\(A\)\s*(?P<A>.+?)\s*\(B\)\s*(?P<B>.+?)\s*\(C\)\s*(?P<C>.+?)\s*\(D\)\s*(?P<D>.+?)\s*"
    r"answer:\s*(?P<ans>[ABCD])\b\s*(?:explanation:\s*(?P<exp>.*))?$",
    re.S)


def parse_mcq(text):
    """Parse model output into a dict, or return None if the format is broken."""
    m = _PATTERN.search(text.strip())
    if not m:
        return None
    options = [m.group(l).strip() for l in LETTERS]
    norm = [re.sub(r"\s+", " ", o.lower()) for o in options]
    if any(not o for o in options) or len(set(norm)) < 4:
        return None
    return {"question": m.group("q").strip(), "options": options,
            "answer": m.group("ans"), "explanation": (m.group("exp") or "").strip()}
