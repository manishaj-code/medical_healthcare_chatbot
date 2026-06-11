"""Clinic-local date/time helpers for appointment slots."""
from datetime import date, datetime, time
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.database import get_settings


@lru_cache
def clinic_tz() -> ZoneInfo:
    name = get_settings().clinic_timezone
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Asia/Kolkata")


def clinic_now() -> datetime:
    return datetime.now(clinic_tz())


def clinic_today() -> date:
    return clinic_now().date()


def is_slot_past(slot_date: date, slot_time: time) -> bool:
    slot_dt = datetime.combine(slot_date, slot_time, tzinfo=clinic_tz())
    return slot_dt < clinic_now()
