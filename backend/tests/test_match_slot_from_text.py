from datetime import time

from app.services.agent_tools import match_slot_from_text


def _slots():
    return [
        {
            "doctor_id": "1",
            "doctor_name": "Dr. Sharma",
            "slot_time": time(9, 0),
            "label": "Today: 9:00 AM",
        },
        {
            "doctor_id": "1",
            "doctor_name": "Dr. Sharma",
            "slot_time": time(9, 0),
            "label": "Tomorrow: 9:00 AM",
        },
        {
            "doctor_id": "2",
            "doctor_name": "Dr. MJ",
            "slot_time": time(9, 0),
            "label": "Today: 9:00 AM",
        },
        {
            "doctor_id": "2",
            "doctor_name": "Dr. MJ",
            "slot_time": time(9, 0),
            "label": "Tomorrow: 9:00 AM",
        },
    ]


def test_tomorrow_time_does_not_match_today_slot():
    slots = _slots()
    chosen = match_slot_from_text("Tomorrow: 9:00 AM", slots, doctor_id="2")
    assert chosen is not None
    assert chosen["doctor_name"] == "Dr. MJ"
    assert "Tomorrow" in chosen["label"]


def test_selected_doctor_scoped_match():
    slots = _slots()
    chosen = match_slot_from_text("Tomorrow: 9:00 AM", slots, doctor_id="2")
    assert chosen["doctor_id"] == "2"
    assert chosen["doctor_name"] == "Dr. MJ"


def test_same_time_different_doctors_prefers_named_doctor():
    slots = _slots()
    chosen = match_slot_from_text("Dr. MJ Tomorrow: 9:00 AM", slots)
    assert chosen is not None
    assert chosen["doctor_name"] == "Dr. MJ"
    assert "Tomorrow" in chosen["label"]
