"""Triage extraction — symptoms come from patient/session data, not keyword guessing."""
from app.services.triage_chat_service import extract_triage_from_history


def _fever_triage_history() -> list[dict]:
    return [
        {"role": "user", "content": "I have a fever"},
        {"role": "assistant", "content": "How long have you been experiencing this?"},
        {"role": "user", "content": "1-3 days"},
        {"role": "assistant", "content": "Do you have any breathing difficulty or shortness of breath?"},
        {"role": "user", "content": "no"},
        {"role": "assistant", "content": "Would you like to book an appointment?"},
        {"role": "user", "content": "yes"},
    ]


def test_history_extraction_does_not_infer_symptoms():
    data = extract_triage_from_history(_fever_triage_history())
    assert data["symptoms"] == []
    assert "1-3 days" in (data["duration"] or "")


def test_history_extraction_never_adds_breathing_from_yes():
    history = [
        {"role": "user", "content": "I have a fever"},
        {"role": "assistant", "content": "Do you have any breathing difficulty or shortness of breath?"},
        {"role": "user", "content": "yes"},
    ]
    data = extract_triage_from_history(history)
    assert data["symptoms"] == []
