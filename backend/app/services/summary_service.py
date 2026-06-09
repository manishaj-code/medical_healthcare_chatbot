from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    Appointment,
    MedicalHistory,
    Medication,
    PatientSummary,
    SymptomAssessment,
)


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
    summary = f"""PATIENT SUMMARY (Pre-Consultation)
Chief Complaint: {', '.join(symptoms) if symptoms else 'Not recorded'}
Duration: {latest.duration if latest else 'N/A'}
Risk Level: {(latest.risk_level.value if hasattr(latest.risk_level, 'value') else latest.risk_level) if latest and latest.risk_level else 'N/A'}
Recommended Specialty: {latest.recommended_specialty if latest else 'N/A'}

Medical History: {', '.join(h.condition for h in history.scalars().all()) or 'None'}
Medications: {', '.join(m.name for m in meds.scalars().all()) or 'None'}
Allergies: {', '.join(a.allergen for a in allergies.scalars().all()) or 'None'}

Recommendation: {latest.recommendation_text if latest else 'Physician evaluation advised.'}
"""

    ps = PatientSummary(
        patient_id=appt.patient_id,
        appointment_id=appointment_id,
        summary_text=summary,
        source_artifact_ids_json={"assessment_id": str(latest.id) if latest else None},
    )
    db.add(ps)
    await db.flush()
    return ps
