"""Tests for post-upload report discussion workflow helpers."""
from app.services.report_discussion_service import (
    REPORT_DISCUSSION_DECLINE,
    REPORT_DISCUSSION_REASON,
    compose_report_discussion_reply,
    is_report_doctor_another_choice,
    is_report_doctor_previous_choice,
    is_report_followup_no,
    is_report_followup_yes,
    parse_consultation_mode,
)


def test_compose_report_discussion_reply_includes_question():
    analysis = {
        "summary": "Hemoglobin is slightly low.",
        "abnormal": [{"test": "Hemoglobin", "value": "10.2 g/dL", "flag": "LOW"}],
    }
    reply = compose_report_discussion_reply(analysis)
    assert "Hemoglobin" in reply
    assert "schedule an appointment" in reply.lower()
    assert "educational summary" in reply.lower()


def test_report_followup_yes_no_detection():
    assert is_report_followup_yes("Yes, schedule an appointment")
    assert is_report_followup_no("No, not right now")
    assert not is_report_followup_yes("No, not right now")


def test_parse_consultation_mode():
    assert parse_consultation_mode("Video consultation") == "video"
    assert parse_consultation_mode("In-person consultation") == "in_person"


def test_decline_copy_mentions_health_records():
    assert "health records" in REPORT_DISCUSSION_DECLINE.lower()


def test_report_doctor_choice_detection():
    assert is_report_doctor_previous_choice("Book with Dr. Sharma again for report review")
    assert is_report_doctor_another_choice("Choose another doctor for report review")
    assert not is_report_doctor_previous_choice("Choose another doctor for report review")


def test_history_has_report_discussion_offer():
    from app.services.report_discussion_service import history_has_report_discussion_offer

    history = [
        {"role": "user", "content": "Yes, schedule an appointment"},
        {
            "role": "assistant",
            "content": "Summary...\n\n**Would you like to schedule an appointment with a doctor to discuss your report in detail?**",
        },
    ]
    assert history_has_report_discussion_offer(history)


def test_is_in_report_discussion_flow_after_yes_click():
    from app.services.report_discussion_service import is_in_report_discussion_flow

    history = [
        {"role": "user", "content": "Yes, schedule an appointment"},
        {
            "role": "assistant",
            "content": (
                "**In simple language**\n\n"
                "_This is an educational summary — your doctor can interpret results in full context._\n\n"
                "**Would you like to schedule an appointment with a doctor to discuss your report in detail?**"
            ),
        },
    ]
    assert is_in_report_discussion_flow({}, history)


def test_consultation_mode_turn_not_triage():
    from app.services.report_discussion_service import (
        is_in_report_discussion_flow,
        is_report_consultation_mode_turn,
    )

    history = [
        {"role": "user", "content": "In-person consultation"},
        {
            "role": "assistant",
            "content": (
                "How would you like to meet your doctor for this report review?\n\n"
                "Choose **In-Person Consultation** or **Video Consultation** below."
            ),
        },
    ]
    assert is_report_consultation_mode_turn(history, "In-person consultation")
    assert is_in_report_discussion_flow({}, history)


def test_slot_booking_message_detection():
    from app.services.report_discussion_service import is_slot_booking_message

    assert is_slot_booking_message("Dr. Rajesh Sharma Today: 5:30 PM")
    assert not is_slot_booking_message("In-person consultation")


def test_rehydrate_preserves_pick_doctor_session():
    import asyncio

    from app.services.report_discussion_service import rehydrate_report_discussion_session

    session = {
        "care_goal": "report_discussion",
        "awaiting": "pick_doctor",
        "last_doctor_search": {"doctors": [{"id": "x", "name": "Dr. Sharma"}]},
        "appointment_reason": "Medical Report Review & Consultation",
    }
    history = [
        {"role": "user", "content": "Dr. Rajesh Sharma Today: 5:30 PM"},
        {"role": "assistant", "content": "Perfect! Here are available in-person slots..."},
    ]

    async def run() -> bool:
        return await rehydrate_report_discussion_session(None, session, history, None)

    assert asyncio.run(run())
    assert session["awaiting"] == "pick_doctor"


def test_report_discussion_reason_constant():
    assert REPORT_DISCUSSION_REASON == "Medical Report Review & Consultation"
