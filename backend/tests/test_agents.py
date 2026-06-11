from app.agents import (
    LLMClient,
    classify_intent,
    detect_emergency,
    detect_prescription_request,
    get_contextual_reply,
)


def test_emergency_detection():
    assert detect_emergency("I have crushing chest pain") is True
    assert detect_emergency("hello how are you") is False


def test_prescription_refusal():
    assert detect_prescription_request("What antibiotic should I take?") is True


def test_intent_classification():
    assert classify_intent("I have fever and cough") == "triage"
    assert classify_intent("book an appointment") == "appointment"
    assert classify_intent("explain my hemoglobin") == "report"


def test_fallback_llm_emergency():
    import asyncio
    client = LLMClient()
    reply = asyncio.run(client.generate("system", "crushing chest pain", []))
    assert "urgent" in reply.lower() or "emergency" in reply.lower()


def test_thanks_after_home_care():
    history = [
        {"role": "assistant", "content": "Here are some self-care suggestions that may help. I'm here anytime if you'd like to book an appointment."},
    ]
    reply = get_contextual_reply("ok thank you", history)
    assert reply and "welcome" in reply.lower()


def test_thanks_with_prefix_after_assessment():
    from app.healthcare_policy import is_thanks_message

    assert is_thanks_message("om thank you!!")
    history = [
        {
            "role": "assistant",
            "content": "Thanks, Aaaaaaaa. Rest and drink plenty of water. I recommend a General Physician.",
        },
    ]
    reply = get_contextual_reply("om thank you!!", history)
    assert reply and "welcome" in reply.lower()


def test_decline_appointment_gives_home_care():
    history = [
        {"role": "user", "content": "I have fever"},
        {"role": "assistant", "content": "How long have you had these symptoms?"},
        {"role": "user", "content": "2 days"},
        {"role": "assistant", "content": "Do you have any breathing difficulty?"},
        {"role": "user", "content": "no"},
        {"role": "assistant", "content": "Do you have any existing conditions like diabetes, asthma, or hypertension?"},
        {"role": "user", "content": "no"},
        {"role": "assistant", "content": "Would you like to book an appointment?"},
    ]
    reply = get_contextual_reply("no", history)
    assert reply and "water" in reply.lower()
    assert "self-care" in reply.lower() or "hydrated" in reply.lower()


def test_triage_bare_number_asks_unit():
    history = [
        {"role": "user", "content": "I have fever"},
        {"role": "assistant", "content": "How long have you had these symptoms?"},
    ]
    reply = get_contextual_reply("2", history)
    assert reply and "days" in reply.lower() and "hours" in reply.lower()


def test_triage_unit_only_after_number():
    history = [
        {"role": "user", "content": "I have fever"},
        {"role": "assistant", "content": "How long have you had these symptoms?"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "Just to confirm: is that 2 days, 2 hours, or 2 months?"},
    ]
    reply = get_contextual_reply("days", history)
    assert reply and "breathing" in reply.lower()


def test_triage_condition_typo_astama():
    history = [
        {"role": "assistant", "content": "Do you have any existing conditions like diabetes, asthma, or hypertension?"},
    ]
    reply = get_contextual_reply("astama", history)
    assert reply and "appointment" in reply.lower()


def test_triage_multiturn_duration():
    history = [
        {"role": "user", "content": "I have fever and cough"},
        {"role": "assistant", "content": "How long have you had these symptoms?"},
    ]
    reply = get_contextual_reply("from 2 days", history)
    assert reply and "breathing" in reply.lower()


def test_triage_multiturn_diabetes():
    history = [
        {"role": "user", "content": "I have fever and cough"},
        {"role": "assistant", "content": "How long have you had these symptoms?"},
        {"role": "user", "content": "2 days"},
        {"role": "assistant", "content": "Do you have any breathing difficulty?"},
        {"role": "user", "content": "No"},
        {"role": "assistant", "content": "Do you have any existing conditions like diabetes, asthma, or hypertension?"},
    ]
    reply = get_contextual_reply("I have diabetes", history)
    assert reply and "appointment" in reply.lower()


def test_fallback_llm_prescription():
    import asyncio
    client = LLMClient()
    reply = asyncio.run(client.generate("system", "prescribe amoxicillin for me", []))
    assert "cannot prescribe" in reply.lower()


def test_triage_urgent_care_yes_not_loop():
    history = [
        {"role": "assistant", "content": "Do you have any breathing difficulty or shortness of breath?"},
        {"role": "user", "content": "yes"},
        {"role": "assistant", "content": "Breathing difficulty can be serious. Would you like help finding urgent care?"},
    ]
    reply = get_contextual_reply("yes", history)
    assert reply is None


def test_triage_multiturn_book_yes_deferred_to_orchestrator():
    history = [
        {"role": "assistant", "content": "Would you like to book an appointment?"},
    ]
    reply = get_contextual_reply("yes", history)
    assert reply is None


def test_wants_to_book():
    from app.services.appointment_chat_service import wants_to_book

    history = [
        {"role": "assistant", "content": "Would you like to book an appointment?"},
    ]
    assert wants_to_book("yes", history) is True
    assert wants_to_book("no", history) is False


def test_format_doctors_slots_message():
    from app.services.appointment_chat_service import format_doctors_slots_message

    msg = format_doctors_slots_message([
        {
            "name": "Dr. Sharma",
            "specializations": ["General Physician"],
            "rating": 4.8,
            "slots": [{"label": "Tomorrow: 11:00 AM"}],
        }
    ])
    assert "Dr. Sharma" in msg
    assert "11:00 AM" in msg
    assert "option number" in msg.lower()
