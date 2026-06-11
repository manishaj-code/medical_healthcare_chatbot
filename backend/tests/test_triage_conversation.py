"""Structured triage conversation — no assumed symptoms from clarifying questions."""
from app.multi_agent.offline_fallback import conversational_triage_turn, _parse_severity


def test_duration_digits_are_not_parsed_as_severity():
    assert _parse_severity("I am doing vomiting from 2 days", {}, awaiting=None) is None
    assert _parse_severity("I am doing vomiting from 2 days", {}, awaiting="pick_duration") is None


def test_severity_buttons_parse_without_awaiting_slot():
    assert _parse_severity("Moderate", {}, awaiting=None) == "Moderate"


def test_vomiting_two_days_asks_severity_not_more_symptoms():
    session = {
        "detected_symptoms": ["Vomiting"],
        "_patient_first_name": "there",
        "triage_collected": {"symptoms": ["Vomiting"]},
    }
    result = conversational_triage_turn("I am doing vomiting from 2 days", session)
    reply = result.get("reply", "").lower()
    assert "stomach pain" not in reply
    assert result.get("session_patch", {}).get("awaiting") == "pick_severity"
    assert "severity" in reply


def test_yes_more_symptoms_opens_free_text_not_stomach_pain():
    session = {
        "detected_symptoms": ["Vomiting"],
        "_patient_first_name": "there",
        "care_goal": "symptom_assessment",
        "awaiting": "more_symptoms",
        "triage_collected": {
            "symptoms": ["Vomiting"],
            "duration": "2 days",
            "severity": "moderate",
            "more_symptoms_asked": True,
            "questions_asked": ["symptoms", "duration", "severity", "more_symptoms"],
        },
    }
    history = [
        {"role": "user", "content": "I am doing vomiting from 2 days"},
        {
            "role": "assistant",
            "content": (
                "Are you also experiencing any other symptoms like "
                "diarrhea, stomach pain, or fever along with the vomiting?"
            ),
        },
    ]
    result = conversational_triage_turn("Yes, I have more symptoms", session, history)
    reply = result.get("reply", "").lower()
    assert "stomach pain" not in reply
    assert "what other symptoms" in reply
    assert result.get("session_patch", {}).get("awaiting") == "more_symptoms"
