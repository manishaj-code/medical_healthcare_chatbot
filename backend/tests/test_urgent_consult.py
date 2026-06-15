"""Urgent consult detection and flow."""
from app.emergency_detection import detect_urgent_consult


def test_severe_stomach_pain_and_breathing_triggers_urgent_consult():
    result = detect_urgent_consult("I have severe stomach pain and breathing issue")
    assert result is not None
    assert result["specialty"] == "Gastroenterologist"
    assert result["er_advisory"] is True
    assert len(result["symptoms"]) >= 1


def test_stroke_triggers_urgent_consult():
    result = detect_urgent_consult("I think I'm having a stroke, my face is drooping")
    assert result is not None
    assert result["risk_level"] == "emergency"
    assert result["specialty"] in ("Neurologist", "General Physician")


def test_severe_bleeding_triggers_urgent_consult():
    result = detect_urgent_consult("There is severe bleeding from my arm and it won't stop")
    assert result is not None
    assert result["er_advisory"] is True


def test_sudden_chest_pain_triggers_urgent_consult():
    result = detect_urgent_consult("Sudden crushing chest pain radiating to my left arm")
    assert result is not None
    assert result["specialty"] == "Cardiologist"
    assert result["risk_level"] == "emergency"


def test_allergic_reaction_triggers_urgent_consult():
    result = detect_urgent_consult("I'm having a severe allergic reaction, throat swelling")
    assert result is not None
    assert result["er_advisory"] is True


def test_routine_headache_not_urgent_consult():
    assert detect_urgent_consult("I have a mild headache") is None


def test_fever_and_headache_without_severity_not_urgent_consult():
    assert detect_urgent_consult("I have fever and headache") is None
