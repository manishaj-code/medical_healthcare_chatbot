"""Patient consult overview aggregation tests."""
from datetime import date, datetime, time, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.patient_consult_summary_service import build_consult_overview_payload


def _appt(
    *,
    status="completed",
    slot_date=None,
    slot_time=None,
    appointment_reason=None,
    linked_report_id=None,
):
    return SimpleNamespace(
        id=uuid4(),
        status=SimpleNamespace(value=status) if not isinstance(status, str) else status,
        slot_date=slot_date or date(2026, 6, 10),
        slot_time=slot_time or time(14, 30),
        consultation_mode="in_person",
        appointment_reason=appointment_reason,
        linked_report_id=linked_report_id,
    )


def _consultation(appt_id, **kwargs):
    return SimpleNamespace(
        appointment_id=appt_id,
        status="completed",
        chief_complaint=kwargs.get("chief_complaint", "Fever"),
        clinical_findings=kwargs.get("clinical_findings", "Temp 101F"),
        diagnosis=kwargs.get("diagnosis", "Viral fever"),
        treatment_plan=kwargs.get("treatment_plan", "Rest and fluids"),
        doctor_notes=kwargs.get("doctor_notes"),
        follow_up_date=kwargs.get("follow_up_date"),
        completed_at=kwargs.get(
            "completed_at",
            datetime(2026, 6, 10, 15, 0, tzinfo=timezone.utc),
        ),
    )


def _report(filename="cbc.pdf", summary="Elevated WBC"):
    rid = uuid4()
    return SimpleNamespace(
        id=rid,
        analysis_json={
            "_meta": {"filename": filename},
            "summary": summary,
            "abnormal": [{"test": "WBC", "value": "12", "flag": "high"}],
        },
        created_at=datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc),
    )


def test_build_overview_merges_visits_and_reports():
    appt = _appt()
    consult = _consultation(appt.id)
    report = _report()
    consultations = {str(appt.id): consult}

    payload = build_consult_overview_payload(
        [appt],
        consultations,
        [report],
        {report.id: report},
        today=date(2026, 6, 15),
    )

    assert payload["rollup"]["completed_visits"] == 1
    assert payload["rollup"]["reports_count"] == 1
    assert "Viral fever" in payload["rollup"]["diagnoses"]
    assert payload["rollup"]["chief_complaints"] == ["Fever"]
    assert "completed consultation" in payload["narrative"].lower()
    assert any(item["type"] == "visit_completed" for item in payload["timeline"])
    assert any(item["type"] == "report_uploaded" for item in payload["timeline"])


def test_report_discussion_upcoming_visit_in_overview():
    report = _report(filename="lipid.pdf", summary="High LDL")
    appt = _appt(
        status="confirmed",
        slot_date=date(2026, 6, 20),
        appointment_reason="Medical Report Review & Consultation",
        linked_report_id=report.id,
    )

    payload = build_consult_overview_payload(
        [appt],
        {},
        [report],
        {report.id: report},
        today=date(2026, 6, 15),
    )

    assert payload["rollup"]["upcoming_visits"] == 1
    upcoming = payload["upcoming_visits"][0]
    assert upcoming["appointment_reason"] == "Medical Report Review & Consultation"
    assert upcoming["linked_report"]["filename"] == "lipid.pdf"
