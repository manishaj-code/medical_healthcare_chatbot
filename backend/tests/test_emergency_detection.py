from app.emergency_detection import (
    detect_emergency,
    detect_mental_health_crisis,
    is_confirmed_emergency,
    is_routine_symptom_message,
)
from app.services.symptom_service import assess_symptoms


def test_headache_is_not_emergency():
    assert detect_emergency("Headache") is False
    assert is_confirmed_emergency("Headache") is False
    assert is_routine_symptom_message("Headache") is True


def test_headache_triage_followups_not_emergency():
    assert is_confirmed_emergency("1 day") is False
    assert is_confirmed_emergency("no") is False


def test_chest_pain_is_emergency():
    assert detect_emergency("I have chest pain and difficulty breathing") is True
    assert is_confirmed_emergency("crushing chest pain") is True
    assert detect_emergency("chest pain") is False
    assert detect_emergency("I have chest pain") is False


def test_mental_health_crisis():
    assert detect_mental_health_crisis("I want to end my life") is True
    assert detect_emergency("I want to end my life") is False


def test_assess_symptoms_headache_not_emergency():
    result = assess_symptoms(["headache"], "1 day", None)
    assert result["risk_level"].value != "emergency"
