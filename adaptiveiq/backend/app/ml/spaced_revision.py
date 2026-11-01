"""Spaced revision (version REVISION_VERSION): a Leitner schedule.

A missed or skipped question enters box 1 and is due after 1 day. Each later correct answer moves it
up one box (due after 3, 7, 14, then 30 days); after a correct answer in the last box it is retired.
A wrong answer at any box sends it back to box 1.
"""
from datetime import datetime, timedelta

REVISION_VERSION = "leitner-v1"
INTERVAL_DAYS = [1, 3, 7, 14, 30]       # box 1..5


def after_answer(box: int | None, correct: bool, now: datetime) -> tuple[int, datetime | None, str]:
    """Returns (new box, due date or None when retired, status)."""
    if box is None:                      # not scheduled yet
        if correct:
            return 0, None, "none"
        return 1, now + timedelta(days=INTERVAL_DAYS[0]), "active"
    if not correct:
        return 1, now + timedelta(days=INTERVAL_DAYS[0]), "active"
    if box >= len(INTERVAL_DAYS):
        return box, None, "retired"
    return box + 1, now + timedelta(days=INTERVAL_DAYS[box]), "active"
