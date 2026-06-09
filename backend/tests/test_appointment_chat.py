from datetime import time

from app.services.appointment_chat_service import (
    _choose_slot_from_text,
    _parse_time_from_text,
)


def _opts():
    return [
        {
            "doctor_id": "1",
            "doctor_name": "Dr. Sharma",
            "slot_time": time(11, 0),
            "label": "Today: 11:00 AM",
        },
        {
            "doctor_id": "1",
            "doctor_name": "Dr. Sharma",
            "slot_time": time(16, 0),
            "label": "Today: 4:00 PM",
        },
        {
            "doctor_id": "1",
            "doctor_name": "Dr. Sharma",
            "slot_time": time(14, 0),
            "label": "Today: 2:00 PM",
        },
        {
            "doctor_id": "2",
            "doctor_name": "Dr. Patel",
            "slot_time": time(11, 0),
            "label": "Today: 11:00 AM",
        },
    ]


def test_parse_time_with_pm():
    assert _parse_time_from_text("dr sharma today 2:00 pm") == time(14, 0)
    assert _parse_time_from_text("11:00 am") == time(11, 0)
    assert _parse_time_from_text("Dr. Sharma today: 4.00 PM") == time(16, 0)


def test_choose_slot_dot_time_format():
    opts = [
        {"doctor_id": "1", "doctor_name": "Dr. Sharma", "slot_time": time(16, 0), "label": "Today: 4:00 PM"},
        {"doctor_id": "1", "doctor_name": "Dr. Sharma", "slot_time": time(9, 0), "label": "Tomorrow: 9:00 AM"},
    ]
    slot, hint = _choose_slot_from_text("Dr. Sharma today: 4.00 PM", opts)
    assert slot is not None
    assert slot["slot_time"] == time(16, 0)
    assert hint is None


def test_choose_slot_doctor_day_time():
    slot, hint = _choose_slot_from_text("Dr Sharma today 2:00 PM", _opts())
    assert slot is not None
    assert slot["slot_time"] == time(14, 0)
    assert hint is None


def test_choose_slot_does_not_pick_wrong_time():
    slot, hint = _choose_slot_from_text("Dr Sharma today 2:00 PM", _opts())
    assert slot["slot_time"] != time(11, 0)


def test_choose_slot_wrong_time_gives_hint():
    opts = [_opts()[0]]  # only 11 AM
    slot, hint = _choose_slot_from_text("Dr Sharma today 2:00 PM", opts)
    assert slot is None
    assert hint and "2:00" in hint.lower() or "not" in hint.lower()
