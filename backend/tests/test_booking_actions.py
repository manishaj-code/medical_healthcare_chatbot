"""Booking action helpers — regression tests for appointment management routing."""
from app.multi_agent.booking_actions import (
    _extract_appointment_uuid,
    _extract_apt_display_id,
    _is_appointment_management_message,
    _parse_specialty_from_text,
    _wants_reminder,
    should_skip_booking_resolution,
)
from app.multi_agent.types import AgentContext


def test_reminder_message_is_appointment_management():
    msg = "Set a reminder 30 minutes before appointment APT-FF7FB"
    assert _wants_reminder(msg)
    assert _is_appointment_management_message(msg)


def test_reminder_message_does_not_parse_as_ent_specialty():
    msg = "Set a reminder 30 minutes before appointment APT-FF7FB"
    assert _parse_specialty_from_text(msg) is None


def test_ent_specialty_still_parses_when_explicit():
    assert _parse_specialty_from_text("I need an ENT specialist") == "ENT Specialist"


def test_reminder_message_extracts_display_and_uuid():
    msg = (
        "Set a reminder 30 minutes before appointment APT-34A90 "
        "appointment_id:550e8400-e29b-41d4-a716-446655440000"
    )
    assert _wants_reminder(msg)
    assert _extract_apt_display_id(msg) == "APT-34A90"
    assert str(_extract_appointment_uuid(msg)) == "550e8400-e29b-41d4-a716-446655440000"


def test_reminder_not_skipped_during_symptom_triage():
    ctx = AgentContext(
        db=None,
        conversation=None,
        patient=None,
        conv_id=None,
        text="Set a reminder 30 minutes before appointment APT-34A90",
        history=[],
        patient_ctx={},
        session={"care_goal": "symptom_assessment", "active_specialist": "triage_agent"},
    )
    assert should_skip_booking_resolution(ctx) is False
