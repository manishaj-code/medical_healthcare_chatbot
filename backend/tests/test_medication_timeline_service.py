"""Medication timeline and duration parsing tests."""
from datetime import date

from app.services.medication_timeline_service import (
    _continuation_status,
    estimate_course_end,
    parse_duration_days,
)


def test_parse_duration_days():
    assert parse_duration_days("7 days") == 7
    assert parse_duration_days("2 weeks") == 14
    assert parse_duration_days("1 month") == 30
    assert parse_duration_days("as needed") is None
    assert parse_duration_days("ongoing") is None


def test_estimate_course_end():
    start = date(2026, 6, 1)
    assert estimate_course_end(start, "7 days") == date(2026, 6, 8)


def test_continuation_status_refill_after_course():
    status, refill = _continuation_status(
        prescribed_on=date(2026, 1, 1),
        duration="7 days",
        is_active=True,
        today=date(2026, 6, 16),
    )
    assert status == "refill_suggested"
    assert refill is True


def test_continuation_status_still_in_course():
    status, refill = _continuation_status(
        prescribed_on=date(2026, 6, 10),
        duration="14 days",
        is_active=True,
        today=date(2026, 6, 16),
    )
    assert status == "continue"
    assert refill is False


def test_continuation_status_open_ended_not_refill():
    status, refill = _continuation_status(
        prescribed_on=date(2026, 6, 1),
        duration="until fever resolves",
        is_active=True,
        today=date(2026, 6, 16),
    )
    assert status == "continue"
    assert refill is False
