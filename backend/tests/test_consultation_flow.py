"""In-person consultation workflow tests."""
from app.services.consultation_ai_service import _check_allergy_warnings


def test_allergy_warning_on_suggested_med():
    warnings = _check_allergy_warnings(
        [{"medicine_name": "Penicillin VK"}],
        ["Penicillin"],
    )
    assert len(warnings) >= 1


def test_no_allergy_warning_when_clear():
    warnings = _check_allergy_warnings(
        [{"medicine_name": "Paracetamol"}],
        ["Penicillin"],
    )
    assert warnings == []
