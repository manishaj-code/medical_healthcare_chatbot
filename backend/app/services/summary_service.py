from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    Appointment,
    MedicalHistory,
    Medication,
    PatientSummary,
    Report,
    SymptomAssessment,
)
from app.services.triage_chat_service import persist_triage_for_patient


async def prepare_appointment_summary(
    db: AsyncSession,
    appointment_id: UUID,
    conversation_id: UUID | None = None,
) -> PatientSummary:
    """Persist chat triage then generate the doctor-facing pre-visit summary."""
    appt = await db.get(Appointment, appointment_id)
    if not appt:
        raise ValueError("Appointment not found")
    try:
        await persist_triage_for_patient(db, appt.patient_id, conversation_id)
    except Exception:
        pass
    return await generate_summary(db, appointment_id)


async def generate_summary(db: AsyncSession, appointment_id: UUID) -> PatientSummary:
    appt = await db.get(Appointment, appointment_id)
    if not appt:
        raise ValueError("Appointment not found")

    assessment = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == appt.patient_id)
        .order_by(SymptomAssessment.completed_at.desc())
        .limit(1)
    )
    latest = assessment.scalar_one_or_none()

    history = await db.execute(select(MedicalHistory).where(MedicalHistory.patient_id == appt.patient_id))
    meds = await db.execute(select(Medication).where(Medication.patient_id == appt.patient_id, Medication.is_active.is_(True)))
    allergies = await db.execute(select(Allergy).where(Allergy.patient_id == appt.patient_id))

    symptoms = latest.symptoms_json.get("symptoms", []) if latest else []
    chief_complaint = (
        appt.appointment_reason
        if appt.appointment_reason
        else (", ".join(symptoms) if symptoms else "Not recorded")
    )

    report_section = ""
    if appt.linked_report_id:
        report = await db.get(Report, appt.linked_report_id)
        if report:
            meta = (report.analysis_json or {}).get("_meta") or {}
            filename = meta.get("filename") or "Uploaded medical report"
            analysis = report.analysis_json or {}
            summary_text = (analysis.get("summary") or "").strip()
            abnormal = analysis.get("abnormal") or []
            abnormal_lines = [
                f"  - {item.get('test', 'Test')}: {item.get('value', '—')} ({item.get('flag', '')})"
                for item in abnormal[:8]
                if isinstance(item, dict)
            ]
            report_section = f"""
Linked Medical Report: {filename}
AI Report Summary: {summary_text or 'See uploaded report in patient records.'}
"""
            if abnormal_lines:
                report_section += "Out-of-range values:\n" + "\n".join(abnormal_lines) + "\n"

    summary = f"""PATIENT SUMMARY (Pre-Consultation)
Chief Complaint: {chief_complaint}
Duration: {latest.duration if latest else 'N/A'}
Risk Level: {(latest.risk_level.value if hasattr(latest.risk_level, 'value') else latest.risk_level) if latest and latest.risk_level else 'N/A'}
Recommended Specialty: {latest.recommended_specialty if latest else 'N/A'}
{report_section}
Medical History: {', '.join(h.condition for h in history.scalars().all()) or 'None'}
Medications: {', '.join(m.name for m in meds.scalars().all()) or 'None'}
Allergies: {', '.join(a.allergen for a in allergies.scalars().all()) or 'None'}

Recommendation: {latest.recommendation_text if latest else 'Physician evaluation advised.'}
"""

    source_ids: dict = {"assessment_id": str(latest.id) if latest else None}
    if appt.linked_report_id:
        source_ids["linked_report_id"] = str(appt.linked_report_id)

    ps = PatientSummary(
        patient_id=appt.patient_id,
        appointment_id=appointment_id,
        summary_text=summary,
        source_artifact_ids_json=source_ids,
    )
    db.add(ps)
    await db.flush()
    return ps
