"""Structured triage conversation — no assumed symptoms from clarifying questions."""
from app.healthcare_policy import should_use_legacy_contextual_reply
from app.multi_agent.offline_fallback import conversational_triage_turn, _parse_severity


def test_structured_triage_disables_legacy_contextual_reply():
    session = {
        "care_goal": "symptom_assessment",
        "awaiting": "pick_duration",
        "detected_symptoms": ["Fever"],
    }
    assert should_use_legacy_contextual_reply(session) is False
    assert should_use_legacy_contextual_reply({"detected_symptoms": ["Fever"]}) is False
    assert should_use_legacy_contextual_reply(
        {"triage_collected": {"symptoms": ["Fever"], "questions_asked": ["symptoms"]}}
    ) is False
    assert should_use_legacy_contextual_reply({"care_goal": "symptom_assessment", "triage_assessed": True}) is True


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
    assert ", there" not in reply
    assert result.get("session_patch", {}).get("awaiting") == "list_more_symptoms"
    assert result.get("session_patch", {}).get("triage_collected", {}).get("more_symptoms_list_prompted") is True


def test_repeat_yes_more_symptoms_nudges_instead_of_looping():
    session = {
        "detected_symptoms": ["Vomiting"],
        "_patient_first_name": "there",
        "care_goal": "symptom_assessment",
        "awaiting": "list_more_symptoms",
        "triage_collected": {
            "symptoms": ["Vomiting"],
            "duration": "2 days",
            "severity": "moderate",
            "more_symptoms_asked": True,
            "more_symptoms_list_prompted": True,
            "questions_asked": ["symptoms", "duration", "severity", "more_symptoms"],
        },
    }
    result = conversational_triage_turn("Yes, I have more symptoms", session)
    reply = result.get("reply", "").lower()
    assert "please type" in reply
    assert "what other symptoms are you experiencing" not in reply
    assert result.get("ui", {}).get("options") == [{"label": "No, that's all", "message": "No other symptoms"}]


def test_typed_symptoms_after_list_prompt_proceeds_to_assess():
    session = {
        "detected_symptoms": ["Vomiting", "Fever"],
        "_patient_first_name": "there",
        "care_goal": "symptom_assessment",
        "awaiting": "list_more_symptoms",
        "triage_collected": {
            "symptoms": ["Vomiting", "Fever"],
            "duration": "2 days",
            "severity": "moderate",
            "more_symptoms_asked": True,
            "more_symptoms_list_prompted": True,
            "questions_asked": ["symptoms", "duration", "severity", "more_symptoms"],
        },
    }
    result = conversational_triage_turn("fever", session)
    assert result.get("tool") == "assess_symptoms"
    assert "Fever" in result.get("tool_args", {}).get("symptoms", [])


def test_new_complaint_after_prior_triage_asks_duration():
    """A fresh symptom message must not reuse duration/severity from an earlier assessment."""
    session = {
        "detected_symptoms": ["Fever", "Headache"],
        "care_goal": "symptom_assessment",
        "active_specialist": "triage_agent",
        "triage_collected": {
            "symptoms": ["Fever", "Headache"],
            "notes": ["I have fever and headache"],
            "questions_asked": ["symptoms"],
        },
    }
    result = conversational_triage_turn("I have fever and headache", session)
    reply = result.get("reply", "").lower()
    assert result.get("tool") != "assess_symptoms"
    assert "how long" in reply
    assert result.get("session_patch", {}).get("awaiting") == "pick_duration"
