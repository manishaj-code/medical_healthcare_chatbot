"""Build pre-visit structured intake from patient context, triage, and reports."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    ConsultationIntake,
    Patient,
    Report,
    SymptomAssessment,
)
from app.services.patient_context import load_patient_context
from app.services.symptom_service import assessment_payload_from_row


def _linked_report_intake(report: Report | None) -> dict | None:
    if not report:
        return None
    analysis = report.analysis_json or {}
    meta = analysis.get("_meta") or {}
    return {
        "report_id": str(report.id),
        "filename": meta.get("filename") or "Medical report",
        "summary": (analysis.get("summary") or "").strip(),
        "abnormal": analysis.get("abnormal") or [],
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def build_structured_intake(db: AsyncSession, patient: Patient, appointment_id: UUID) -> dict:
    ctx = await load_patient_context(db, patient)
    appt = await db.get(Appointment, appointment_id)

    if appt and appt.linked_report_id:
        report = await db.get(Report, appt.linked_report_id)
        linked = _linked_report_intake(report)
        consult_for = appt.appointment_reason or "Medical Report Review & Consultation"
        return {
            "visit_type": "report_discussion",
            "consult_for": consult_for,
            "chief_complaint": consult_for,
            "linked_report": linked,
            "symptoms": [],
            "duration": None,
            "severity": None,
            "medical_history": ctx.get("conditions") or [],
            "allergies": ctx.get("allergies") or [],
            "current_medications": ctx.get("medications") or [],
            "uploaded_reports": [linked] if linked else [],
            "triage_risk": None,
            "recommended_specialty": None,
            "recommendation_text": None,
            "memory_facts": ctx.get("memory_facts") or [],
        }

    assessment_row = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == patient.id)
        .order_by(SymptomAssessment.completed_at.desc().nullslast())
        .limit(1)
    )
    latest = assessment_row.scalar_one_or_none()
    assessment = assessment_payload_from_row(latest) if latest else {}

    reports = await db.execute(
        select(Report).where(Report.patient_id == patient.id).order_by(Report.created_at.desc()).limit(5)
    )
    report_list = [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "has_analysis": bool(r.analysis_json),
        }
        for r in reports.scalars().all()
    ]

    symptoms = assessment.get("symptoms") or []
    chief = symptoms[0] if symptoms else None
    if not chief and assessment.get("recommendation_text"):
        chief = (assessment.get("recommendation_text") or "")[:200]

    return {
        "visit_type": "symptom",
        "chief_complaint": chief,
        "symptoms": symptoms,
        "duration": assessment.get("duration"),
        "severity": assessment.get("risk_level"),
        "medical_history": ctx.get("conditions") or [],
        "allergies": ctx.get("allergies") or [],
        "current_medications": ctx.get("medications") or [],
        "uploaded_reports": report_list,
        "triage_risk": assessment.get("risk_level"),
        "recommended_specialty": assessment.get("recommended_specialty"),
        "recommendation_text": assessment.get("recommendation_text"),
        "memory_facts": ctx.get("memory_facts") or [],
    }


async def ensure_consultation_intake(
    db: AsyncSession, patient: Patient, appointment_id: UUID
) -> ConsultationIntake:
    existing = await db.execute(
        select(ConsultationIntake).where(ConsultationIntake.appointment_id == appointment_id)
    )
    row = existing.scalar_one_or_none()
    structured = await build_structured_intake(db, patient, appointment_id)
    risk = structured.get("triage_risk") or structured.get("severity")

    if row:
        row.structured_intake = structured
        row.ai_risk_level = risk
        row.status = "ready"
        return row

    row = ConsultationIntake(
        appointment_id=appointment_id,
        patient_id=patient.id,
        structured_intake=structured,
        ai_risk_level=risk,
        status="ready",
    )
    db.add(row)
    await db.flush()
    return row
