"""Tests for stripping pre-consultation text from clinical findings."""
from app.services.consultation_service import clean_clinical_findings_for_record


def test_clean_clinical_findings_removes_triage_template_and_self_care():
    findings = """Presenting symptoms: Fever, Headache.
Duration: 1-3 days.
Medical history: None.
Rest in a quiet, dark room and stay hydrated. Take over-the-counter pain relief if needed. See a doctor if severe, sudden, or recurring.
The patient presents with a chief complaint of fever and headache, with a duration of 1-3 days and low severity.
The patient has no known medical history, allergies, or current medications.
The patient is recommended to see a general physician.
Temp 38.2 C, mild pharyngeal erythema."""

    cleaned = clean_clinical_findings_for_record(
        findings,
        recommendation_text=(
            "Rest in a quiet, dark room and stay hydrated. "
            "Take over-the-counter pain relief if needed. "
            "See a doctor if severe, sudden, or recurring."
        ),
    )

    assert cleaned is not None
    assert "Presenting symptoms" not in cleaned
    assert "Rest in a quiet" not in cleaned
    assert "recommended to see" not in cleaned.lower()
    assert "Temp 38.2" in cleaned


def test_clean_clinical_findings_preserves_doctor_exam_notes():
    text = "BP 120/80. Lungs clear. No lymphadenopathy."
    assert clean_clinical_findings_for_record(text) == text
