"""Booking action helpers — regression tests for appointment management routing."""
from unittest.mock import AsyncMock, patch

import pytest

from app.multi_agent.booking_actions import (
    _extract_appointment_uuid,
    _extract_apt_display_id,
    _is_appointment_management_message,
    _parse_set_reminder_token,
    _parse_specialty_from_text,
    _patient_picked_doctor_for_slots,
    _wants_reminder,
    should_skip_booking_resolution,
    synthesize_tool_result,
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


def test_reminder_token_extracts_display_and_uuid():
    msg = "[set_reminder:APT-34A90:550e8400-e29b-41d4-a716-446655440000]"
    assert _wants_reminder(msg)
    assert _parse_set_reminder_token(msg) == {
        "apt_id": "APT-34A90",
        "appointment_id": "550e8400-e29b-41d4-a716-446655440000",
    }
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


def test_patient_picked_doctor_for_slots():
    assert not _patient_picked_doctor_for_slots({}, "doc-1")
    assert not _patient_picked_doctor_for_slots({"awaiting": "pick_duration"}, "doc-1")
    assert _patient_picked_doctor_for_slots({"awaiting": "pick_slot"}, "doc-1")
    assert _patient_picked_doctor_for_slots(
        {"selected_doctor": {"id": "doc-1", "name": "Dr. A"}},
        "doc-1",
    )


@pytest.mark.asyncio
async def test_synthesize_slots_without_doctor_pick_returns_doctor_list():
    tool_result = {
        "slots": [{"label": "Mon 10am", "slot_id": "s1"}],
        "doctor_name": "Dr. Rajesh Sharma",
        "doctor_id": "doc-123",
    }
    ctx = AgentContext(
        db=AsyncMock(),
        conversation=None,
        patient=None,
        conv_id=None,
        text="1-3 days",
        history=[],
        patient_ctx={},
        session={"awaiting": "pick_duration", "detected_symptoms": ["stomach pain"]},
    )
    mock_search = {
        "doctors": [
            {
                "id": "d1",
                "name": "Dr. A",
                "specialty": "Gastroenterologist",
                "slots": [{"label": "Tue 2pm", "slot_id": "s2"}],
            }
        ],
        "total": 1,
    }
    with patch(
        "app.multi_agent.booking_actions.tool_search_doctors",
        new_callable=AsyncMock,
        return_value=mock_search,
    ):
        with patch(
            "app.multi_agent.booking_actions.resolve_patient_first_name",
            new_callable=AsyncMock,
            return_value="John",
        ):
            resp = await synthesize_tool_result(tool_result, ctx)

    assert resp is not None
    assert resp.ui is not None
    assert resp.ui["type"] == "doctor_list"
    assert resp.session_patch.get("awaiting") == "pick_doctor"
